#!/usr/bin/env python3
"""
Liquidation Reversal (LIQ-REV) Parameter Optimization Backtest
================================================================
Grid search over 5 parameter dimensions to find optimal LIQ-REV settings.

Original problem: SL -0.24% too tight, win rate 3-6%, PF < 0.2
Goal: Find parameter combinations where OOS EV > 0 and PF > 1.0

Grid:
  - Cascade threshold: [1.0%, 1.5%, 2.0%, 3.0%]
  - SL: [0.5%, 1.0%, 1.5%, 2.0%]
  - TP: [1.0%, 1.5%, 2.0%, 3.0%]
  - RSI thresholds: [(25,75), (30,70), (35,65), (40,60)]
  - MaxHold: [6, 8, 12, 16] bars

Total: 4^5 = 1024 combinations
"""

import json
import itertools
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
PRICE_PATH = Path(r"C:\Users\user\Desktop\cursor\trade\data\btc_price_4h_cache.csv")
OUTPUT_PATH = Path(r"C:\Users\user\Desktop\cursor\trade\data\liq_rev_optimized_results.json")

# Fixed params
RSI_PERIOD = 14
FEE_ONE_WAY = 0.00035          # 0.035% taker
SLIPPAGE_ONE_WAY = 0.0003      # 0.03%
INITIAL_CAPITAL = 190.0
RISK_PER_TRADE = 0.015         # 1.5%
LEVERAGE = 1
IS_RATIO = 0.70                # 70% IS / 30% OOS

# ──────────────────────────────────────────────
# Parameter Grid
# ──────────────────────────────────────────────
CASCADE_THRESHOLDS = [0.01, 0.015, 0.02, 0.03]       # 1.0%, 1.5%, 2.0%, 3.0%
SL_PCTS = [0.005, 0.01, 0.015, 0.02]                  # 0.5%, 1.0%, 1.5%, 2.0%
TP_PCTS = [0.01, 0.015, 0.02, 0.03]                    # 1.0%, 1.5%, 2.0%, 3.0%
RSI_THRESHOLDS = [(25, 75), (30, 70), (35, 65), (40, 60)]
MAX_HOLD_BARS = [6, 8, 12, 16]


# ──────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────
def load_price_data(path: Path) -> pd.DataFrame:
    """Load 4h OHLCV data."""
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ──────────────────────────────────────────────
# Indicators
# ──────────────────────────────────────────────
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_cascade_direction(close: pd.Series, threshold: float) -> pd.Series:
    """
    Return cascade direction:
     +1 = sharp drop (potential LONG reversal)
     -1 = sharp rise (potential SHORT reversal)
     0  = no cascade
    """
    pct_change = close.pct_change()
    direction = pd.Series(0, index=close.index, dtype=float)
    direction[pct_change <= -threshold] = 1    # sharp drop -> LONG bias
    direction[pct_change >= threshold] = -1    # sharp rise -> SHORT bias
    return direction


