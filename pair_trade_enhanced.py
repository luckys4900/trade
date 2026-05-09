"""
BTC-ETH Pair Trading Strategy - ENHANCED VERSION
=================================================
Cointegration + Dynamic Hedging + Regime Detection + Multi-Asset Analysis

IMPROVEMENTS:
1. Dynamic Hedge Ratio - Monthly updating vs Fixed
2. Regime Detection AI - HIGH_CORR, NORMAL, LOW_CORR
3. Multi-Asset Testing - BTC/ETH, BTC/SOL, ETH/SOL, BTC/XRP
4. Spread Trading - Alternative to cointegration
5. Composite Signals - Z-score + Spread + Correlation
6. Expectancy Optimization - Target p < 0.05, EV > +0.15%
"""

import pathlib
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from statsmodels.tsa.stattools import coint, adfuller
from scipy import stats as scipy_stats


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class PairConfig:
    lookback: int = 100
    z_entry: float = 2.0
    z_exit: float = 0.0
    z_stop: float = 3.5
    hedge_ratio_method: str = "ols"
    risk_per_trade: float = 0.01
    time_stop_bars: int = 40
    taker_fee: float = 0.00035
    slippage: float = 0.001


# ============================================================================
# IMPROVEMENT 1: DYNAMIC HEDGE RATIO TRACKING
# ============================================================================

class DynamicHedgeRatioTracker:
    """Tracks monthly updating hedge ratio vs locked ratio"""

    def __init__(self, initial_df: pd.DataFrame, initial_hr: float, lookback: int = 100):
        self.lookback = lookback
        self.initial_hr = initial_hr
        self.history = []
        self._compute_history(initial_df)

    def _compute_history(self, df):
        """Compute hedge ratio for each month"""
        df = df.copy()
        df['yearmonth'] = df.index.to_period('M')

        for ym in df['yearmonth'].unique():
            month_df = df[df['yearmonth'] == ym]
            if len(month_df) >= self.lookback:
                X = np.column_stack([np.ones(len(month_df)), month_df['eth_close'].values])
                beta = np.linalg.lstsq(X, month_df['btc_close'].values, rcond=None)[0]
                hr = beta[1]
                self.history.append({
                    'yearmonth': ym,
                    'hedge_ratio': hr,
                    'n_bars': len(month_df)
                })

    def get_hr_at_bar(self, bar_idx: int, df: pd.DataFrame, is_dynamic: bool = True) -> float:
        """Get hedge ratio at specific bar"""
        if not is_dynamic:
            return self.initial_hr

        current_date = df.index[bar_idx]
        current_ym = current_date.to_period('M')

        matching = [h for h in self.history if h['yearmonth'] == current_ym]
        if matching:
            return matching[0]['hedge_ratio']
        return self.initial_hr


# ============================================================================
# IMPROVEMENT 2: REGIME DETECTION
# ============================================================================

class RegimeDetector:
    """Detects correlation regime: HIGH_CORR (>0.75), NORMAL (0.5-0.75), LOW_CORR (<0.5)"""

    def __init__(self, lookback: int = 100):
        self.lookback = lookback
        self.regimes = []

    def detect(self, df: pd.DataFrame, col1: str, col2: str) -> str:
        """Detect regime for last bar"""
        if len(df) < self.lookback:
            return 'NORMAL'

        corr = df[col1].iloc[-self.lookback:].corr(df[col2].iloc[-self.lookback:])

        if corr > 0.75:
            return 'HIGH_CORR'
        elif corr > 0.5:
            return 'NORMAL'
        else:
            return 'LOW_CORR'

    def get_action(self, regime: str) -> Dict:
        """Get trading action for regime"""
        actions = {
            'HIGH_CORR': {'leverage': 0.5, 'z_entry': 1.5, 'reason': 'Low spread variance'},
            'NORMAL': {'leverage': 1.0, 'z_entry': 2.0, 'reason': 'Standard regime'},
            'LOW_CORR': {'leverage': 1.5, 'z_entry': 2.5, 'reason': 'High spread variance, tighter entry'},
        }
        return actions.get(regime, actions['NORMAL'])


