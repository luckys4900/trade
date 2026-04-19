import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd
from pykalman import KalmanFilter

logger = logging.getLogger(__name__)


class KalmanHedgeRatio:
    def __init__(self, delta: float = 1e-4, obs_noise: float = 1e-3):
        self.delta = delta
        self.obs_noise = obs_noise
        self.state_mean: Optional[np.ndarray] = None
        self.state_cov: Optional[np.ndarray] = None
        self.warm_up: int = 60

    def initialize(self, btc_price: float, eth_price: float) -> None:
        init_slope = eth_price / btc_price if btc_price > 0 else 1.0
        self.state_mean = np.array([0.0, init_slope])
        self.state_cov = np.eye(2)
        logger.info("Kalman initialized: slope=%.4f", init_slope)

    def update(self, btc_price: float, eth_price: float) -> Dict[str, float]:
        if self.state_mean is None:
            self.initialize(btc_price, eth_price)

        obs_matrix = np.array([[1.0, btc_price]])
        trans_cov = (self.delta / (1.0 - self.delta)) * np.eye(2)

        predicted_mean = self.state_mean.copy()
        predicted_cov = self.state_cov + trans_cov

        innovation = eth_price - (obs_matrix @ predicted_mean)[0]
        innovation_cov = (obs_matrix @ predicted_cov @ obs_matrix.T)[
            0, 0
        ] + self.obs_noise
        kalman_gain = (predicted_cov @ obs_matrix.T) / innovation_cov

        self.state_mean = predicted_mean + (kalman_gain.flatten() * innovation)
        self.state_cov = predicted_cov - kalman_gain @ obs_matrix @ predicted_cov
        self.state_cov = (self.state_cov + self.state_cov.T) / 2

        hedge_ratio = float(self.state_mean[1])
        intercept = float(self.state_mean[0])
        spread = eth_price - hedge_ratio * btc_price - intercept
        uncertainty = float(np.sqrt(self.state_cov[1, 1]))

        return {
            "hedge_ratio": hedge_ratio,
            "intercept": intercept,
            "spread": spread,
            "uncertainty": uncertainty,
        }

    def batch_update(
        self,
        btc_series: pd.Series,
        eth_series: pd.Series,
    ) -> pd.DataFrame:
        records = []
        indices = []

        for i in range(len(btc_series)):
            btc_p = float(btc_series.iloc[i])
            eth_p = float(eth_series.iloc[i])

            if i < self.warm_up:
                self.update(btc_p, eth_p)
                records.append(
                    {
                        "hedge_ratio": np.nan,
                        "intercept": np.nan,
                        "spread": np.nan,
                        "uncertainty": np.nan,
                    }
                )
            else:
                result = self.update(btc_p, eth_p)
                records.append(result)

            indices.append(btc_series.index[i])

        df = pd.DataFrame(records, index=indices)
        df.index.name = "timestamp"
        n_valid = df["hedge_ratio"].notna().sum()
        logger.info("Kalman hedge ratio: %d/%d valid rows", n_valid, len(df))
        return df

    def plot_hedge_ratio(
        self,
        kalman_df: pd.DataFrame,
        ols_ratio: float,
        save_path: str,
    ) -> None:
        import matplotlib.pyplot as plt

        valid = kalman_df.dropna(subset=["hedge_ratio"])

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.plot(valid.index, valid["hedge_ratio"], linewidth=0.8, label="Kalman")
        ax.axhline(ols_ratio, color="red", linestyle="--", label=f"OLS={ols_ratio:.4f}")
        ax.fill_between(
            valid.index,
            valid["hedge_ratio"] - 2 * valid["uncertainty"],
            valid["hedge_ratio"] + 2 * valid["uncertainty"],
            alpha=0.2,
            color="steelblue",
        )
        ax.set_title("Kalman Hedge Ratio vs Static OLS")
        ax.set_ylabel("Hedge Ratio (ETH per BTC)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(save_path, dpi=150)
        plt.close(fig)
        logger.info("Saved: %s", save_path)
