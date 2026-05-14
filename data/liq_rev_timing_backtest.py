#!/usr/bin/env python3
"""
Liquidation Reversal - Entry Timing Comparison Backtest (Optimized)
===================================================================
Tests 3 entry timing patterns for LIQ-REV strategy:

Pattern 1: 1-Bar Delayed Entry
Pattern 2: Reversal Confirmation Entry
Pattern 3: High-Vol After Reversal Entry

Grid: 3 x 4 x 4 x 3 x 3 = 432 per pattern = 1296 total
"""

import json
import itertools
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ----------------------------------------------
# Configuration
# ----------------------------------------------
PRICE_PATH = Path(r"C:\Users\user\Desktop\cursor\trade\data\btc_price_4h_cache.csv")
OUTPUT_PATH = Path(r"C:\Users\user\Desktop\cursor\trade\data\liq_rev_timing_results.json")

RSI_PERIOD = 14
ATR_PERIOD = 14
FEE_ONE_WAY = 0.00035
SLIPPAGE_ONE_WAY = 0.0003
INITIAL_CAPITAL = 190.0
RISK_PER_TRADE = 0.015
LEVERAGE = 1
IS_RATIO = 0.70

CASCADE_THRESHOLDS = [0.02, 0.025, 0.03]
SL_PCTS = [0.005, 0.01, 0.015, 0.02]
TP_PCTS = [0.01, 0.015, 0.02, 0.03]
RSI_THRESHOLDS = [(30, 70), (35, 65), (40, 60)]
MAX_HOLD_BARS = [6, 8, 12]
PATTERNS = ["delayed_1bar", "reversal_confirm", "highvol_reversal"]