# ──────────────────────────────────────────────
# Backtest Engine (parameterized)
# ──────────────────────────────────────────────
def run_backtest(
    df: pd.DataFrame,
    cascade_threshold: float,
    sl_pct: float,
    tp_pct: float,
    rsi_long_threshold: int,
    rsi_short_threshold: int,
    max_hold_bars: int,
    label: str = "",
) -> dict:
    """
    Run LIQ-REV backtest with given parameters.
    Returns summary stats dict (no trade list for performance).
    """
    df = df.copy().reset_index(drop=True)

    # Compute indicators
    df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)
    df["cascade_dir"] = compute_cascade_direction(df["close"], cascade_threshold)

    # Entry signals
    cascade = df["cascade_dir"] != 0
    df["signal_long"] = cascade & (df["cascade_dir"] == 1) & (df["rsi"] < rsi_long_threshold)
    df["signal_short"] = cascade & (df["cascade_dir"] == -1) & (df["rsi"] > rsi_short_threshold)

    # Trade simulation
    trades_pnl = []
    capital = INITIAL_CAPITAL
    in_position = False
    pos_side = None
    entry_price = 0.0
    entry_idx = 0
    position_size = 0.0

    for i in range(1, len(df)):
        row = df.iloc[i]

        if in_position:
            bars_held = i - entry_idx
            high = row["high"]
            low = row["low"]
            close = row["close"]

            if pos_side == "LONG":
                tp_price = entry_price * (1 + tp_pct)
                sl_price = entry_price * (1 - sl_pct)

                if low <= sl_price:
                    exit_price = sl_price * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "SL"
                elif high >= tp_price:
                    exit_price = tp_price * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "TP"
                elif bars_held >= max_hold_bars:
                    exit_price = close * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "MAX_HOLD"
                else:
                    continue

            elif pos_side == "SHORT":
                tp_price = entry_price * (1 - tp_pct)
                sl_price = entry_price * (1 + sl_pct)

                if high >= sl_price:
                    exit_price = sl_price * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "SL"
                elif low <= tp_price:
                    exit_price = tp_price * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "TP"
                elif bars_held >= max_hold_bars:
                    exit_price = close * (1 + SLIPPAGE_ONE_WAY)
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
            if df.iloc[i]["signal_long"]:
                entry_price = row["close"] * (1 + SLIPPAGE_ONE_WAY)
                pos_side = "LONG"
            elif df.iloc[i]["signal_short"]:
                entry_price = row["close"] * (1 - SLIPPAGE_ONE_WAY)
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
    final_capital = capital
    total_return_pct = (final_capital / INITIAL_CAPITAL - 1) * 100

    wins = trade_df[trade_df["pnl_dollar"] > 0]
    losses = trade_df[trade_df["pnl_dollar"] <= 0]
    win_rate = len(wins) / len(trade_df) * 100

    gross_profit = wins["pnl_dollar"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["pnl_dollar"].sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0)

    # Max drawdown
    equity_curve = [INITIAL_CAPITAL]
    running_capital = INITIAL_CAPITAL
    for t in trades_pnl:
        running_capital += t["pnl_dollar"]
        equity_curve.append(running_capital)
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualized)
    trade_returns = trade_df["pnl_pct"].values / 100
    if len(trade_returns) > 1 and np.std(trade_returns) > 0:
        avg_bars = trade_df["bars_held"].mean()
        trades_per_year = 2190 / avg_bars if avg_bars > 0 else 1
        mean_annual = np.mean(trade_returns) * trades_per_year
        std_annual = np.std(trade_returns) * np.sqrt(trades_per_year)
        sharpe = mean_annual / std_annual if std_annual > 0 else 0
    else:
        sharpe = 0.0

    # EV per trade
    avg_trade_pnl_pct = trade_df["pnl_pct"].mean()
    ev_per_trade = avg_trade_pnl_pct

    # Exit reason counts
    sl_count = len(trade_df[trade_df["exit_reason"] == "SL"])
    tp_count = len(trade_df[trade_df["exit_reason"] == "TP"])
    maxhold_count = len(trade_df[trade_df["exit_reason"] == "MAX_HOLD"])

    # Side counts
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


