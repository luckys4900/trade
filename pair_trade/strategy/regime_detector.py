import logging
from typing import Dict, List, Tuple
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CorrelationRegime(Enum):
    """
    Regime classification based on rolling correlation.
    """
    HIGH_CORR = "HIGH_CORR"       # corr >= 0.75
    NORMAL_REGIME = "NORMAL"      # 0.5 <= corr < 0.75
    LOW_CORR = "LOW_CORR"         # corr < 0.5


class RegimeDetector:
    """
    Detects market regimes based on rolling correlation between BTC and ETH.
    Updates regime every bar, using a 20-bar lookback window.
    """

    def __init__(
        self,
        correlation_window: int = 20,
        high_corr_threshold: float = 0.75,
        low_corr_threshold: float = 0.50,
    ):
        self.corr_window = correlation_window
        self.high_thresh = high_corr_threshold
        self.low_thresh = low_corr_threshold

    def compute_rolling_correlation(
        self,
        btc_series: pd.Series,
        eth_series: pd.Series,
    ) -> pd.Series:
        """
        Compute rolling correlation between BTC and ETH.

        Args:
            btc_series: BTC price series
            eth_series: ETH price series

        Returns:
            Series of rolling correlations
        """
        # Use log returns for correlation (more stable)
        btc_returns = np.log(btc_series / btc_series.shift(1)).dropna()
        eth_returns = np.log(eth_series / eth_series.shift(1)).dropna()

        common_idx = btc_returns.index.intersection(eth_returns.index)
        btc_ret = btc_returns.loc[common_idx]
        eth_ret = eth_returns.loc[common_idx]

        rolling_corr = btc_ret.rolling(self.corr_window).corr(eth_ret)
        return rolling_corr

    def classify_regime(self, correlation: float) -> CorrelationRegime:
        """
        Classify regime based on correlation value.

        Args:
            correlation: current rolling correlation

        Returns:
            CorrelationRegime enum value
        """
        if correlation >= self.high_thresh:
            return CorrelationRegime.HIGH_CORR
        elif correlation >= self.low_thresh:
            return CorrelationRegime.NORMAL_REGIME
        else:
            return CorrelationRegime.LOW_CORR

    def get_position_multiplier(self, regime: CorrelationRegime) -> float:
        """
        Get position size multiplier for each regime.

        HIGH_CORR:   1.0x (full position)
        NORMAL:      0.5x (50% reduced)
        LOW_CORR:    0.0x (no new trades, close existing)

        Args:
            regime: CorrelationRegime enum

        Returns:
            Position multiplier [0.0, 1.0]
        """
        multipliers = {
            CorrelationRegime.HIGH_CORR: 1.0,
            CorrelationRegime.NORMAL_REGIME: 0.5,
            CorrelationRegime.LOW_CORR: 0.0,
        }
        return multipliers.get(regime, 0.0)

    def detect_regimes(
        self,
        btc_series: pd.Series,
        eth_series: pd.Series,
    ) -> pd.DataFrame:
        """
        Full regime detection pipeline.

        Args:
            btc_series: BTC price series with datetime index
            eth_series: ETH price series with datetime index

        Returns:
            DataFrame with columns: timestamp, correlation, regime, multiplier
        """
        rolling_corr = self.compute_rolling_correlation(btc_series, eth_series)

        # Align with common dates
        common_idx = rolling_corr.index

        regimes = []
        for ts in common_idx:
            corr_val = rolling_corr.loc[ts]

            if pd.isna(corr_val):
                regime = CorrelationRegime.NORMAL_REGIME
                mult = 0.5
            else:
                regime = self.classify_regime(corr_val)
                mult = self.get_position_multiplier(regime)

            regimes.append({
                'timestamp': ts,
                'correlation': corr_val,
                'regime': regime.value,
                'multiplier': mult,
            })

        df = pd.DataFrame(regimes).set_index('timestamp')

        # Statistics
        regime_counts = df['regime'].value_counts()
        logger.info(
            "Regime distribution: %s",
            regime_counts.to_dict(),
        )

        return df

    def get_regime_statistics(self, regime_df: pd.DataFrame) -> Dict:
        """
        Compute statistics on regime distribution and correlation.

        Args:
            regime_df: DataFrame from detect_regimes()

        Returns:
            Dictionary with statistics
        """
        if regime_df.empty:
            return {}

        corr_data = regime_df['correlation'].dropna()

        return {
            'mean_correlation': float(corr_data.mean()),
            'std_correlation': float(corr_data.std()),
            'min_correlation': float(corr_data.min()),
            'max_correlation': float(corr_data.max()),
            'pct_high_corr': float(
                (regime_df['regime'] == CorrelationRegime.HIGH_CORR.value).sum() / len(regime_df) * 100
            ),
            'pct_normal': float(
                (regime_df['regime'] == CorrelationRegime.NORMAL_REGIME.value).sum() / len(regime_df) * 100
            ),
            'pct_low_corr': float(
                (regime_df['regime'] == CorrelationRegime.LOW_CORR.value).sum() / len(regime_df) * 100
            ),
        }
