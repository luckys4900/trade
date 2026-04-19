import logging
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    @staticmethod
    def sharpe_ratio(returns: pd.Series, periods_per_year: int = 2190) -> float:
        if len(returns) < 2 or returns.std() == 0:
            return 0.0
        return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))

    @staticmethod
    def max_drawdown(equity_curve: pd.Series) -> Dict:
        eq = equity_curve.values
        if len(eq) < 2:
            return {
                "max_dd_pct": 0,
                "peak_idx": 0,
                "trough_idx": 0,
                "duration_bars": 0,
                "recovery_bars": 0,
            }
        peak = np.maximum.accumulate(eq)
        dd_pct = (peak - eq) / peak * 100
        trough_idx = int(np.argmax(dd_pct))
        peak_idx = int(np.argmax(eq[: trough_idx + 1]))

        duration = trough_idx - peak_idx
        if trough_idx < len(eq) - 1:
            recovery_level = eq[peak_idx]
            recovery_bars = 0
            for j in range(trough_idx + 1, len(eq)):
                recovery_bars += 1
                if eq[j] >= recovery_level:
                    break
        else:
            recovery_bars = len(eq) - trough_idx

        return {
            "max_dd_pct": round(float(dd_pct[trough_idx]), 2),
            "peak_idx": peak_idx,
            "trough_idx": trough_idx,
            "duration_bars": duration,
            "recovery_bars": recovery_bars,
        }

    @staticmethod
    def profit_factor(trades_df: pd.DataFrame) -> float:
        if "net_pnl" not in trades_df.columns or trades_df.empty:
            return 0.0
        pnls = trades_df["net_pnl"].values
        wins = pnls[pnls > 0]
        losses = np.abs(pnls[pnls < 0])
        if len(losses) == 0 or np.sum(losses) == 0:
            return 0.0
        return float(np.sum(wins) / np.sum(losses))

    @staticmethod
    def t_test_pnl(trades_df: pd.DataFrame) -> Dict:
        if "net_pnl" not in trades_df.columns or len(trades_df) < 2:
            return {"t_stat": 0, "p_value": 1.0, "significant": False}
        pnls = trades_df["net_pnl"].values
        if np.std(pnls) == 0:
            return {"t_stat": 0, "p_value": 1.0, "significant": False}
        t_stat, p_val = sp_stats.ttest_1samp(pnls, 0)
        return {
            "t_stat": round(float(t_stat), 3),
            "p_value": round(float(p_val), 4),
            "significant": p_val < 0.05,
        }

    @staticmethod
    def monte_carlo_simulation(trades_df: pd.DataFrame, n_sim: int = 1000) -> Dict:
        if "net_pnl" not in trades_df.columns or len(trades_df) < 5:
            return {
                "pf_distribution": [],
                "actual_pf": 0,
                "percentile_rank": 0,
                "is_significant": False,
            }

        pnls = trades_df["net_pnl"].values.copy()
        actual_pf = PerformanceMetrics.profit_factor(trades_df)

        pf_dist = []
        for _ in range(n_sim):
            shuffled = np.random.permutation(pnls)
            wins = shuffled[shuffled > 0]
            losses = np.abs(shuffled[shuffled < 0])
            if len(losses) > 0 and np.sum(losses) > 0:
                pf_dist.append(float(np.sum(wins) / np.sum(losses)))
            else:
                pf_dist.append(0.0)

        if not pf_dist:
            return {
                "pf_distribution": [],
                "actual_pf": actual_pf,
                "percentile_rank": 0,
                "is_significant": False,
            }

        pf_arr = np.array(pf_dist)
        pct_rank = float(np.mean(pf_arr <= actual_pf) * 100)

        return {
            "pf_distribution": pf_dist,
            "actual_pf": round(actual_pf, 3),
            "percentile_rank": round(pct_rank, 1),
            "is_significant": pct_rank >= 95,
        }

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
