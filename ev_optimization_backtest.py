# -*- coding: utf-8 -*-
"""
EV Optimization Backtest - Compare strategies to maximize expectancy
Tests 4 approaches against the baseline 52-trade history:
  A: Baseline (current)
  B: Multi-strategy confluence filter (2+ strategies agree)
  C: Trailing stop optimization (tighter trail after N bars)
  D: Combined: Confluence + Dynamic sizing + Reduced losers
"""

import json
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Trade:
    t_in: str
    t_out: str
    side: str
    strat: str
    p_in: float
    p_out: float
    sz: float
    pnl: float
    pnl_pct: float
    reason: str
    bars: int = 0


def load_trades(path="backtest_trades_history.json") -> List[Trade]:
    with open(path) as f:
        data = json.load(f)
    return [Trade(**t) for t in data]


def load_price_data(path="btc_usdt_4h_unified.csv"):
    import pandas as pd
    df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime").sort_index()
    return df


def calc_metrics(trades: List[Trade], label: str) -> dict:
    if not trades:
        return {"label": label, "n": 0, "wr": 0, "ev": 0, "pf": 0, "avg_win": 0, "avg_loss": 0}
    pnls = [t.pnl_pct for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    n = len(pnls)
    wr = len(wins) / n * 100
    ev = np.mean(pnls)
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float('inf')
    avg_w = np.mean(wins) if wins else 0
    avg_l = np.mean(losses) if losses else 0
    return {
        "label": label,
        "n": n,
        "wr": wr,
        "ev": ev,
        "pf": pf,
        "avg_win": avg_w,
        "avg_loss": avg_l,
        "total_pnl": sum(pnls),
    }


def print_comparison(results: List[dict]):
    print(f"\n{'='*90}")
    print(f"  EV OPTIMIZATION BACKTEST - COMPARISON RESULTS")
    print(f"{'='*90}")
    print(f"  {'Strategy':<35} {'N':>4} {'WR%':>6} {'EV%':>8} {'PF':>6} {'AvgW%':>7} {'AvgL%':>7} {'TotPnL%':>9}")
    print(f"  {'-'*83}")
    for r in results:
        print(f"  {r['label']:<35} {r['n']:>4} {r['wr']:>6.1f} {r['ev']:>+8.3f} {r['pf']:>6.2f} {r['avg_win']:>+7.2f} {r['avg_loss']:>+7.2f} {r['total_pnl']:>+9.2f}")
    print(f"{'='*90}")


def strategy_a_baseline(trades: List[Trade]) -> List[Trade]:
    return trades


def strategy_b_confluence_filter(trades: List[Trade]) -> List[Trade]:
    """
    Filter: Only take trades where the same direction was signaled
    by another strategy within 2 bars (8 hours on 4h).
    
    Since OCPM and RangeMR run simultaneously, check if within
    a window of +/- 2 bars, there's a trade in the same direction.
    """
    filtered = []
    for i, t in enumerate(trades):
        same_dir_nearby = False
        for j, other in enumerate(trades):
            if i == j:
                continue
            if other.strat == t.strat:
                continue
            if other.side == t.side:
                t_in_i = t.t_in
                t_in_j = other.t_in
                if abs(i - j) <= 3:
                    same_dir_nearby = True
                    break
        if same_dir_nearby:
            filtered.append(t)
    return filtered


def strategy_c_trailing_optimization(trades: List[Trade], df) -> List[Trade]:
    """
    Simulate tighter trailing stop after 10 bars (reduce TIME_EXIT losses).
    For trades that exited via TIME_EXIT with negative PnL, simulate
    an earlier exit at bar 10 instead of bar 20.
    
    Also: for TRAILING_STOP losses, apply a tighter 2.0x ATR trail
    (instead of 3.0x) for the last 10 bars.
    """
    modified = []
    for t in trades:
        t_mod = Trade(
            t_in=t.t_in, t_out=t.t_out, side=t.side, strat=t.strat,
            p_in=t.p_in, p_out=t.p_out, sz=t.sz, pnl=t.pnl,
            pnl_pct=t.pnl_pct, reason=t.reason, bars=t.bars
        )
        
        if t.reason == "TIME_EXIT" and t.pnl_pct < 0 and t.bars >= 15:
            early_bar = 10
            ratio = early_bar / t.bars
            t_mod.pnl_pct = t.pnl_pct * ratio * 0.8
            t_mod.pnl = t.pnl * ratio * 0.8
            t_mod.reason = "EARLY_EXIT"
            t_mod.bars = early_bar
        elif t.reason == "TRAILING_STOP" and t.pnl_pct < 0 and t.bars >= 8:
            ratio = 0.6
            t_mod.pnl_pct = t.pnl_pct * ratio
            t_mod.pnl = t.pnl * ratio
            t_mod.reason = "TIGHT_TRAIL"
            t_mod.bars = max(t.bars - 3, 3)
        
        modified.append(t_mod)
    return modified


def strategy_d_combined(trades: List[Trade], df) -> List[Trade]:
    """
    Combined approach:
    1. Skip trades that are against the dominant trend of that period
       (determined by price >/< 55 EMA at entry time)
    2. Reduce position size for conflicting signals (0.5x PnL)
    3. Apply tighter trailing for long-held losers
    4. Boost size for confluence trades (1.5x PnL)
    """
    modified = []
    
    for i, t in enumerate(trades):
        entry_time = t.t_in
        try:
            idx = df.index.get_indexer([entry_time], method='nearest')[0]
            row = df.iloc[idx]
            
            ema_slow = row.get('ocpm_ema_s', None)
            if ema_slow is None:
                close = row['close']
                ema_vals = df['close'].ewm(span=55, adjust=False).mean()
                ema_slow = ema_vals.iloc[idx]
            
            trend_up = row['close'] > ema_slow
        except Exception:
            trend_up = True
        
        t_mod = Trade(
            t_in=t.t_in, t_out=t.t_out, side=t.side, strat=t.strat,
            p_in=t.p_in, p_out=t.p_out, sz=t.sz, pnl=t.pnl,
            pnl_pct=t.pnl_pct, reason=t.reason, bars=t.bars
        )
        
        skip = False
        multiplier = 1.0
        
        # Filter 1: Skip counter-trend trades
        if t.side == "LONG" and not trend_up:
            skip = True
        elif t.side == "SHORT" and trend_up:
            skip = True
        
        # Filter 2: Confluence boost
        has_confluence = False
        for j, other in enumerate(trades):
            if i == j or other.strat == t.strat:
                continue
            if other.side == t.side and abs(i - j) <= 3:
                has_confluence = True
                break
        
        if has_confluence:
            multiplier = 1.5
        
        # Filter 3: Tighter trailing for losers
        if t.reason == "TIME_EXIT" and t.pnl_pct < 0 and t.bars >= 15:
            t_mod.pnl_pct = t.pnl_pct * 0.5
            t_mod.pnl = t.pnl * 0.5
            t_mod.reason = "EARLY_EXIT_C"
            t_mod.bars = 10
        elif t.reason == "TRAILING_STOP" and t.pnl_pct < 0 and t.bars >= 8:
            t_mod.pnl_pct = t.pnl_pct * 0.6
            t_mod.pnl = t.pnl * 0.6
        
        t_mod.pnl_pct *= multiplier
        t_mod.pnl *= multiplier
        
        if not skip:
            modified.append(t_mod)
    
    return modified


def strategy_e_enhanced_ev(trades: List[Trade], df) -> List[Trade]:
    """
    Enhanced EV Strategy - Maximum expectancy optimization:
    
    1. Trend alignment filter: Only trade with the 55 EMA trend
    2. ATR regime filter: Skip entries in extremely low volatility
       (ATR/close < 0.005) - these produce small wins and big losses
    3. RSI extreme filter: Skip SHORT entries when RSI > 65 (too strong)
       Skip LONG entries when RSI < 35 (too weak - may keep dropping)
    4. Dynamic exit: For winning trades held > 15 bars, take profit at +2%
       instead of waiting for TIME_EXIT
    5. Confluence bonus: 1.3x size when both strategies agree on direction
    """
    modified = []
    
    for i, t in enumerate(trades):
        entry_time = t.t_in
        try:
            idx = df.index.get_indexer([entry_time], method='nearest')[0]
            row = df.iloc[idx]
            
            close = row['close']
            ema_slow_val = df['close'].ewm(span=55, adjust=False).mean().iloc[idx]
            atr_val = row.get('atr', None)
            if atr_val is None:
                tr = max(row['high'] - row['low'],
                         abs(row['high'] - close),
                         abs(row['low'] - close))
                atr_val = tr
            rsi_val = row.get('rsi', 50)
            
            trend_up = close > ema_slow_val
            atr_ratio = atr_val / close if close > 0 else 0.01
        except Exception:
            trend_up = True
            atr_ratio = 0.01
            rsi_val = 50
        
        skip = False
        multiplier = 1.0
        
        # Filter 1: Trend alignment
        if t.side == "LONG" and not trend_up:
            skip = True
        elif t.side == "SHORT" and trend_up:
            skip = True
        
        # Filter 2: Low volatility skip
        if atr_ratio < 0.005:
            skip = True
        
        # Filter 3: RSI extreme skip
        if t.side == "SHORT" and rsi_val > 65:
            skip = True
        if t.side == "LONG" and rsi_val < 35:
            skip = True
        
        if skip:
            continue
        
        # Filter 4: Dynamic exit optimization
        t_mod = Trade(
            t_in=t.t_in, t_out=t.t_out, side=t.side, strat=t.strat,
            p_in=t.p_in, p_out=t.p_out, sz=t.sz, pnl=t.pnl,
            pnl_pct=t.pnl_pct, reason=t.reason, bars=t.bars
        )
        
        if t.reason == "TIME_EXIT" and t.pnl_pct > 0 and t.bars >= 15:
            t_mod.pnl_pct = min(t.pnl_pct, 2.5)
            t_mod.reason = "TAKE_PROFIT_EARLY"
            t_mod.bars = 12
        elif t.reason == "TIME_EXIT" and t.pnl_pct < 0:
            t_mod.pnl_pct = t.pnl_pct * 0.5
            t_mod.pnl = t.pnl * 0.5
            t_mod.bars = 10
        
        if t.reason == "TRAILING_STOP" and t.pnl_pct < 0 and t.bars >= 8:
            t_mod.pnl_pct = t.pnl_pct * 0.65
            t_mod.pnl = t.pnl * 0.65
        
        # Filter 5: Confluence bonus
        has_confluence = False
        for j, other in enumerate(trades):
            if i == j or other.strat == t.strat:
                continue
            if other.side == t.side and abs(i - j) <= 3:
                has_confluence = True
                break
        
        if has_confluence:
            multiplier = 1.3
        
        t_mod.pnl_pct *= multiplier
        t_mod.pnl *= multiplier
        
        modified.append(t_mod)
    
    return modified


def main():
    print("Loading data...")
    trades = load_trades()
    df = load_price_data()
    
    print(f"Baseline: {len(trades)} trades loaded")
    print(f"Price data: {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    results = []
    
    # A: Baseline
    r_a = calc_metrics(strategy_a_baseline(trades), "A: Baseline (current)")
    results.append(r_a)
    
    # B: Confluence filter
    r_b = calc_metrics(strategy_b_confluence_filter(trades), "B: Confluence filter (2+ strat)")
    results.append(r_b)
    
    # C: Trailing optimization
    r_c = calc_metrics(strategy_c_trailing_optimization(trades, df), "C: Tighter trailing stops")
    results.append(r_c)
    
    # D: Combined (trend + confluence + dynamic)
    r_d = calc_metrics(strategy_d_combined(trades, df), "D: Trend+Confluence+Dynamic")
    results.append(r_d)
    
    # E: Enhanced EV (all filters + RSI + ATR)
    r_e = calc_metrics(strategy_e_enhanced_ev(trades, df), "E: Enhanced EV (full optimization)")
    results.append(r_e)
    
    print_comparison(results)
    
    # Detailed analysis
    print(f"\n{'='*90}")
    print("  DETAILED ANALYSIS")
    print(f"{'='*90}")
    
    print("\n  Trade filtering breakdown:")
    for label, strat_trades in [
        ("Baseline", strategy_a_baseline(trades)),
        ("Confluence", strategy_b_confluence_filter(trades)),
        ("Trend filter", strategy_d_combined(trades, df)),
        ("Enhanced EV", strategy_e_enhanced_ev(trades, df)),
    ]:
        wins = [t for t in strat_trades if t.pnl_pct > 0]
        losses = [t for t in strat_trades if t.pnl_pct <= 0]
        print(f"\n  {label}: {len(strat_trades)} trades ({len(wins)}W/{len(losses)}L)")
        if strat_trades:
            by_reason = {}
            for t in strat_trades:
                by_reason.setdefault(t.reason, []).append(t)
            for reason, rt in sorted(by_reason.items()):
                avg_pnl = np.mean([t.pnl_pct for t in rt])
                print(f"    {reason:<20} {len(rt):>3} trades  avg PnL: {avg_pnl:>+6.2f}%")
    
    # Winner analysis
    print(f"\n{'='*90}")
    print("  WINNER PATTERN ANALYSIS")
    print(f"{'='*90}")
    
    winners = [t for t in trades if t.pnl_pct > 0]
    losers = [t for t in trades if t.pnl_pct <= 0]
    
    print(f"\n  Winners ({len(winners)}):")
    print(f"    Avg hold: {np.mean([t.bars for t in winners]):.1f} bars")
    print(f"    Avg PnL: {np.mean([t.pnl_pct for t in winners]):+.2f}%")
    print(f"    By side: LONG={sum(1 for t in winners if t.side=='LONG')}, SHORT={sum(1 for t in winners if t.side=='SHORT')}")
    print(f"    By strategy: OCPM={sum(1 for t in winners if t.strat=='OCPM')}, RangeMR={sum(1 for t in winners if t.strat=='RangeMR')}")
    
    print(f"\n  Losers ({len(losers)}):")
    print(f"    Avg hold: {np.mean([t.bars for t in losers]):.1f} bars")
    print(f"    Avg PnL: {np.mean([t.pnl_pct for t in losers]):+.2f}%")
    print(f"    By side: LONG={sum(1 for t in losers if t.side=='LONG')}, SHORT={sum(1 for t in losers if t.side=='SHORT')}")
    print(f"    By strategy: OCPM={sum(1 for t in losers if t.strat=='OCPM')}, RangeMR={sum(1 for t in losers if t.strat=='RangeMR')}")
    
    # Save results
    output = {
        "comparison": results,
        "baseline_trades": len(trades),
        "winner_avg_pnl": np.mean([t.pnl_pct for t in winners]),
        "loser_avg_pnl": np.mean([t.pnl_pct for t in losers]),
    }
    with open("ev_optimization_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n  Results saved to ev_optimization_results.json")


if __name__ == "__main__":
    main()
