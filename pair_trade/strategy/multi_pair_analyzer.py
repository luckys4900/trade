import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint, adfuller

logger = logging.getLogger(__name__)


class MultiPairAnalyzer:
    """
    Analyze stability and cointegration of multiple currency pairs.

    Pairs to test:
    - BTC/ETH (baseline)
    - BTC/SOL
    - ETH/SOL
    - BTC/XRP
    """

    def __init__(self, rolling_window: int = 120):
        self.window = rolling_window

    def compute_correlation_stability(
        self,
        price_series1: pd.Series,
        price_series2: pd.Series,
        window: int = 20,
    ) -> Dict[str, float]:
        """
        Measure correlation stability between two assets.

        Args:
            price_series1: First asset price series
            price_series2: Second asset price series
            window: Rolling correlation window (bars)

        Returns:
            Dictionary with stability metrics
        """
        # Log returns
        ret1 = np.log(price_series1 / price_series1.shift(1)).dropna()
        ret2 = np.log(price_series2 / price_series2.shift(1)).dropna()

        common_idx = ret1.index.intersection(ret2.index)
        ret1 = ret1.loc[common_idx]
        ret2 = ret2.loc[common_idx]

        rolling_corr = ret1.rolling(window).corr(ret2)

        return {
            'mean_corr': float(rolling_corr.mean()),
            'std_corr': float(rolling_corr.std()),
            'min_corr': float(rolling_corr.min()),
            'max_corr': float(rolling_corr.max()),
            'stability_ratio': float(rolling_corr.std() / abs(rolling_corr.mean()) if rolling_corr.mean() != 0 else 0),
        }

    def test_cointegration(
        self,
        price_series1: pd.Series,
        price_series2: pd.Series,
    ) -> Dict:
        """
        Test if two price series are cointegrated using Johansen/Engle-Granger.

        Args:
            price_series1: First asset price series
            price_series2: Second asset price series

        Returns:
            Dictionary with cointegration metrics
        """
        common_idx = price_series1.index.intersection(price_series2.index)
        p1 = price_series1.loc[common_idx].values
        p2 = price_series2.loc[common_idx].values

        try:
            score, p_value, critical_values = coint(p1, p2)
        except Exception as e:
            logger.warning(f"Cointegration test failed: {e}")
            return {
                'cointegrated': False,
                'p_value': 1.0,
                'coint_score': np.nan,
            }

        return {
            'cointegrated': p_value < 0.05,
            'p_value': float(p_value),
            'coint_score': float(score),
            'is_strong': p_value < 0.01,
        }

    def compute_halflife_by_window(
        self,
        price1: pd.Series,
        price2: pd.Series,
        hedge_ratio: float = None,
        n_windows: int = 10,
    ) -> Dict:
        """
        Estimate half-life of mean reversion in rolling windows.
        Shows how quickly spread reverts to mean.

        Args:
            price1: First asset price
            price2: Second asset price
            hedge_ratio: Hedge ratio (default: OLS estimate)
            n_windows: Number of rolling windows to test

        Returns:
            Dictionary with half-life statistics
        """
        common_idx = price1.index.intersection(price2.index)
        p1 = price1.loc[common_idx]
        p2 = price2.loc[common_idx]

        if hedge_ratio is None:
            # OLS estimate
            x = np.column_stack([p1.values, np.ones(len(p1))])
            try:
                coef = np.linalg.lstsq(x, p2.values, rcond=None)[0]
                hedge_ratio = coef[0]
            except:
                hedge_ratio = 1.0

        # Compute spread
        spread = p1 - hedge_ratio * p2

        # Rolling half-lives
        half_lives = []
        window_size = len(spread) // n_windows

        for i in range(n_windows - 1):
            start_idx = i * window_size
            end_idx = (i + 1) * window_size
            window_spread = spread.iloc[start_idx:end_idx]

            hl = self._estimate_halflife(window_spread)
            if not np.isnan(hl):
                half_lives.append(hl)

        if not half_lives:
            return {
                'mean_halflife_bars': np.nan,
                'mean_halflife_hours': np.nan,
                'min_halflife': np.nan,
                'max_halflife': np.nan,
                'halflife_std': np.nan,
            }

        return {
            'mean_halflife_bars': float(np.mean(half_lives)),
            'mean_halflife_hours': float(np.mean(half_lives) * 4),
            'min_halflife': float(np.min(half_lives)),
            'max_halflife': float(np.max(half_lives)),
            'halflife_std': float(np.std(half_lives)),
        }

    @staticmethod
    def _estimate_halflife(spread: pd.Series) -> float:
        """Estimate half-life of mean reversion."""
        if len(spread) < 10:
            return np.nan

        spread_values = spread.dropna().values
        spread_lag = spread_values[:-1]
        delta = np.diff(spread_values)

        if len(spread_lag) < 5:
            return np.nan

        x = np.column_stack([spread_lag, np.ones(len(spread_lag))])
        try:
            beta = np.linalg.lstsq(x, delta, rcond=None)[0]
            lam = beta[0]
            if lam >= 0:
                return np.nan
            halflife = -np.log(2) / np.log(1 + lam)
            return max(0.0, halflife)
        except:
            return np.nan

    def compare_pairs(
        self,
        pairs: Dict[str, Tuple[pd.Series, pd.Series]],
    ) -> pd.DataFrame:
        """
        Compare multiple pairs across various metrics.

        Args:
            pairs: Dictionary of {pair_name: (price1_series, price2_series)}

        Returns:
            DataFrame with comparison results
        """
        results = []

        for pair_name, (p1, p2) in pairs.items():
            logger.info(f"Analyzing pair: {pair_name}")

            # Correlation stability
            corr_stats = self.compute_correlation_stability(p1, p2)

            # Cointegration
            coint_stats = self.test_cointegration(p1, p2)

            # Half-life
            hl_stats = self.compute_halflife_by_window(p1, p2)

            results.append({
                'pair': pair_name,
                'mean_corr': corr_stats['mean_corr'],
                'corr_stability': corr_stats['stability_ratio'],
                'cointegrated': coint_stats['cointegrated'],
                'coint_p_value': coint_stats['p_value'],
                'mean_halflife_bars': hl_stats['mean_halflife_bars'],
                'halflife_std': hl_stats['halflife_std'],
            })

        df = pd.DataFrame(results)

        # Rank pairs by stability (lower std_corr is better)
        df['stability_rank'] = df['corr_stability'].rank()

        logger.info("Pair comparison:\n%s", df.to_string())
        return df

    def stability_score(self, pair_metrics: Dict) -> float:
        """
        Compute overall stability score for a pair.

        Higher score = more stable.

        Factors:
        - Correlation mean (prefer high)
        - Correlation stability (prefer low std)
        - Cointegration p-value (prefer low)
        - Half-life consistency (prefer low std)

        Args:
            pair_metrics: Dictionary with metrics from test_cointegration, etc.

        Returns:
            Score [0, 100]
        """
        score = 50.0  # baseline

        # Cointegration (strong = +20)
        if pair_metrics.get('coint_p_value', 1.0) < 0.01:
            score += 20
        elif pair_metrics.get('coint_p_value', 1.0) < 0.05:
            score += 10

        # Correlation (high = +20)
        mean_corr = pair_metrics.get('mean_corr', 0)
        if mean_corr > 0.7:
            score += 20
        elif mean_corr > 0.5:
            score += 10

        # Stability (low std = +10)
        corr_std = pair_metrics.get('corr_stability', 1.0)
        if corr_std < 0.3:
            score += 10
        elif corr_std < 0.6:
            score += 5

        return max(0, min(100, score))
