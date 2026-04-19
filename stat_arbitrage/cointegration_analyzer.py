import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import logging

logger = logging.getLogger(__name__)


class CointegrationAnalyzer:
    def __init__(self):
        pass

    def johansen_test(self, series1: pd.Series, series2: pd.Series, det_order: int = 0) -> dict:
        """Perform Johansen cointegration test"""
        data = np.column_stack((series1.values, series2.values))

        result = coint_johansen(data, det_order=det_order, k_ar_diff=1)

        eigenvalue = result.eig[0]
        trace_stat = result.lr1[0]
        crit_val = result.cvt[0, 0]

        # Simple p-value: based on whether trace_stat exceeds critical value
        p_value = 0.01 if trace_stat > crit_val else 0.50

        return {
            'eigenvalue': eigenvalue,
            'trace_stat': trace_stat,
            'critical_values': result.cvt,
            'p_value': p_value
        }

    def adf_test(self, series: pd.Series) -> dict:
        """Augmented Dickey-Fuller test for stationarity"""
        result = adfuller(series.dropna(), autolag='AIC')

        return {
            'adf_stat': result[0],
            'p_value': result[1],
            'used_lag': result[2],
            'nobs': result[3],
            'critical_values': result[4]
        }

    def hurst_exponent(self, prices: np.ndarray, max_lag: int = None) -> float:
        """Calculate Hurst exponent (mean reversion indicator)
        H < 0.5: Mean reverting, H > 0.5: Trending
        """
        if max_lag is None:
            max_lag = min(len(prices) // 2, 100)

        lags = range(1, max_lag)
        tau = [np.sqrt(np.std(np.diff(prices[::lag]))) for lag in lags]

        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        hurst = poly[0] * 2

        return hurst

    def z_score(self, spread: pd.Series, window: int = 20) -> pd.Series:
        """Calculate z-score of spread for signal generation"""
        mean = spread.rolling(window).mean()
        std = spread.rolling(window).std()
        z = (spread - mean) / std
        return z

    def analyze_pair(self, df1: pd.DataFrame, df2: pd.DataFrame) -> dict:
        """Comprehensive pair analysis"""
        close1 = df1['close']
        close2 = df2['close']

        # Cointegration test
        joh_result = self.johansen_test(close1, close2)

        # Spread analysis
        spread = close1 - close2
        adf_result = self.adf_test(spread)

        # Hurst exponent
        hurst = self.hurst_exponent(spread.values)

        return {
            'johansen_p_value': joh_result['p_value'],
            'adf_p_value': adf_result['p_value'],
            'hurst': hurst,
            'is_cointegrated': joh_result['p_value'] < 0.05,
            'is_stationary': adf_result['p_value'] < 0.05,
            'is_mean_reverting': hurst < 0.5
        }
