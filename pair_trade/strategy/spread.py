import logging
from typing import Dict

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

logger = logging.getLogger(__name__)


class SpreadCalculator:
    def __init__(self, lookback_window: int = 120):
        self.lookback = lookback_window

    def calculate_zscore(self, spread_series: pd.Series) -> pd.Series:
        rolling_mean = spread_series.rolling(
            self.lookback, min_periods=self.lookback
        ).mean()
        rolling_std = spread_series.rolling(
            self.lookback, min_periods=self.lookback
        ).std()
        zscore = (spread_series - rolling_mean) / rolling_std.replace(0, np.nan)
        return zscore.shift(1)

    @staticmethod
    def calculate_halflife(spread_series: pd.Series) -> float:
        spread = spread_series.dropna()
        if len(spread) < 10:
            return np.nan
        spread_lag = spread.shift(1).dropna()
        delta = spread.diff().dropna()
        common = spread_lag.index.intersection(delta.index)
        if len(common) < 10:
            return np.nan
        y = delta.loc[common].values
        x = spread_lag.loc[common].values
        x = np.column_stack([x, np.ones(len(x))])
        try:
            beta = np.linalg.lstsq(x, y, rcond=None)[0]
            lam = beta[0]
            if lam >= 0:
                return np.nan
            halflife = -np.log(2) / np.log(1 + lam)
            return max(0.0, halflife)
        except Exception:
            return np.nan

    @staticmethod
    def hurst_exponent(series: pd.Series, max_lag: int = 100) -> float:
        vals = series.dropna().values
        if len(vals) < max_lag * 2:
            return np.nan
        lags = range(2, min(max_lag, len(vals) // 2))
        rs_values = []
        for lag in lags:
            segs = [vals[i : i + lag] for i in range(0, len(vals) - lag, lag)]
            if not segs:
                continue
            rs_list = []
            for seg in segs:
                if len(seg) < 2:
                    continue
                mean_seg = np.mean(seg)
                cumdev = np.cumsum(seg - mean_seg)
                r = np.max(cumdev) - np.min(cumdev)
                s = np.std(seg, ddof=1)
                if s > 0:
                    rs_list.append(r / s)
            if rs_list:
                rs_values.append((np.log(lag), np.log(np.mean(rs_list))))

        if len(rs_values) < 5:
            return np.nan
        x = np.array([v[0] for v in rs_values])
        y = np.array([v[1] for v in rs_values])
        x = np.column_stack([x, np.ones(len(x))])
        try:
            beta = np.linalg.lstsq(x, y, rcond=None)[0]
            return float(beta[0])
        except Exception:
            return np.nan

    def get_spread_stats(self, spread_series: pd.Series) -> Dict[str, float]:
        spread = spread_series.dropna()
        hl = self.calculate_halflife(spread)
        hurst = self.hurst_exponent(spread)
        try:
            adf_result = adfuller(spread, maxlag=20, regression="c")
            adf_pvalue = float(adf_result[1])
        except Exception:
            adf_pvalue = np.nan

        return {
            "mean": float(spread.mean()),
            "std": float(spread.std()),
            "halflife_bars": hl,
            "halflife_hours": hl * 4 if not np.isnan(hl) else np.nan,
            "adf_pvalue": adf_pvalue,
            "hurst_exponent": hurst,
        }
