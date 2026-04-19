import logging
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint, OLS
from tqdm import tqdm

logger = logging.getLogger(__name__)


class CointegrationMonitor:
    def __init__(
        self,
        window: int = 120,
        p_threshold_strong: float = 0.01,
        p_threshold_moderate: float = 0.05,
    ):
        self.window = window
        self.p_strong = p_threshold_strong
        self.p_moderate = p_threshold_moderate

    def _classify_regime(self, p_value: float) -> str:
        if p_value < self.p_strong:
            return "STRONG"
        elif p_value < self.p_moderate:
            return "MODERATE"
        return "NONE"

    def rolling_coint_test(
        self,
        btc_series: pd.Series,
        eth_series: pd.Series,
        step: int = 4,
    ) -> pd.DataFrame:
        n = len(btc_series)
        results = []
        indices = []

        for i in tqdm(
            range(self.window, n, step),
            desc="Rolling cointegration",
            leave=False,
        ):
            btc_win = btc_series.iloc[i - self.window : i]
            eth_win = eth_series.iloc[i - self.window : i]

            try:
                score, p_value, _ = coint(btc_win, eth_win)
            except Exception:
                continue

            try:
                ols_model = OLS(eth_win.values, btc_win.values).fit()
                hedge_ratio = float(ols_model.params[0])
            except Exception:
                hedge_ratio = np.nan

            regime = self._classify_regime(p_value)
            results.append(
                {
                    "p_value": p_value,
                    "coint_stat": score,
                    "hedge_ratio_ols": hedge_ratio,
                    "regime": regime,
                }
            )
            indices.append(btc_series.index[i])

        df = pd.DataFrame(results, index=indices)
        df.index.name = "timestamp"
        logger.info(
            "Cointegration regimes: STRONG=%d MODERATE=%d NONE=%d",
            (df["regime"] == "STRONG").sum(),
            (df["regime"] == "MODERATE").sum(),
            (df["regime"] == "NONE").sum(),
        )
        return df

    @staticmethod
    def get_position_size_multiplier(regime: str) -> float:
        if regime == "STRONG":
            return 1.0
        elif regime == "MODERATE":
            return 0.5
        return 0.0

    def regime_stats(self, coint_df: pd.DataFrame) -> Dict[str, float]:
        total = len(coint_df)
        if total == 0:
            return {"STRONG": 0, "MODERATE": 0, "NONE": 0}
        counts = coint_df["regime"].value_counts()
        return {
            "STRONG": counts.get("STRONG", 0) / total * 100,
            "MODERATE": counts.get("MODERATE", 0) / total * 100,
            "NONE": counts.get("NONE", 0) / total * 100,
        }

    def plot_rolling_pvalue(self, df: pd.DataFrame, save_path: str) -> None:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.semilogy(df.index, df["p_value"], linewidth=0.8, color="steelblue")
        ax.axhline(
            self.p_strong, color="green", linestyle="--", label=f"p={self.p_strong}"
        )
        ax.axhline(
            self.p_moderate,
            color="orange",
            linestyle="--",
            label=f"p={self.p_moderate}",
        )

        regimes = df["regime"].values
        colors = {"STRONG": "green", "MODERATE": "yellow", "NONE": "red"}
        for i in range(len(df) - 1):
            ax.axvspan(
                df.index[i],
                df.index[i + 1],
                alpha=0.15,
                color=colors.get(regimes[i], "gray"),
            )

        ax.set_title("Rolling Cointegration p-value")
        ax.set_ylabel("p-value (log scale)")
        ax.legend()
        ax.set_ylim(1e-4, 1)
        fig.tight_layout()
        fig.savefig(save_path, dpi=150)
        plt.close(fig)
        logger.info("Saved: %s", save_path)