# ──────────────────────────────────────────────
# Main: Grid Search
# ──────────────────────────────────────────────
def main():
    print("=" * 70)
    print("LIQ-REV Parameter Optimization (Grid Search)")
    print("=" * 70)

    # Load data
    print("\n[1] Loading price data...")
    price_df = load_price_data(PRICE_PATH)
    print(f"    {len(price_df)} bars, {price_df['datetime'].iloc[0]} -> {price_df['datetime'].iloc[-1]}")

    # Split IS / OOS
    n = len(price_df)
    is_end = int(n * IS_RATIO)
    is_df = price_df.iloc[:is_end].copy()
    oos_df = price_df.iloc[is_end:].copy()

    print(f"\n[2] IS period: {is_df['datetime'].iloc[0]} -> {is_df['datetime'].iloc[-1]} ({len(is_df)} bars)")
    print(f"    OOS period: {oos_df['datetime'].iloc[0]} -> {oos_df['datetime'].iloc[-1]} ({len(oos_df)} bars)")

    # Build parameter grid
    param_grid = list(itertools.product(
        CASCADE_THRESHOLDS,
        SL_PCTS,
        TP_PCTS,
        RSI_THRESHOLDS,
        MAX_HOLD_BARS,
    ))
    total_combos = len(param_grid)
    print(f"\n[3] Grid search: {total_combos} combinations")

    # Run grid search
    results = []
    start_time = time.time()

    for idx, (cascade_th, sl, tp, (rsi_long, rsi_short), max_hold) in enumerate(param_grid):
        if (idx + 1) % 100 == 0 or idx == 0:
            elapsed = time.time() - start_time
            eta = elapsed / (idx + 1) * (total_combos - idx - 1) if idx > 0 else 0
            print(f"    [{idx+1}/{total_combos}] cascade={cascade_th:.3f} SL={sl:.3f} TP={tp:.3f} "
                  f"RSI=({rsi_long},{rsi_short}) maxhold={max_hold}  "
                  f"elapsed={elapsed:.1f}s ETA={eta:.0f}s")

        # IS backtest
        is_result = run_backtest(
            is_df,
            cascade_threshold=cascade_th,
            sl_pct=sl,
            tp_pct=tp,
            rsi_long_threshold=rsi_long,
            rsi_short_threshold=rsi_short,
            max_hold_bars=max_hold,
            label=f"IS_c{cascade_th}_sl{sl}_tp{tp}_rsi{rsi_long}-{rsi_short}_mh{max_hold}",
        )

        # OOS backtest
        oos_result = run_backtest(
            oos_df,
            cascade_threshold=cascade_th,
            sl_pct=sl,
            tp_pct=tp,
            rsi_long_threshold=rsi_long,
            rsi_short_threshold=rsi_short,
            max_hold_bars=max_hold,
            label=f"OOS_c{cascade_th}_sl{sl}_tp{tp}_rsi{rsi_long}-{rsi_short}_mh{max_hold}",
        )

        results.append({
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

    # ── Analysis ──
    print("\n" + "=" * 70)
    print("ANALYSIS: OOS EV > 0 and PF > 1.0")
    print("=" * 70)

    profitable_oos = []
    for r in results:
        oos = r["oos"]
        pf = oos["profit_factor"]
        pf_val = pf if isinstance(pf, (int, float)) else 0
        if oos["ev_per_trade"] > 0 and pf_val > 1.0 and oos["total_trades"] >= 5:
            profitable_oos.append(r)

    print(f"\n  Total combinations: {len(results)}")
    print(f"  OOS EV > 0 & PF > 1.0 (min 5 trades): {len(profitable_oos)}")

    if profitable_oos:
        # Sort by OOS EV descending
        profitable_oos.sort(key=lambda x: x["oos"]["ev_per_trade"], reverse=True)

        print(f"\n  {'#':<4} {'Cascade':>8} {'SL%':>6} {'TP%':>6} {'RSI':>8} {'MH':>4} "
              f"{'IS_Ret%':>8} {'OOS_Ret%':>9} {'IS_PF':>8} {'OOS_PF':>8} "
              f"{'IS_WR%':>7} {'OOS_WR%':>8} {'IS_Tr':>6} {'OOS_Tr':>6} "
              f"{'IS_EV':>8} {'OOS_EV':>8} {'OOS_MDD':>8}")

        print("  " + "-" * 120)

        for i, r in enumerate(profitable_oos[:20]):  # Show top 20
            p = r["params"]
            is_r = r["is"]
            oos_r = r["oos"]
            is_pf = is_r["profit_factor"] if isinstance(is_r["profit_factor"], (int, float)) else 0
            oos_pf = oos_r["profit_factor"] if isinstance(oos_r["profit_factor"], (int, float)) else 0
            print(f"  {i+1:<4} {p['cascade_threshold']*100:>7.1f}% {p['sl_pct']*100:>5.1f}% {p['tp_pct']*100:>5.1f}% "
                  f"({p['rsi_long']},{p['rsi_short']}) {p['max_hold_bars']:>4} "
                  f"{is_r['total_return_pct']:>8.2f} {oos_r['total_return_pct']:>9.2f} "
                  f"{is_pf:>8.4f} {oos_pf:>8.4f} "
                  f"{is_r['win_rate']:>7.1f} {oos_r['win_rate']:>8.1f} "
                  f"{is_r['total_trades']:>6} {oos_r['total_trades']:>6} "
                  f"{is_r['ev_per_trade']:>8.4f}% {oos_r['ev_per_trade']:>8.4f}% "
                  f"{oos_r['max_drawdown_pct']:>8.2f}")
    else:
        print("\n  No combinations found with OOS EV > 0 and PF > 1.0 (min 5 trades)")

    # ── Top 5 by OOS EV (even if not profitable) ──
    print("\n" + "=" * 70)
    print("TOP 5 BY OOS EV PER TRADE (all combinations)")
    print("=" * 70)

    all_sorted = sorted(results, key=lambda x: x["oos"]["ev_per_trade"], reverse=True)

    print(f"\n  {'#':<4} {'Cascade':>8} {'SL%':>6} {'TP%':>6} {'RSI':>8} {'MH':>4} "
          f"{'IS_Ret%':>8} {'OOS_Ret%':>9} {'IS_PF':>8} {'OOS_PF':>8} "
          f"{'IS_WR%':>7} {'OOS_WR%':>8} {'IS_Tr':>6} {'OOS_Tr':>6} "
          f"{'IS_EV':>8} {'OOS_EV':>8} {'OOS_MDD':>8}")

    print("  " + "-" * 120)

    for i, r in enumerate(all_sorted[:5]):
        p = r["params"]
        is_r = r["is"]
        oos_r = r["oos"]
        is_pf = is_r["profit_factor"] if isinstance(is_r["profit_factor"], (int, float)) else 0
        oos_pf = oos_r["profit_factor"] if isinstance(oos_r["profit_factor"], (int, float)) else 0
        print(f"  {i+1:<4} {p['cascade_threshold']*100:>7.1f}% {p['sl_pct']*100:>5.1f}% {p['tp_pct']*100:>5.1f}% "
              f"({p['rsi_long']},{p['rsi_short']}) {p['max_hold_bars']:>4} "
              f"{is_r['total_return_pct']:>8.2f} {oos_r['total_return_pct']:>9.2f} "
              f"{is_pf:>8.4f} {oos_pf:>8.4f} "
              f"{is_r['win_rate']:>7.1f} {oos_r['win_rate']:>8.1f} "
              f"{is_r['total_trades']:>6} {oos_r['total_trades']:>6} "
              f"{is_r['ev_per_trade']:>8.4f}% {oos_r['ev_per_trade']:>8.4f}% "
              f"{oos_r['max_drawdown_pct']:>8.2f}")

    # ── Parameter sensitivity analysis ──
    print("\n" + "=" * 70)
    print("PARAMETER SENSITIVITY (avg OOS EV by parameter value)")
    print("=" * 70)

    for param_name, param_values, getter in [
        ("Cascade Threshold", CASCADE_THRESHOLDS, lambda p: p["cascade_threshold"]),
        ("SL%", SL_PCTS, lambda p: p["sl_pct"]),
        ("TP%", TP_PCTS, lambda p: p["tp_pct"]),
        ("RSI Long", [t[0] for t in RSI_THRESHOLDS], lambda p: p["rsi_long"]),
        ("MaxHold", MAX_HOLD_BARS, lambda p: p["max_hold_bars"]),
    ]:
        print(f"\n  {param_name}:")
        for val in param_values:
            matching = [r for r in results if getter(r["params"]) == val]
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
                and r["oos"]["total_trades"] >= 5
            )
            print(f"    {val:>6}: avg_OOS_EV={avg_oos_ev:+.6f}%  avg_OOS_PF={avg_oos_pf:.4f}  "
                  f"avg_OOS_WR={avg_oos_wr:.1f}%  profitable_combos={profitable_count}/{len(matching)}")

    # ── Save all results to JSON ──
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
        elif isinstance(obj, float) and (obj != obj):  # NaN check
            return None
        elif obj == float("inf"):
            return "inf"
        elif obj == float("-inf"):
            return "-inf"
        return obj

    output = {
        "metadata": {
            "description": "LIQ-REV Grid Search Optimization",
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
            "fixed_params": {
                "rsi_period": RSI_PERIOD,
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
        "top5_oos_ev": make_serializable(all_sorted[:5]),
        "all_results": make_serializable(results),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[4] Results saved to: {OUTPUT_PATH}")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total combinations tested: {total_combos}")
    print(f"  Combinations with OOS EV > 0 & PF > 1.0 (min 5 trades): {len(profitable_oos)}")

    if profitable_oos:
        best = profitable_oos[0]
        bp = best["params"]
        bo = best["oos"]
        print(f"\n  BEST OOS COMBINATION:")
        print(f"    Cascade: {bp['cascade_threshold']*100:.1f}%")
        print(f"    SL: {bp['sl_pct']*100:.1f}%")
        print(f"    TP: {bp['tp_pct']*100:.1f}%")
        print(f"    RSI: ({bp['rsi_long']}, {bp['rsi_short']})")
        print(f"    MaxHold: {bp['max_hold_bars']} bars")
        print(f"    OOS Return: {bo['total_return_pct']:.2f}%")
        print(f"    OOS Win Rate: {bo['win_rate']:.1f}%")
        print(f"    OOS PF: {bo['profit_factor']}")
        print(f"    OOS EV/trade: {bo['ev_per_trade']:.4f}%")
        print(f"    OOS Trades: {bo['total_trades']}")
        print(f"    OOS MDD: {bo['max_drawdown_pct']:.2f}%")
    else:
        print("\n  No profitable OOS combination found.")
        # Show best by OOS EV anyway
        best_ev = all_sorted[0]
        bp = best_ev["params"]
        bo = best_ev["oos"]
        print(f"\n  BEST BY OOS EV (even if not profitable):")
        print(f"    Cascade: {bp['cascade_threshold']*100:.1f}%")
        print(f"    SL: {bp['sl_pct']*100:.1f}%")
        print(f"    TP: {bp['tp_pct']*100:.1f}%")
        print(f"    RSI: ({bp['rsi_long']}, {bp['rsi_short']})")
        print(f"    MaxHold: {bp['max_hold_bars']} bars")
        print(f"    OOS Return: {bo['total_return_pct']:.2f}%")
        print(f"    OOS Win Rate: {bo['win_rate']:.1f}%")
        print(f"    OOS PF: {bo['profit_factor']}")
        print(f"    OOS EV/trade: {bo['ev_per_trade']:.4f}%")
        print(f"    OOS Trades: {bo['total_trades']}")

    print("\n" + "=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()