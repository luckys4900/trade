import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from pykalman import KalmanFilter
from statsmodels.regression.linear_model import OLS

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

    def compute_monthly_beta(
        self,
        btc_series: pd.Series,
        eth_series: pd.Series,
        lookback_days: int = 60,
    ) -> pd.DataFrame:
        """
        Compute monthly hedge ratio (beta) updates.
        Every month-start, use past 60 days of data for OLS regression.

        Args:
            btc_series: BTC price series with datetime index
            eth_series: ETH price series with datetime index
            lookback_days: days of history to use for OLS (default 60)

        Returns:
            DataFrame with monthly beta values
        """
        common_idx = btc_series.index.intersection(eth_series.index)
        btc_close = btc_series.loc[common_idx]
        eth_close = eth_series.loc[common_idx]

        # Get unique month-starts
        month_starts = pd.date_range(
            start=btc_close.index.min(),
            end=btc_close.index.max(),
            freq='MS'
        )

        monthly_betas = []

        for month_start in month_starts:
            lookback_start = month_start - timedelta(days=lookback_days)
            fit_idx = btc_close.index[(btc_close.index >= lookback_start) &
                                       (btc_close.index < month_start)]

            if len(fit_idx) < 10:
                continue

            x_data = btc_close.loc[fit_idx].values
            y_data = eth_close.loc[fit_idx].values

            try:
                x_with_const = np.column_stack([x_data, np.ones(len(x_data))])
                ols_model = OLS(y_data, x_with_const).fit()
                beta = float(ols_model.params[0])
                r_squared = float(ols_model.rsquared)

                monthly_betas.append({
                    'month_start': month_start,
                    'beta': beta,
                    'r_squared': r_squared,
                    'n_obs': len(fit_idx),
                })
            except Exception as e:
                logger.warning(f"Failed to compute beta for {month_start}: {e}")
                continue

        df = pd.DataFrame(monthly_betas)
        if not df.empty:
            logger.info(
                "Computed %d monthly betas (range: %.4f - %.4f)",
                len(df),
                df['beta'].min(),
                df['beta'].max(),
            )
        return df

    def apply_monthly_beta_to_spread(
        self,
        btc_series: pd.Series,
        eth_series: pd.Series,
        monthly_betas: pd.DataFrame,
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Apply monthly-updated hedge ratios to compute spread.
        For each timestamp, use the beta from its corresponding month.

        Args:
            btc_series: BTC prices with datetime index
            eth_series: ETH prices with datetime index
            monthly_betas: DataFrame with month_start and beta columns

        Returns:
            Tuple of (spread series, hedge_ratio_df with monthly updates)
        """
        if monthly_betas.empty:
            logger.warning("No monthly betas available, falling back to Kalman")
            return pd.Series(dtype=float), pd.DataFrame()

        common_idx = btc_series.index.intersection(eth_series.index)
        btc_close = btc_series.loc[common_idx]
        eth_close = eth_series.loc[common_idx]

        spreads = []
        hedge_ratios = []

        for i, ts in enumerate(common_idx):
            # Find which month this timestamp belongs to
            month_idx = (monthly_betas['month_start'] <= ts).idxmax() if (monthly_betas['month_start'] <= ts).any() else -1

            if month_idx == -1 or month_idx >= len(monthly_betas):
                continue

            beta = monthly_betas.iloc[month_idx]['beta']
            spread = eth_close.iloc[i] - beta * btc_close.iloc[i]

            spreads.append(spread)
            hedge_ratios.append({
                'timestamp': ts,
                'hedge_ratio': beta,
                'spread': spread,
                'month_start': monthly_betas.iloc[month_idx]['month_start'],
            })

        spread_series = pd.Series(spreads, index=common_idx[:len(spreads)])
        hedge_ratio_df = pd.DataFrame(hedge_ratios).set_index('timestamp')

        logger.info(
            "Applied monthly beta to %d timestamps",
            len(spread_series),
        )
        return spread_series, hedge_ratio_df

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