# ----------------------------------------------
# Data Loading
# ----------------------------------------------
def load_price_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ----------------------------------------------
# Pre-compute indicators (done once)
# ----------------------------------------------
def precompute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-compute all indicators needed by any pattern."""
    df = df.copy()
    df["pct_change"] = df["close"].pct_change()
    df["is_bullish"] = df["close"] > df["open"]
    df["is_bearish"] = df["close"] < df["open"]

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.ewm(alpha=1.0 / RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

    # ATR
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1.0 / ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    df["atr_avg"] = df["atr"].rolling(window=50, min_periods=30).mean()

    return df


# ----------------------------------------------
# Signal Generation (vectorized)
# ----------------------------------------------
def generate_signals(df: pd.DataFrame, pattern: str, cascade_threshold: float,
                     rsi_long_threshold: int, rsi_short_threshold: int) -> tuple:
    """
    Generate entry signals as boolean arrays (signal_long, signal_short).
    Returns numpy boolean arrays for fast backtesting.
    """
    pct = df["pct_change"].values
    rsi = df["rsi"].values
    n = len(df)

    # Cascade detection (vectorized)
    cascade_long = pct <= -cascade_threshold   # sharp drop -> LONG bias
    cascade_short = pct >= cascade_threshold    # sharp rise -> SHORT bias

    if pattern == "delayed_1bar":
        # Pattern 1: Enter on NEXT bar after cascade, with RSI filter on entry bar
        signal_long = np.zeros(n, dtype=bool)
        signal_short = np.zeros(n, dtype=bool)

        # Shift cascade signals by 1 bar
        cascade_long_next = np.roll(cascade_long, 1)
        cascade_short_next = np.roll(cascade_short, 1)
        cascade_long_next[0] = False
        cascade_short_next[0] = False

        # Entry on next bar with RSI filter
        signal_long = cascade_long_next & (rsi < rsi_long_threshold)
        signal_short = cascade_short_next & (rsi > rsi_short_threshold)

        # First few bars can't have valid signals (no prior cascade)
        signal_long[:2] = False
        signal_short[:2] = False

    elif pattern == "reversal_confirm":
        # Pattern 2: Enter on NEXT bar only if it reverses the cascade direction
        signal_long = np.zeros(n, dtype=bool)
        signal_short = np.zeros(n, dtype=bool)

        is_bullish = df["is_bullish"].values
        is_bearish = df["is_bearish"].values

        cascade_long_next = np.roll(cascade_long, 1)
        cascade_short_next = np.roll(cascade_short, 1)
        cascade_long_next[0] = False
        cascade_short_next[0] = False

        # After sharp drop: next bar must be bullish + RSI oversold -> LONG
        signal_long = cascade_long_next & is_bullish & (rsi < rsi_long_threshold)
        # After sharp rise: next bar must be bearish + RSI overbought -> SHORT
        signal_short = cascade_short_next & is_bearish & (rsi > rsi_short_threshold)

        signal_long[:2] = False
        signal_short[:2] = False

    elif pattern == "highvol_reversal":
        # Pattern 3: Enter when ATR normalizes after high-vol period
        # that contained a cascade event
        atr = df["atr"].values
        atr_avg = df["atr_avg"].values

        # High-vol: max ATR over last 3 bars >= 2x average ATR
        atr_rolling_max = pd.Series(atr).rolling(window=3, min_periods=1).max().values
        high_vol = atr_rolling_max >= 2.0 * atr_avg
        high_vol[:ATR_PERIOD + 3] = False  # warmup

        # Track high-vol windows and cascade events within them
        signal_long = np.zeros(n, dtype=bool)
        signal_short = np.zeros(n, dtype=bool)

        in_high_vol = False
        cascade_dir_in_window = 0  # +1=long bias, -1=short bias

        for i in range(ATR_PERIOD + 3, n):
            if high_vol[i]:
                if not in_high_vol:
                    in_high_vol = True
                    cascade_dir_in_window = 0
                # Track cascade direction during high-vol
                if cascade_long[i]:
                    cascade_dir_in_window = 1
                elif cascade_short[i]:
                    cascade_dir_in_window = -1
            else:
                if in_high_vol:
                    # High-vol just ended - check for entry
                    if pd.notna(atr_avg[i]) and atr[i] <= atr_avg[i]:
                        if cascade_dir_in_window == 1 and rsi[i] < rsi_long_threshold:
                            signal_long[i] = True
                        elif cascade_dir_in_window == -1 and rsi[i] > rsi_short_threshold:
                            signal_short[i] = True
                    in_high_vol = False
                    cascade_dir_in_window = 0

    else:
        raise ValueError(f"Unknown pattern: {pattern}")

    return signal_long, signal_short


# ----------------------------------------------
# Backtest Engine (numpy-optimized)
# ----------------------------------------------
def run_backtest(
    df: pd.DataFrame,
    signal_long: np.ndarray,
    signal_short: np.ndarray,
    sl_pct: float,
    tp_pct: float,
    max_hold_bars: int,
    label: str = "",
) -> dict:
    """Run backtest using pre-computed signal arrays."""
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(df)

    trades_pnl = []
    capital = INITIAL_CAPITAL
    in_position = False
    pos_side = None
    entry_price = 0.0
    entry_idx = 0
    position_size = 0.0

    for i in range(1, n):
        if in_position:
            bars_held = i - entry_idx
            h = high[i]
            l = low[i]
            c = close[i]

            if pos_side == "LONG":
                tp_price = entry_price * (1 + tp_pct)
                sl_price = entry_price * (1 - sl_pct)

                if l <= sl_price:
                    exit_price = sl_price * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "SL"
                elif h >= tp_price:
                    exit_price = tp_price * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "TP"
                elif bars_held >= max_hold_bars:
                    exit_price = c * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "MAX_HOLD"
                else:
                    continue

            elif pos_side == "SHORT":
                tp_price = entry_price * (1 - tp_pct)
                sl_price = entry_price * (1 + sl_pct)

                if h >= sl_price:
                    exit_price = sl_price * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "SL"
                elif l <= tp_price:
                    exit_price = tp_price * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "TP"
                elif bars_held >= max_hold_bars:
                    exit_price = c * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "MAX_HOLD"
                else:
                    continue
            else:
                continue

            pnl_dollar = position_size * pnl_pct * LEVERAGE
            capital += pnl_dollar
            trades_pnl.append({
                "pnl_pct": pnl_pct,
                "pnl_dollar": pnl_dollar,
                "exit_reason": exit_reason,
                "bars_held": bars_held,
                "side": pos_side,
            })
            in_position = False
            pos_side = None

        # Check for new entry
        if not in_position:
            if signal_long[i]:
                entry_price = close[i] * (1 + SLIPPAGE_ONE_WAY)
                pos_side = "LONG"
            elif signal_short[i]:
                entry_price = close[i] * (1 - SLIPPAGE_ONE_WAY)
                pos_side = "SHORT"
            else:
                continue

            position_size = capital * RISK_PER_TRADE
            entry_idx = i
            in_position = True

    # Compute summary statistics
    if not trades_pnl:
        return {
            "label": label,
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_trades": 0,
            "avg_trade_pnl_pct": 0.0,
            "sl_count": 0,
            "tp_count": 0,
            "maxhold_count": 0,
            "long_trades": 0,
            "short_trades": 0,
            "ev_per_trade": 0.0,
        }

    trade_df = pd.DataFrame(trades_pnl)
    total_return_pct = (capital / INITIAL_CAPITAL - 1) * 100

    wins = trade_df[trade_df["pnl_dollar"] > 0]
    losses = trade_df[trade_df["pnl_dollar"] <= 0]
    win_rate = len(wins) / len(trade_df) * 100

    gross_profit = wins["pnl_dollar"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["pnl_dollar"].sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0)

    # Max drawdown
    equity_curve = np.cumsum([INITIAL_CAPITAL] + [t["pnl_dollar"] for t in trades_pnl])
    peak = np.maximum.accumulate(equity_curve)
    max_dd = float(np.max((peak - equity_curve) / peak * 100))

    # Sharpe ratio
    trade_returns = trade_df["pnl_pct"].values / 100
    if len(trade_returns) > 1 and np.std(trade_returns) > 0:
        avg_bars = trade_df["bars_held"].mean()
        trades_per_year = 2190 / avg_bars if avg_bars > 0 else 1
        mean_annual = np.mean(trade_returns) * trades_per_year
        std_annual = np.std(trade_returns) * np.sqrt(trades_per_year)
        sharpe = mean_annual / std_annual if std_annual > 0 else 0
    else:
        sharpe = 0.0

    avg_trade_pnl_pct = trade_df["pnl_pct"].mean()
    ev_per_trade = avg_trade_pnl_pct

    sl_count = len(trade_df[trade_df["exit_reason"] == "SL"])
    tp_count = len(trade_df[trade_df["exit_reason"] == "TP"])
    maxhold_count = len(trade_df[trade_df["exit_reason"] == "MAX_HOLD"])
    long_trades = len(trade_df[trade_df["side"] == "LONG"])
    short_trades = len(trade_df[trade_df["side"] == "SHORT"])

    return {
        "label": label,
        "total_return_pct": round(total_return_pct, 4),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
        "total_trades": len(trade_df),
        "avg_trade_pnl_pct": round(avg_trade_pnl_pct, 6),
        "sl_count": sl_count,
        "tp_count": tp_count,
        "maxhold_count": maxhold_count,
        "long_trades": long_trades,
        "short_trades": short_trades,
        "ev_per_trade": round(ev_per_trade, 6),
    }


# ----------------------------------------------
# Main
# ----------------------------------------------
def main():
    print("=" * 80)
    print("LIQ-REV Entry Timing Comparison Backtest (Optimized)")
    print("=" * 80)
    print(f"\nPatterns: {PATTERNS}")
    print(f"Cascade thresholds: {[f'{x*100:.1f}%' for x in CASCADE_THRESHOLDS]}")
    print(f"SL: {[f'{x*100:.1f}%' for x in SL_PCTS]}")
    print(f"TP: {[f'{x*100:.1f}%' for x in TP_PCTS]}")
    print(f"RSI thresholds: {RSI_THRESHOLDS}")
    print(f"MaxHold: {MAX_HOLD_BARS}")

    # Load data
    print("\n[1] Loading price data...")
    price_df = load_price_data(PRICE_PATH)
    print(f"    {len(price_df)} bars, {price_df['datetime'].iloc[0]} -> {price_df['datetime'].iloc[-1]}")

    # Pre-compute indicators
    print("\n[2] Pre-computing indicators...")
    price_df = precompute_indicators(price_df)

    # Split IS / OOS
    n = len(price_df)
    is_end = int(n * IS_RATIO)
    is_df = price_df.iloc[:is_end].copy().reset_index(drop=True)
    oos_df = price_df.iloc[is_end:].copy().reset_index(drop=True)

    print(f"    IS period: {is_df['datetime'].iloc[0]} -> {is_df['datetime'].iloc[-1]} ({len(is_df)} bars)")
    print(f"    OOS period: {oos_df['datetime'].iloc[0]} -> {oos_df['datetime'].iloc[-1]} ({len(oos_df)} bars)")

    # Build parameter grid
    param_grid = list(itertools.product(
        CASCADE_THRESHOLDS,
        SL_PCTS,
        TP_PCTS,
        RSI_THRESHOLDS,
        MAX_HOLD_BARS,
    ))
    combos_per_pattern = len(param_grid)
    total_combos = combos_per_pattern * len(PATTERNS)
    print(f"\n[3] Grid search: {combos_per_pattern} combos x {len(PATTERNS)} patterns = {total_combos} total")

    # Run grid search
    all_results = []
    start_time = time.time()
    processed = 0

    for pattern in PATTERNS:
        print(f"\n{'-' * 80}")
        print(f"  Pattern: {pattern}")
        print(f"{'-' * 80}")

        for cascade_th, sl, tp, (rsi_long, rsi_short), max_hold in param_grid:
            processed += 1

            if processed % 100 == 0 or processed == 1:
                elapsed = time.time() - start_time
                eta = elapsed / processed * (total_combos - processed) if processed > 0 else 0
                print(f"    [{processed}/{total_combos}] pattern={pattern} cascade={cascade_th:.3f} "
                      f"SL={sl:.3f} TP={tp:.3f} RSI=({rsi_long},{rsi_short}) mh={max_hold}  "
                      f"elapsed={elapsed:.1f}s ETA={eta:.0f}s")

            # Generate signals for IS and OOS
            is_sig_long, is_sig_short = generate_signals(
                is_df, pattern, cascade_th, rsi_long, rsi_short)
            oos_sig_long, oos_sig_short = generate_signals(
                oos_df, pattern, cascade_th, rsi_long, rsi_short)

            # IS backtest
            is_result = run_backtest(
                is_df, is_sig_long, is_sig_short,
                sl_pct=sl, tp_pct=tp, max_hold_bars=max_hold,
                label=f"IS_{pattern}_c{cascade_th}_sl{sl}_tp{tp}_rsi{rsi_long}-{rsi_short}_mh{max_hold}",
            )

            # OOS backtest
            oos_result = run_backtest(
                oos_df, oos_sig_long, oos_sig_short,
                sl_pct=sl, tp_pct=tp, max_hold_bars=max_hold,
                label=f"OOS_{pattern}_c{cascade_th}_sl{tp}_rsi{rsi_long}-{rsi_short}_mh{max_hold}",
            )

            all_results.append({
                "pattern": pattern,
                "params": {
                    "cascade_threshold": cascade_th,
                    "sl_pct": sl,
                    "tp_pct": tp,
                    "rsi_long": rsi_long,
                    "rsi_short": rsi_short,
                    "max_hold_bars": max_hold,
                },
                "is": is_result,
                "oos": oos_result,
            })

    elapsed_total = time.time() - start_time
    print(f"\n    Grid search completed in {elapsed_total:.1f}s")

    # -- Analysis --
    print("\n" + "=" * 80)
    print("ANALYSIS: OOS EV > 0 & PF > 1.0 & Trades >= 10")
    print("=" * 80)

    profitable_oos = []
    for r in all_results:
        oos = r["oos"]
        pf = oos["profit_factor"]
        pf_val = pf if isinstance(pf, (int, float)) else 0
        if oos["ev_per_trade"] > 0 and pf_val > 1.0 and oos["total_trades"] >= 10:
            profitable_oos.append(r)

    print(f"\n  Total combinations: {len(all_results)}")
    print(f"  OOS EV > 0 & PF > 1.0 & Trades >= 10: {len(profitable_oos)}")

    # -- Per-pattern analysis --
    for pattern in PATTERNS:
        pattern_results = [r for r in all_results if r["pattern"] == pattern]
        pattern_profitable = [r for r in profitable_oos if r["pattern"] == pattern]

        print(f"\n{'=' * 80}")
        print(f"  PATTERN: {pattern}")
        print(f"{'=' * 80}")
        print(f"  Total combos: {len(pattern_results)}")
        print(f"  Profitable OOS combos: {len(pattern_profitable)}")

        if pattern_profitable:
            pattern_profitable.sort(key=lambda x: x["oos"]["ev_per_trade"], reverse=True)

            print(f"\n  {'#':<4} {'Cascade':>8} {'SL%':>6} {'TP%':>6} {'RSI':>8} {'MH':>4} "
                  f"{'IS_Ret%':>8} {'OOS_Ret%':>9} {'IS_PF':>8} {'OOS_PF':>8} "
                  f"{'IS_WR%':>7} {'OOS_WR%':>8} {'IS_Tr':>6} {'OOS_Tr':>6} "
                  f"{'IS_EV':>8} {'OOS_EV':>8} {'OOS_MDD':>8}")

            print("  " + "-" * 130)

            for i, r in enumerate(pattern_profitable[:15]):
                p = r["params"]
                is_r = r["is"]
                oos_r = r["oos"]
                is_pf = is_r["profit_factor"] if isinstance(is_r["profit_factor"], (int, float)) else 0
                oos_pf = oos_r["profit_factor"] if isinstance(oos_r["profit_factor"], (int, float)) else 0
                print(f"  {i+1:<4} {p['cascade_threshold']*100:>7.1f}% {p['sl_pct']*100:>5.1f}% "
                      f"{p['tp_pct']*100:>5.1f}% ({p['rsi_long']},{p['rsi_short']}) {p['max_hold_bars']:>4} "
                      f"{is_r['total_return_pct']:>8.2f} {oos_r['total_return_pct']:>9.2f} "
                      f"{is_pf:>8.4f} {oos_pf:>8.4f} "
                      f"{is_r['win_rate']:>7.1f} {oos_r['win_rate']:>8.1f} "
                      f"{is_r['total_trades']:>6} {oos_r['total_trades']:>6} "
                      f"{is_r['ev_per_trade']:>8.4f}% {oos_r['ev_per_trade']:>8.4f}% "
                      f"{oos_r['max_drawdown_pct']:>8.2f}")
        else:
            print("\n  No profitable OOS combinations found for this pattern.")
            pattern_sorted = sorted(pattern_results, key=lambda x: x["oos"]["ev_per_trade"], reverse=True)
            print(f"\n  Top 5 by OOS EV (even if not meeting criteria):")

            print(f"\n  {'#':<4} {'Cascade':>8} {'SL%':>6} {'TP%':>6} {'RSI':>8} {'MH':>4} "
                  f"{'IS_Ret%':>8} {'OOS_Ret%':>9} {'IS_PF':>8} {'OOS_PF':>8} "
                  f"{'IS_WR%':>7} {'OOS_WR%':>8} {'IS_Tr':>6} {'OOS_Tr':>6} "
                  f"{'IS_EV':>8} {'OOS_EV':>8} {'OOS_MDD':>8}")

            print("  " + "-" * 130)

            for i, r in enumerate(pattern_sorted[:5]):
                p = r["params"]
                is_r = r["is"]
                oos_r = r["oos"]
                is_pf = is_r["profit_factor"] if isinstance(is_r["profit_factor"], (int, float)) else 0
                oos_pf = oos_r["profit_factor"] if isinstance(oos_r["profit_factor"], (int, float)) else 0
                print(f"  {i+1:<4} {p['cascade_threshold']*100:>7.1f}% {p['sl_pct']*100:>5.1f}% "
                      f"{p['tp_pct']*100:>5.1f}% ({p['rsi_long']},{p['rsi_short']}) {p['max_hold_bars']:>4} "
                      f"{is_r['total_return_pct']:>8.2f} {oos_r['total_return_pct']:>9.2f} "
                      f"{is_pf:>8.4f} {oos_pf:>8.4f} "
                      f"{is_r['win_rate']:>7.1f} {oos_r['win_rate']:>8.1f} "
                      f"{is_r['total_trades']:>6} {oos_r['total_trades']:>6} "
                      f"{is_r['ev_per_trade']:>8.4f}% {oos_r['ev_per_trade']:>8.4f}% "
                      f"{oos_r['max_drawdown_pct']:>8.2f}")

    # -- Cross-pattern comparison --
    print(f"\n{'=' * 80}")
    print("  CROSS-PATTERN COMPARISON (Best OOS EV per pattern)")
    print(f"{'=' * 80}")

    for pattern in PATTERNS:
        pattern_results = [r for r in all_results if r["pattern"] == pattern]
        pattern_profitable = [r for r in profitable_oos if r["pattern"] == pattern]

        if pattern_profitable:
            best = pattern_profitable[0]
        else:
            best = max(pattern_results, key=lambda x: x["oos"]["ev_per_trade"])

        bp = best["params"]
        bo = best["oos"]
        bi = best["is"]
        is_pf = bi["profit_factor"] if isinstance(bi["profit_factor"], (int, float)) else 0
        oos_pf = bo["profit_factor"] if isinstance(bo["profit_factor"], (int, float)) else 0

        print(f"\n  {pattern}:")
        print(f"    Cascade: {bp['cascade_threshold']*100:.1f}%  SL: {bp['sl_pct']*100:.1f}%  "
              f"TP: {bp['tp_pct']*100:.1f}%  RSI: ({bp['rsi_long']},{bp['rsi_short']})  "
              f"MaxHold: {bp['max_hold_bars']}")
        print(f"    IS  -> Ret: {bi['total_return_pct']:.2f}%  PF: {is_pf:.4f}  "
              f"WR: {bi['win_rate']:.1f}%  Trades: {bi['total_trades']}  EV: {bi['ev_per_trade']:.4f}%")
        print(f"    OOS -> Ret: {bo['total_return_pct']:.2f}%  PF: {oos_pf:.4f}  "
              f"WR: {bo['win_rate']:.1f}%  Trades: {bo['total_trades']}  EV: {bo['ev_per_trade']:.4f}%  "
              f"MDD: {bo['max_drawdown_pct']:.2f}%")

    # -- Parameter sensitivity per pattern --
    print(f"\n{'=' * 80}")
    print("  PARAMETER SENSITIVITY (avg OOS EV by parameter value)")
    print(f"{'=' * 80}")

    for pattern in PATTERNS:
        pattern_results = [r for r in all_results if r["pattern"] == pattern]
        print(f"\n  Pattern: {pattern}")

        for param_name, param_values, getter in [
            ("Cascade Threshold", CASCADE_THRESHOLDS, lambda p: p["cascade_threshold"]),
            ("SL%", SL_PCTS, lambda p: p["sl_pct"]),
            ("TP%", TP_PCTS, lambda p: p["tp_pct"]),
            ("RSI Long", [t[0] for t in RSI_THRESHOLDS], lambda p: p["rsi_long"]),
            ("MaxHold", MAX_HOLD_BARS, lambda p: p["max_hold_bars"]),
        ]:
            print(f"\n    {param_name}:")
            for val in param_values:
                matching = [r for r in pattern_results if getter(r["params"]) == val]
                avg_oos_ev = np.mean([r["oos"]["ev_per_trade"] for r in matching])
                avg_oos_pf = np.mean([
                    r["oos"]["profit_factor"] if isinstance(r["oos"]["profit_factor"], (int, float)) else 0
                    for r in matching
                ])
                avg_oos_wr = np.mean([r["oos"]["win_rate"] for r in matching])
                profitable_count = sum(
                    1 for r in matching
                    if r["oos"]["ev_per_trade"] > 0
                    and (r["oos"]["profit_factor"] if isinstance(r["oos"]["profit_factor"], (int, float)) else 0) > 1.0
                    and r["oos"]["total_trades"] >= 10
                )
                print(f"      {val:>6}: avg_OOS_EV={avg_oos_ev:+.6f}%  avg_OOS_PF={avg_oos_pf:.4f}  "
                      f"avg_OOS_WR={avg_oos_wr:.1f}%  profitable={profitable_count}/{len(matching)}")

    # -- Overall best --
    print(f"\n{'=' * 80}")
    print("  OVERALL BEST (across all patterns)")
    print(f"{'=' * 80}")

    if profitable_oos:
        profitable_oos.sort(key=lambda x: x["oos"]["ev_per_trade"], reverse=True)
        best = profitable_oos[0]
        bp = best["params"]
        bo = best["oos"]
        bi = best["is"]
        is_pf = bi["profit_factor"] if isinstance(bi["profit_factor"], (int, float)) else 0
        oos_pf = bo["profit_factor"] if isinstance(bo["profit_factor"], (int, float)) else 0

        print(f"\n  Pattern: {best['pattern']}")
        print(f"  Cascade: {bp['cascade_threshold']*100:.1f}%")
        print(f"  SL: {bp['sl_pct']*100:.1f}%")
        print(f"  TP: {bp['tp_pct']*100:.1f}%")
        print(f"  RSI: ({bp['rsi_long']}, {bp['rsi_short']})")
        print(f"  MaxHold: {bp['max_hold_bars']} bars")
        print(f"  IS  -> Ret: {bi['total_return_pct']:.2f}%  PF: {is_pf:.4f}  "
              f"WR: {bi['win_rate']:.1f}%  Trades: {bi['total_trades']}  EV: {bi['ev_per_trade']:.4f}%")
        print(f"  OOS -> Ret: {bo['total_return_pct']:.2f}%  PF: {oos_pf:.4f}  "
              f"WR: {bo['win_rate']:.1f}%  Trades: {bo['total_trades']}  EV: {bo['ev_per_trade']:.4f}%  "
              f"MDD: {bo['max_drawdown_pct']:.2f}%")
    else:
        print("\n  No profitable OOS combination found across any pattern.")
        for pattern in PATTERNS:
            pattern_results = [r for r in all_results if r["pattern"] == pattern]
            best = max(pattern_results, key=lambda x: x["oos"]["ev_per_trade"])
            bp = best["params"]
            bo = best["oos"]
            print(f"\n  Best for {pattern}: Cascade={bp['cascade_threshold']*100:.1f}% "
                  f"SL={bp['sl_pct']*100:.1f}% TP={bp['tp_pct']*100:.1f}% "
                  f"RSI=({bp['rsi_long']},{bp['rsi_short']}) MH={bp['max_hold_bars']} "
                  f"OOS_EV={bo['ev_per_trade']:.4f}% OOS_PF={bo['profit_factor']} "
                  f"OOS_Trades={bo['total_trades']}")

    # -- Save results --
    def make_serializable(obj):
        if isinstance(obj, dict):
            return {str(k): make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, pd.Period):
            return str(obj)
        elif isinstance(obj, float) and (obj != obj):
            return None
        elif obj == float("inf"):
            return "inf"
        elif obj == float("-inf"):
            return "-inf"
        return obj

    output = {
        "metadata": {
            "description": "LIQ-REV Entry Timing Comparison Backtest",
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "data_file": str(PRICE_PATH),
            "data_bars": len(price_df),
            "is_bars": len(is_df),
            "oos_bars": len(oos_df),
            "is_start": str(is_df["datetime"].iloc[0]),
            "is_end": str(is_df["datetime"].iloc[-1]),
            "oos_start": str(oos_df["datetime"].iloc[0]),
            "oos_end": str(oos_df["datetime"].iloc[-1]),
            "total_combinations": total_combos,
            "patterns": PATTERNS,
            "fixed_params": {
                "rsi_period": RSI_PERIOD,
                "atr_period": ATR_PERIOD,
                "fee_one_way": FEE_ONE_WAY,
                "slippage_one_way": SLIPPAGE_ONE_WAY,
                "initial_capital": INITIAL_CAPITAL,
                "risk_per_trade": RISK_PER_TRADE,
                "leverage": LEVERAGE,
                "is_ratio": IS_RATIO,
            },
            "grid_params": {
                "cascade_thresholds": CASCADE_THRESHOLDS,
                "sl_pcts": SL_PCTS,
                "tp_pcts": TP_PCTS,
                "rsi_thresholds": RSI_THRESHOLDS,
                "max_hold_bars": MAX_HOLD_BARS,
            },
        },
        "profitable_oos": make_serializable(profitable_oos),
        "all_results": make_serializable(all_results),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[4] Results saved to: {OUTPUT_PATH}")

    # -- Summary --
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total combinations tested: {total_combos}")
    print(f"  Combinations with OOS EV > 0 & PF > 1.0 & Trades >= 10: {len(profitable_oos)}")

    for pattern in PATTERNS:
        pattern_profitable = [r for r in profitable_oos if r["pattern"] == pattern]
        print(f"    {pattern}: {len(pattern_profitable)} profitable combos")

    print("\n" + "=" * 80)
    print("BACKTEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()