# ============================================================================
# IMPROVEMENT 3: MULTI-ASSET ANALYZER
# ============================================================================

class MultiAssetAnalyzer:
    """Analyzes correlation stability across multiple pairs"""

    @staticmethod
    def load_multi_data(base_path: pathlib.Path, pair_names: List[Tuple[str, str]]) -> Dict[str, pd.DataFrame]:
        """Load multiple currency pairs"""
        data = {}
        for asset1, asset2 in pair_names:
            try:
                p1_path = base_path / f"{asset1}_usdt_4h_unified.csv"
                p2_path = base_path / f"data/{asset2}_usdt_4h.csv"

                if not p1_path.exists() or not p2_path.exists():
                    continue

                df1 = pd.read_csv(p1_path, parse_dates=['datetime'], index_col='datetime').sort_index()
                df2 = pd.read_csv(p2_path, parse_dates=['datetime'], index_col='datetime').sort_index()

                common = df1.index.intersection(df2.index)
                df1 = df1.loc[common]
                df2 = df2.loc[common]

                df1.columns = [f"{asset1.lower()}_{c}" for c in df1.columns]
                df2.columns = [f"{asset2.lower()}_{c}" for c in df2.columns]

                merged = pd.concat([df1, df2], axis=1).dropna()
                pair_key = f"{asset1}/{asset2}"
                data[pair_key] = merged
            except:
                pass

        return data

    @staticmethod
    def compute_correlation_stability(df: pd.DataFrame, col1: str, col2: str,
                                     lookback: int = 100, n_periods: int = 12) -> Dict:
        """Compute correlation stability score"""
        if len(df) < lookback * 2:
            return {'stability_score': 0, 'mean_corr': 0, 'std_corr': 0, 'n_windows': 0}

        corrs = []
        for i in range(lookback, len(df), lookback // 4):
            window = df.iloc[i-lookback:i]
            c = window[col1].corr(window[col2])
            if not np.isnan(c):
                corrs.append(c)

        if not corrs:
            return {'stability_score': 0, 'mean_corr': 0, 'std_corr': 0, 'n_windows': 0}

        mean_c = np.mean(corrs)
        std_c = np.std(corrs)
        stability_score = 1.0 / (1.0 + std_c)  # Higher is more stable

        return {
            'stability_score': round(stability_score, 3),
            'mean_corr': round(mean_c, 3),
            'std_corr': round(std_c, 3),
            'n_windows': len(corrs)
        }


# ============================================================================
# IMPROVEMENT 4: SPREAD TRADING SYSTEM
# ============================================================================

class SpreadTradingSignal:
    """Spread-based trading without relying on cointegration"""

    def __init__(self, lookback: int = 100):
        self.lookback = lookback

    def compute_spread_stats(self, btc_close: np.ndarray, eth_close: np.ndarray,
                            hedge_ratio: float, lookback: int = None) -> Dict:
        """Compute spread statistics"""
        if lookback is None:
            lookback = self.lookback

        spread = btc_close - hedge_ratio * eth_close

        if len(spread) < lookback:
            return {
                'spread_mean': 0, 'spread_std': 0, 'spread_z': 0,
                'spread_direction': 0
            }

        recent_window = spread[-lookback:]
        mean = np.mean(recent_window)
        std = np.std(recent_window)
        current = spread[-1]

        z_score = (current - mean) / std if std > 0 else 0
        direction = 1 if current > mean else -1

        return {
            'spread_mean': round(mean, 2),
            'spread_std': round(std, 2),
            'spread_z': round(z_score, 2),
            'spread_direction': direction,
            'spread_current': round(current, 2)
        }


# ============================================================================
# IMPROVEMENT 5: COMPOSITE SIGNAL INTEGRATOR
# ============================================================================

class CompositeSignalIntegrator:
    """Combines Z-score, Spread, and Correlation signals"""

    @staticmethod
    def integrate_signals(z_score: float, spread_z: float, correlation: float,
                         regime: str) -> Dict:
        """Integrate multiple signals for final decision"""

        # Signal strength from each component
        z_strength = min(abs(z_score) / 2.0, 1.0)  # 0-1 scale
        spread_strength = min(abs(spread_z) / 2.0, 1.0)
        corr_strength = correlation if correlation > 0.5 else 1 - correlation  # Closer to extreme (high/low)

        # All signals agree?
        z_extreme = abs(z_score) > 2.0
        spread_extreme = abs(spread_z) > 2.0

        all_agree = z_extreme and spread_extreme

        # Composite score (weighted)
        weights = {'z': 0.4, 'spread': 0.4, 'corr': 0.2}
        composite = (z_strength * weights['z'] +
                    spread_strength * weights['spread'] +
                    corr_strength * weights['corr'])

        return {
            'z_extreme': z_extreme,
            'spread_extreme': spread_extreme,
            'all_signals_agree': all_agree,
            'composite_score': round(composite, 3),
            'confidence': 'HIGH' if all_agree else 'MEDIUM' if composite > 0.6 else 'LOW'
        }


# ============================================================================
# CORE BACKTEST ENGINE (UNCHANGED)
# ============================================================================

def load_pair_data(btc_path, eth_path):
    btc = pd.read_csv(
        btc_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()
    eth = pd.read_csv(
        eth_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()

    common = btc.index.intersection(eth.index)
    btc = btc.loc[common].copy()
    eth = eth.loc[common].copy()

    btc.columns = [f"btc_{c}" if c not in ["datetime"] else c for c in btc.columns]
    eth.columns = [f"eth_{c}" if c not in ["datetime"] else c for c in eth.columns]

    df = pd.concat([btc, eth], axis=1).dropna()
    return df


def cointegration_test(df):
    btc_close = df["btc_close"]
    eth_close = df["eth_close"]

    score, pvalue, critical = coint(btc_close, eth_close)
    adf_result = adfuller(btc_close / eth_close)

    X = np.column_stack([np.ones(len(eth_close)), eth_close.values])
    beta = np.linalg.lstsq(X, btc_close.values, rcond=None)[0]
    hedge_ratio = beta[1]
    spread = btc_close.values - hedge_ratio * eth_close.values

    spread_series = pd.Series(spread, index=df.index)
    half_life = (
        -np.log(2) / adfuller(spread_series.dropna())[0]
        if adfuller(spread_series.dropna())[0] < 0
        else 999
    )

    return {
        "coint_stat": round(score, 4),
        "coint_pvalue": round(pvalue, 6),
        "coint_critical": {
            "1%": round(critical[0], 4),
            "5%": round(critical[1], 4),
            "10%": round(critical[2], 4),
        },
        "adf_stat": round(adf_result[0], 4),
        "adf_pvalue": round(adf_result[1], 6),
        "hedge_ratio": round(hedge_ratio, 6),
        "half_life_bars": round(half_life, 1) if half_life < 999 else "inf",
        "spread_mean": round(spread_series.mean(), 2),
        "spread_std": round(spread_series.std(), 2),
        "is_cointegrated": pvalue < 0.05,
    }


class PairBacktest:
    def __init__(self, cfg: PairConfig, start_balance: float = 10_000.0, use_dynamic_hr: bool = False, use_regime: bool = False, use_composite: bool = False):
        self.cfg = cfg
        self.balance = start_balance
        self.start_balance = start_balance
        self.trades: List[Dict] = []
        self.bar_idx = 0
        self.in_pos = False
        self.pos_direction = 0
        self.entry_bar = 0
        self.entry_zscore = 0.0
        self.btc_size = 0.0
        self.eth_size = 0.0
        self.btc_entry_px = 0.0
        self.eth_entry_px = 0.0
        self.hedge_ratio = 0.0
        self.use_dynamic_hr = use_dynamic_hr
        self.use_regime = use_regime
        self.use_composite = use_composite
        self.regime_detector = RegimeDetector() if use_regime else None
        self.spread_signal = SpreadTradingSignal() if use_composite else None

    def _fee(self, notional):
        return notional * self.cfg.taker_fee

    def _apply_slip(self, px, side):
        if side == "buy":
            return px * (1 + self.cfg.slippage)
        return px * (1 - self.cfg.slippage)

    def _open(self, row, z_score, hedge_ratio, direction):
        btc_px = self._apply_slip(row["btc_close"], "sell" if direction > 0 else "buy")
        eth_px = self._apply_slip(row["eth_close"], "buy" if direction > 0 else "sell")

        risk_budget = self.balance * self.cfg.risk_per_trade

        btc_notional = risk_budget / 2
        eth_notional = btc_notional * hedge_ratio

        self.btc_size = btc_notional / btc_px
        self.eth_size = eth_notional / eth_px

        self.balance -= self._fee(btc_notional)
        self.balance -= self._fee(eth_notional)

        self.in_pos = True
        self.pos_direction = direction
        self.entry_bar = self.bar_idx
        self.entry_zscore = z_score
        self.btc_entry_px = btc_px
        self.eth_entry_px = eth_px
        self.hedge_ratio = hedge_ratio

    def _close(self, row, reason):
        if not self.in_pos:
            return

        if self.pos_direction > 0:
            btc_fill = self._apply_slip(row["btc_close"], "buy")
            eth_fill = self._apply_slip(row["eth_close"], "sell")
            btc_pnl = (self.btc_entry_px - btc_fill) * self.btc_size
            eth_pnl = (eth_fill - self.eth_entry_px) * self.eth_size
        else:
            btc_fill = self._apply_slip(row["btc_close"], "sell")
            eth_fill = self._apply_slip(row["eth_close"], "buy")
            btc_pnl = (btc_fill - self.btc_entry_px) * self.btc_size
            eth_pnl = (self.eth_entry_px - eth_fill) * self.eth_size

        self.balance -= self._fee(abs(self.btc_size * btc_fill))
        self.balance -= self._fee(abs(self.eth_size * eth_fill))

        total_pnl = btc_pnl + eth_pnl

        self.trades.append(
            {
                "entry_bar": self.entry_bar,
                "exit_bar": self.bar_idx,
                "direction": "SHORT_BTC_LONG_ETH"
                if self.pos_direction > 0
                else "LONG_BTC_SHORT_ETH",
                "entry_z": round(self.entry_zscore, 2),
                "pnl": round(total_pnl, 2),
                "btc_pnl": round(btc_pnl, 2),
                "eth_pnl": round(eth_pnl, 2),
                "reason": reason,
                "balance_after": round(self.balance, 2),
            }
        )
        self.in_pos = False

    def run(self, df, hedge_ratio, hr_tracker=None):
        btc_c = df["btc_close"].values
        eth_c = df["eth_close"].values
        spread = btc_c - hedge_ratio * eth_c
        spread_series = pd.Series(spread, index=df.index)

        z_scores = np.full(len(df), np.nan)

        for i in range(self.cfg.lookback, len(df)):
            window = spread_series.iloc[i - self.cfg.lookback : i]
            mean = window.mean()
            std = window.std()
            if std > 0:
                z_scores[i] = (spread[i] - mean) / std

        z_series = pd.Series(z_scores, index=df.index)

        for i in range(self.cfg.lookback + 1, len(df)):
            self.bar_idx = i
            z = z_series.iloc[i]
            if np.isnan(z):
                continue

            row = df.iloc[i]

            # Get current hedge ratio (dynamic or fixed)
            current_hr = hr_tracker.get_hr_at_bar(i, df, self.use_dynamic_hr) if hr_tracker else hedge_ratio

            # Regime detection
            entry_z = self.cfg.z_entry
            if self.use_regime:
                regime = self.regime_detector.detect(df, 'btc_close', 'eth_close')
                action = self.regime_detector.get_action(regime)
                entry_z = action['z_entry']

            if self.in_pos:
                held = i - self.entry_bar

                if self.pos_direction > 0 and z <= self.cfg.z_exit:
                    self._close(row, "Z_REVERT")
                    continue
                elif self.pos_direction < 0 and z >= self.cfg.z_exit:
                    self._close(row, "Z_REVERT")
                    continue

                if abs(z) >= self.cfg.z_stop:
                    self._close(row, "Z_STOP")
                    continue

                if held >= self.cfg.time_stop_bars:
                    self._close(row, "TIME_STOP")
                    continue

            if self.in_pos:
                continue

            if z >= entry_z:
                self._open(row, z, current_hr, 1)
            elif z <= -entry_z:
                self._open(row, z, current_hr, -1)


def calc_stats(trades, start_bal):
    if not trades:
        return {
            "n": 0,
            "pnl": 0,
            "wr": 0,
            "pf": 0,
            "avg": 0,
            "max_dd": 0,
            "max_dd_pct": 0,
            "final": start_bal,
            "reasons": {},
            "sharpe": 0,
            "t_stat": 0,
            "significant": False,
            "p_value": 1.0,
            "ev_pct": 0,
        }

    pnls = [t["pnl"] for t in trades]
    n = len(trades)
    total_pnl = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    wr = len(wins) / n * 100
    pf = sum(wins) / sum(losses) if losses else 0

    equity = np.cumsum([0] + pnls) + start_bal
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = dd.max()
    max_dd_pct = max_dd / peak.max() * 100 if peak.max() > 0 else 0

    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1

    pnl_arr = np.array(pnls)

    # T-test for significance
    t_stat = 0
    p_value = 1.0
    if len(pnl_arr) > 1 and pnl_arr.std() > 0:
        t_stat = float(pnl_arr.mean() / (pnl_arr.std() / np.sqrt(len(pnl_arr))))
        # Two-tailed t-test p-value
        p_value = 2 * (1 - scipy_stats.t.cdf(abs(t_stat), len(pnl_arr) - 1))

    # Expectancy as percentage of starting balance
    ev_pct = (total_pnl / start_bal) * 100

    daily_chunks = np.array_split(pnls, max(1, len(pnls) // 6))
    daily_sums = [sum(c) for c in daily_chunks]
    darr = np.array(daily_sums)
    sharpe = (
        darr.mean() / darr.std() * np.sqrt(365)
        if len(darr) > 1 and darr.std() > 0
        else 0
    )

    return {
        "n": n,
        "pnl": round(total_pnl, 2),
        "wr": round(wr, 1),
        "pf": round(pf, 3),
        "avg": round(total_pnl / n, 2),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "final": round(start_bal + total_pnl, 2),
        "reasons": reasons,
        "t_stat": round(t_stat, 3),
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
        "ev_pct": round(ev_pct, 3),
    }


def print_stats(label, s):
    print(
        "  {:<50} PnL={:>10,.2f} | EV%={:>6.3f}% | N={:>3} | WR={:>5.1f}% | "
        "p={:.4f} | Sig={:<5}".format(
            label,
            s["pnl"],
            s["ev_pct"],
            s["n"],
            s["wr"],
            s["p_value"],
            "YES" if s["significant"] else "NO"
        )
    )


# ============================================================================
# MAIN ANALYSIS
# ============================================================================

def main():
    base = pathlib.Path(__file__).parent
    btc_path = base / "btc_usdt_4h_unified.csv"
    eth_path = base / "data" / "eth_usdt_4h.csv"

    print("="*150)
    print("PAIR TRADING ENHANCEMENT ANALYSIS")
    print("="*150)
    print()

    print("Loading pair data...")
    df = load_pair_data(btc_path, eth_path)
    print("Combined: {} bars ({} ~ {})".format(len(df), df.index[0], df.index[-1]))
    print()

    # Split data
    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()

    print("="*150)
    print("BASELINE ANALYSIS")
    print("="*150)

    baseline_coint = cointegration_test(df)
    print("Cointegration: p-value = {:.6f}, HR = {:.6f}".format(
        baseline_coint["coint_pvalue"], baseline_coint["hedge_ratio"]
    ))
    hr_locked = baseline_coint["hedge_ratio"]
    print()

    start_bal = 10_000.0
    cfg_default = PairConfig()

    # Test 1: Fixed HR vs Dynamic HR
    print("="*150)
    print("IMPROVEMENT 1: DYNAMIC HEDGE RATIO TRACKING")
    print("="*150)

    hr_tracker = DynamicHedgeRatioTracker(df_oos, hr_locked, lookback=100)

    # Fixed HR
    bt_fixed = PairBacktest(cfg_default, start_bal, use_dynamic_hr=False)
    bt_fixed.run(df_oos, hr_locked, hr_tracker)
    stats_fixed = calc_stats(bt_fixed.trades, start_bal)

    # Dynamic HR
    bt_dynamic = PairBacktest(cfg_default, start_bal, use_dynamic_hr=True)
    bt_dynamic.run(df_oos, hr_locked, hr_tracker)
    stats_dynamic = calc_stats(bt_dynamic.trades, start_bal)

    print_stats("Fixed HR (baseline)", stats_fixed)
    print_stats("Dynamic HR (monthly update)", stats_dynamic)

    improvement_pnl = stats_dynamic["pnl"] - stats_fixed["pnl"]
    improvement_pct = (improvement_pnl / abs(stats_fixed["pnl"])) * 100 if stats_fixed["pnl"] != 0 else 0
    print("  Improvement: PnL Delta = {:.2f} ({:.1f}%)".format(improvement_pnl, improvement_pct))
    print()

    # Test 2: Regime Detection
    print("="*150)
    print("IMPROVEMENT 2: REGIME DETECTION AI")
    print("="*150)

    bt_regime = PairBacktest(cfg_default, start_bal, use_regime=True)
    bt_regime.run(df_oos, hr_locked, hr_tracker)
    stats_regime = calc_stats(bt_regime.trades, start_bal)

    print_stats("Regime Detection", stats_regime)
    print("  Regime Actions: HIGH_CORR (Z=1.5), NORMAL (Z=2.0), LOW_CORR (Z=2.5)")
    print()

    # Test 3: Combined (Dynamic HR + Regime)
    print("="*150)
    print("IMPROVEMENT 1+2: DYNAMIC HR + REGIME DETECTION")
    print("="*150)

    bt_combined = PairBacktest(cfg_default, start_bal, use_dynamic_hr=True, use_regime=True)
    bt_combined.run(df_oos, hr_locked, hr_tracker)
    stats_combined = calc_stats(bt_combined.trades, start_bal)

    print_stats("Combined (Dynamic HR + Regime)", stats_combined)
    improvement_combined = stats_combined["pnl"] - stats_fixed["pnl"]
    print("  Improvement vs Fixed HR: {:.2f} PnL ({:.1f}%)".format(
        improvement_combined, (improvement_combined / abs(stats_fixed["pnl"])) * 100 if stats_fixed["pnl"] != 0 else 0
    ))
    print()

    # Test 4: Multi-Asset Analysis
    print("="*150)
    print("IMPROVEMENT 3: MULTI-ASSET CORRELATION STABILITY ANALYSIS")
    print("="*150)

    analyzer = MultiAssetAnalyzer()
    pair_names = [
        ("btc", "eth"),
        ("btc", "sol"),
        ("eth", "sol"),
        ("btc", "xrp"),
    ]

    multi_data = analyzer.load_multi_data(base, pair_names)

    stability_scores = {}
    for pair_key, pair_df in multi_data.items():
        col1, col2 = pair_key.lower().split('/')
        col1 += '_close'
        col2 += '_close'

        stability = analyzer.compute_correlation_stability(pair_df, col1, col2, lookback=100)
        stability_scores[pair_key] = stability

        print("Pair: {:<12} | Stability Score: {:.3f} | Mean Corr: {:.3f} (+/- {:.3f}) | Windows: {}".format(
            pair_key,
            stability['stability_score'],
            stability['mean_corr'],
            stability['std_corr'],
            stability['n_windows']
        ))

    best_pair = max(stability_scores.items(), key=lambda x: x[1]['stability_score']) if stability_scores else None
    if best_pair:
        print("\n  BEST PAIR (Most stable correlation): {}".format(best_pair[0]))
        print("  Stability Score: {:.3f} | Mean Corr: {:.3f}".format(
            best_pair[1]['stability_score'], best_pair[1]['mean_corr']
        ))
    print()

    # Test 5: Spread-based Trading
    print("="*150)
    print("IMPROVEMENT 4: SPREAD TRADING (NO COINTEGRATION DEPENDENCY)")
    print("="*150)

    spread_signal = SpreadTradingSignal(lookback=100)
    spread_stats = spread_signal.compute_spread_stats(
        df_oos["btc_close"].values,
        df_oos["eth_close"].values,
        hr_locked
    )
    print("Latest Spread Stats:")
    for k, v in spread_stats.items():
        print("  {}: {}".format(k, v))
    print("\nSpread trading approach: Use spread value directly without cointegration test")
    print("Advantage: Works even when correlation changes (e.g., regime shifts)")
    print()

    # Test 6: Composite Signals
    print("="*150)
    print("IMPROVEMENT 5: COMPOSITE SIGNAL INTEGRATION")
    print("="*150)

    # Example signals
    example_z = 2.2
    example_spread_z = 2.1
    example_corr = 0.72
    example_regime = 'NORMAL'

    composite = CompositeSignalIntegrator.integrate_signals(
        example_z, example_spread_z, example_corr, example_regime
    )

    print("Example Signal Integration:")
    print("  Z-Score: {:.2f} | Spread Z: {:.2f} | Correlation: {:.2f} | Regime: {}".format(
        example_z, example_spread_z, example_corr, example_regime
    ))
    print("  Results:")
    for k, v in composite.items():
        print("    {}: {}".format(k, v))
    print("\nSignal Quality Interpretation:")
    print("  HIGH confidence: All signals agree (Z > 2.0 AND Spread Z > 2.0)")
    print("  MEDIUM confidence: Composite score > 0.6")
    print("  LOW confidence: Composite score <= 0.6")
    print()

    # SUMMARY
    print("="*150)
    print("FINAL EXPECTANCY COMPARISON")
    print("="*150)
    print()

    results_summary = [
        ("Baseline (Fixed HR)", stats_fixed),
        ("Dynamic HR", stats_dynamic),
        ("Regime Detection", stats_regime),
        ("Dynamic HR + Regime", stats_combined),
    ]

    print("Rank | Strategy              | PnL       | EV (%)    | N  | WR %  | p-value | Significant")
    print("-"*95)
    for i, (name, s) in enumerate(sorted(results_summary, key=lambda x: x[1]["pnl"], reverse=True), 1):
        sig = "YES" if s["significant"] else "NO"
        print("{:<4} | {:<21} | {:<9,.2f} | {:<9.3f} | {:<3} | {:<5.1f} | {:.4f} | {}".format(
            i, name, s["pnl"], s["ev_pct"], s["n"], s["wr"], s["p_value"], sig
        ))

    print()
    print("TARGET METRICS:")
    print("  EV (Expectancy) > +0.15%")
    print("  p-value < 0.05 (statistically significant)")
    print()

    best_result = max(results_summary, key=lambda x: x[1]["pnl"])
    print("BEST PERFORMER: {}".format(best_result[0]))
    print("  PnL: {:.2f} | EV: {:.3f}% | p-value: {:.4f}".format(
        best_result[1]["pnl"], best_result[1]["ev_pct"], best_result[1]["p_value"]
    ))

    if best_result[1]["ev_pct"] > 0.15 and best_result[1]["p_value"] < 0.05:
        print("\n>>> TARGET ACHIEVED <<<")
    else:
        target_1 = "MISS" if best_result[1]["ev_pct"] <= 0.15 else "PASS"
        target_2 = "MISS" if best_result[1]["p_value"] >= 0.05 else "PASS"
        print("\n>>> TARGET NOT ACHIEVED <<<")
        print("  EV > 0.15%: {}".format(target_1))
        print("  p < 0.05: {}".format(target_2))


if __name__ == "__main__":
    main()
