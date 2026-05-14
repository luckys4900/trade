#!/usr/bin/env python3
"""
Liquidation Reversal (LIQ-REV) Backtest
========================================
Pure pandas/numpy implementation - no backtesting.py dependency.

Strategy:
  - Detect liquidation cascade: price change >= ±2% from previous bar
  - Entry: cascade + RSI(14)<30 → LONG, cascade + RSI(14)>70 → SHORT
  - Exit: TP +0.95%, SL -0.24%, Max Hold 12 bars (48h)
  - Fees: 0.035% taker one-way (0.07% round-trip)
  - Slippage: 0.03% one-way

FR-filter variant:
  - FR > 0.01% → SHORT only
  - FR < -0.01% → LONG only

Backtest:
  - IS: first 70% of data
  - OOS: last 30% of data
  - Initial capital: $190, Risk/trade: 1.5%, Leverage: 1x
"""

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
PRICE_PATH = Path(r"C:\Users\user\Desktop\cursor\trade\data\btc_price_4h_cache.csv")
FR_PATH = Path(r"C:\Users\user\Desktop\cursor\trade\data\btc_funding_rate.csv")
OUTPUT_PATH = Path(r"C:\Users\user\Desktop\cursor\trade\data\liq_rev_backtest_results.json")

# Strategy params
CASCADE_THRESHOLD = 0.02       # ±2% price change = liquidation cascade
RSI_PERIOD = 14
RSI_LONG_THRESHOLD = 30        # RSI < 30 → LONG
RSI_SHORT_THRESHOLD = 70       # RSI > 70 → SHORT
TP_PCT = 0.0095                # +0.95%
SL_PCT = 0.0024                # -0.24%
MAX_HOLD_BARS = 12             # 12 bars = 48 hours
FEE_ONE_WAY = 0.00035         # 0.035% taker
SLIPPAGE_ONE_WAY = 0.0003      # 0.03%

# Backtest params
INITIAL_CAPITAL = 190.0
RISK_PER_TRADE = 0.015         # 1.5%
LEVERAGE = 1
IS_RATIO = 0.70                # first 70% = IS, last 30% = OOS

# FR filter thresholds
FR_SHORT_THRESHOLD = 0.0001    # FR > 0.01% → SHORT
FR_LONG_THRESHOLD = -0.0001   # FR < -0.01% → LONG


# ──────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────
def load_price_data(path: Path) -> pd.DataFrame:
    """Load 4h OHLCV data."""
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_funding_rate(path: Path) -> pd.DataFrame:
    """Load hourly funding rate data."""
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


# ──────────────────────────────────────────────
# Indicators
# ──────────────────────────────────────────────
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # Wilder's EMA (exponential moving average with alpha = 1/period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_cascade_signal(close: pd.Series, threshold: float = 0.02) -> pd.Series:
    """Detect liquidation cascade: |close/prev_close - 1| >= threshold."""
    pct_change = close.pct_change()
    cascade = pct_change.abs() >= threshold
    return cascade


def compute_cascade_direction(close: pd.Series, threshold: float = 0.02) -> pd.Series:
    """
    Return cascade direction:
     +1 = sharp drop (potential LONG reversal)
     -1 = sharp rise (potential SHORT reversal)
     0  = no cascade
    """
    pct_change = close.pct_change()
    direction = pd.Series(0, index=close.index, dtype=float)
    direction[pct_change <= -threshold] = 1   # sharp drop → LONG bias
    direction[pct_change >= threshold] = -1   # sharp rise → SHORT bias
    return direction


# ──────────────────────────────────────────────
# Merge FR into price data
# ──────────────────────────────────────────────
def merge_funding_rate(price_df: pd.DataFrame, fr_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge hourly funding rate into 4h price data.
    Use the FR value closest to each 4h bar's open time.
    """
    fr = fr_df.set_index("datetime")
    # Reindex FR to 4h frequency using nearest match
    price_dt = price_df["datetime"]
    merged_fr = fr.reindex(price_dt, method="nearest", tolerance=pd.Timedelta("2h"))
    price_df = price_df.copy()
    price_df["fundingRate"] = merged_fr["fundingRate"].values
    return price_df


# ──────────────────────────────────────────────
# Backtest Engine
# ──────────────────────────────────────────────
def run_backtest(
    df: pd.DataFrame,
    use_fr_filter: bool = False,
    label: str = "LIQ-REV",
) -> dict:
    """
    Run the LIQ-REV backtest on a DataFrame slice.
    Returns a dict with trade list and summary stats.
    """
    df = df.copy().reset_index(drop=True)

    # Compute indicators
    df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)
    df["cascade"] = compute_cascade_signal(df["close"], CASCADE_THRESHOLD)
    df["cascade_dir"] = compute_cascade_direction(df["close"], CASCADE_THRESHOLD)

    # Entry signals
    df["signal_long"] = df["cascade"] & (df["cascade_dir"] == 1) & (df["rsi"] < RSI_LONG_THRESHOLD)
    df["signal_short"] = df["cascade"] & (df["cascade_dir"] == -1) & (df["rsi"] > RSI_SHORT_THRESHOLD)

    # Apply FR filter if requested
    if use_fr_filter and "fundingRate" in df.columns:
        fr = df["fundingRate"].fillna(0.0)
        # LONG only when FR < -0.01%
        df["signal_long"] = df["signal_long"] & (fr < FR_LONG_THRESHOLD)
        # SHORT only when FR > 0.01%
        df["signal_short"] = df["signal_short"] & (fr > FR_SHORT_THRESHOLD)

    # ── Trade simulation ──
    trades = []
    capital = INITIAL_CAPITAL
    in_position = False
    pos_side = None       # "LONG" or "SHORT"
    entry_price = 0.0
    entry_idx = 0
    entry_time = None
    position_size = 0.0   # dollar size of position

    for i in range(1, len(df)):
        row = df.iloc[i]

        # ── If in position, check exit conditions ──
        if in_position:
            bars_held = i - entry_idx
            high = row["high"]
            low = row["low"]
            close = row["close"]

            if pos_side == "LONG":
                # Apply slippage to exit
                # TP hit?
                tp_price = entry_price * (1 + TP_PCT)
                sl_price = entry_price * (1 - SL_PCT)

                if low <= sl_price:
                    # SL hit - exit at SL price with slippage
                    exit_price = sl_price * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "SL"
                elif high >= tp_price:
                    # TP hit - exit at TP price with slippage
                    exit_price = tp_price * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "TP"
                elif bars_held >= MAX_HOLD_BARS:
                    # Max hold - exit at close with slippage
                    exit_price = close * (1 - SLIPPAGE_ONE_WAY)
                    pnl_pct = (exit_price / entry_price) - 1 - 2 * FEE_ONE_WAY
                    exit_reason = "MAX_HOLD"
                else:
                    continue  # hold

            elif pos_side == "SHORT":
                tp_price = entry_price * (1 - TP_PCT)
                sl_price = entry_price * (1 + SL_PCT)

                if high >= sl_price:
                    # SL hit
                    exit_price = sl_price * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "SL"
                elif low <= tp_price:
                    # TP hit
                    exit_price = tp_price * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "TP"
                elif bars_held >= MAX_HOLD_BARS:
                    exit_price = close * (1 + SLIPPAGE_ONE_WAY)
                    pnl_pct = 1 - (exit_price / entry_price) - 2 * FEE_ONE_WAY
                    exit_reason = "MAX_HOLD"
                else:
                    continue  # hold

            # Record trade
            pnl_dollar = position_size * pnl_pct * LEVERAGE
            capital += pnl_dollar

            trades.append({
                "entry_time": str(entry_time),
                "exit_time": str(row["datetime"]),
                "side": pos_side,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "pnl_pct": round(pnl_pct * 100, 4),  # as percentage
                "pnl_dollar": round(pnl_dollar, 4),
                "exit_reason": exit_reason,
                "bars_held": bars_held,
                "capital_after": round(capital, 2),
            })

            in_position = False
            pos_side = None

        # ── Check for new entry (only if not in position) ──
        if not in_position:
            # Apply entry slippage
            if df.iloc[i]["signal_long"]:
                entry_price = row["close"] * (1 + SLIPPAGE_ONE_WAY)  # buy higher
                pos_side = "LONG"
            elif df.iloc[i]["signal_short"]:
                entry_price = row["close"] * (1 - SLIPPAGE_ONE_WAY)  # sell lower
                pos_side = "SHORT"
            else:
                continue

            # Position sizing: risk-based
            position_size = capital * RISK_PER_TRADE
            entry_idx = i
            entry_time = row["datetime"]
            in_position = True

    # ── Compute summary statistics ──
    if not trades:
        return {
            "label": label,
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_trades": 0,
            "trades": [],
            "monthly_breakdown": {},
        }

    trade_df = pd.DataFrame(trades)

    # Total return
    final_capital = trade_df.iloc[-1]["capital_after"]
    total_return_pct = (final_capital / INITIAL_CAPITAL - 1) * 100

    # Win rate
    wins = trade_df[trade_df["pnl_dollar"] > 0]
    losses = trade_df[trade_df["pnl_dollar"] <= 0]
    win_rate = len(wins) / len(trade_df) * 100 if len(trade_df) > 0 else 0

    # Profit factor
    gross_profit = wins["pnl_dollar"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["pnl_dollar"].sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0

    # Max drawdown
    equity_curve = [INITIAL_CAPITAL] + trade_df["capital_after"].tolist()
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualized, assuming 4h bars → 6 bars/day → 2190 bars/year)
    trade_returns = trade_df["pnl_pct"].values / 100  # convert back to decimal
    if len(trade_returns) > 1 and np.std(trade_returns) > 0:
        # Average bars per trade
        avg_bars = trade_df["bars_held"].mean()
        trades_per_year = 2190 / avg_bars if avg_bars > 0 else 1
        mean_annual = np.mean(trade_returns) * trades_per_year
        std_annual = np.std(trade_returns) * np.sqrt(trades_per_year)
        sharpe = mean_annual / std_annual if std_annual > 0 else 0
    else:
        sharpe = 0.0

    # Monthly breakdown
    trade_df["exit_month"] = pd.to_datetime(trade_df["exit_time"], utc=True).dt.to_period("M")
    monthly = {}
    for period, group in trade_df.groupby("exit_month"):
        m_wins = group[group["pnl_dollar"] > 0]
        m_losses = group[group["pnl_dollar"] <= 0]
        m_gross_profit = m_wins["pnl_dollar"].sum() if len(m_wins) > 0 else 0
        m_gross_loss = abs(m_losses["pnl_dollar"].sum()) if len(m_losses) > 0 else 0
        monthly[str(period)] = {
            "trades": len(group),
            "wins": len(m_wins),
            "losses": len(m_losses),
            "win_rate": round(len(m_wins) / len(group) * 100, 1) if len(group) > 0 else 0,
            "total_pnl": round(group["pnl_dollar"].sum(), 4),
            "gross_profit": round(m_gross_profit, 4),
            "gross_loss": round(m_gross_loss, 4),
        }

    return {
        "label": label,
        "total_return_pct": round(total_return_pct, 2),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 4),
        "total_trades": len(trade_df),
        "trades": trades,
        "monthly_breakdown": monthly,
    }


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Liquidation Reversal (LIQ-REV) Backtest")
    print("=" * 60)

    # Load data
    print("\n[1] Loading price data...")
    price_df = load_price_data(PRICE_PATH)
    print(f"    Price data: {len(price_df)} bars, {price_df['datetime'].iloc[0]} → {price_df['datetime'].iloc[-1]}")

    print("[2] Loading funding rate data...")
    fr_df = load_funding_rate(FR_PATH)
    print(f"    FR data: {len(fr_df)} rows, {fr_df['datetime'].iloc[0]} → {fr_df['datetime'].iloc[-1]}")

    # Merge FR into price data
    print("[3] Merging funding rate into price data...")
    price_with_fr = merge_funding_rate(price_df, fr_df)
    fr_coverage = price_with_fr["fundingRate"].notna().sum()
    print(f"    FR coverage: {fr_coverage}/{len(price_with_fr)} bars ({fr_coverage/len(price_with_fr)*100:.1f}%)")

    # Split IS / OOS
    n = len(price_df)
    is_end = int(n * IS_RATIO)
    oos_start = is_end

    is_df = price_df.iloc[:is_end].copy()
    oos_df = price_df.iloc[oos_start:].copy()

    is_df_fr = price_with_fr.iloc[:is_end].copy()
    oos_df_fr = price_with_fr.iloc[oos_start:].copy()

    print(f"\n[4] IS period: {is_df['datetime'].iloc[0]} → {is_df['datetime'].iloc[-1]} ({len(is_df)} bars)")
    print(f"    OOS period: {oos_df['datetime'].iloc[0]} → {oos_df['datetime'].iloc[-1]} ({len(oos_df)} bars)")

    # ── Run backtests ──
    results = {}

    # 1. LIQ-REV (no FR filter) - IS
    print("\n[5] Running LIQ-REV (no FR filter) - IS...")
    res_is = run_backtest(is_df, use_fr_filter=False, label="LIQ-REV_IS")
    results["liq_rev_is"] = {k: v for k, v in res_is.items() if k != "trades"}
    print(f"    Trades: {res_is['total_trades']}, Return: {res_is['total_return_pct']}%, "
          f"Win Rate: {res_is['win_rate']}%, PF: {res_is['profit_factor']}, "
          f"MDD: {res_is['max_drawdown_pct']}%, Sharpe: {res_is['sharpe_ratio']}")

    # 2. LIQ-REV (no FR filter) - OOS
    print("[6] Running LIQ-REV (no FR filter) - OOS...")
    res_oos = run_backtest(oos_df, use_fr_filter=False, label="LIQ-REV_OOS")
    results["liq_rev_oos"] = {k: v for k, v in res_oos.items() if k != "trades"}
    print(f"    Trades: {res_oos['total_trades']}, Return: {res_oos['total_return_pct']}%, "
          f"Win Rate: {res_oos['win_rate']}%, PF: {res_oos['profit_factor']}, "
          f"MDD: {res_oos['max_drawdown_pct']}%, Sharpe: {res_oos['sharpe_ratio']}")

    # 3. LIQ-REV + FR filter - IS
    print("[7] Running LIQ-REV + FR filter - IS...")
    res_is_fr = run_backtest(is_df_fr, use_fr_filter=True, label="LIQ-REV_FR_IS")
    results["liq_rev_fr_is"] = {k: v for k, v in res_is_fr.items() if k != "trades"}
    print(f"    Trades: {res_is_fr['total_trades']}, Return: {res_is_fr['total_return_pct']}%, "
          f"Win Rate: {res_is_fr['win_rate']}%, PF: {res_is_fr['profit_factor']}, "
          f"MDD: {res_is_fr['max_drawdown_pct']}%, Sharpe: {res_is_fr['sharpe_ratio']}")

    # 4. LIQ-REV + FR filter - OOS
    print("[8] Running LIQ-REV + FR filter - OOS...")
    res_oos_fr = run_backtest(oos_df_fr, use_fr_filter=True, label="LIQ-REV_FR_OOS")
    results["liq_rev_fr_oos"] = {k: v for k, v in res_oos_fr.items() if k != "trades"}
    print(f"    Trades: {res_oos_fr['total_trades']}, Return: {res_oos_fr['total_return_pct']}%, "
          f"Win Rate: {res_oos_fr['win_rate']}%, PF: {res_oos_fr['profit_factor']}, "
          f"MDD: {res_oos_fr['max_drawdown_pct']}%, Sharpe: {res_oos_fr['sharpe_ratio']}")

    # ── Summary table ──
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Variant':<20} {'Period':<6} {'Trades':>7} {'Return%':>9} {'WinRate%':>9} "
          f"{'PF':>8} {'MDD%':>7} {'Sharpe':>8}")
    print("-" * 80)

    for key, variant, period in [
        ("liq_rev_is", "LIQ-REV", "IS"),
        ("liq_rev_oos", "LIQ-REV", "OOS"),
        ("liq_rev_fr_is", "LIQ-REV+FR", "IS"),
        ("liq_rev_fr_oos", "LIQ-REV+FR", "OOS"),
    ]:
        r = results[key]
        pf_str = f"{r['profit_factor']:.4f}" if isinstance(r['profit_factor'], (int, float)) else str(r['profit_factor'])
        print(f"{variant:<16} {period:<6} {r['total_trades']:>7} {r['total_return_pct']:>9.2f} {r['win_rate']:>9.2f} "
              f"{pf_str:>8} {r['max_drawdown_pct']:>7.2f} {r['sharpe_ratio']:>8.4f}")

    print("\n" + "=" * 80)
    print("DETAILED SUMMARY")
    print("=" * 80)
    for key in ["liq_rev_is", "liq_rev_oos", "liq_rev_fr_is", "liq_rev_fr_oos"]:
        r = results[key]
        pf_str = f"{r['profit_factor']:.4f}" if isinstance(r['profit_factor'], (int, float)) else str(r['profit_factor'])
        print(f"\n  {r['label']}:")
        print(f"    Total Return:  {r['total_return_pct']:.2f}%")
        print(f"    Win Rate:      {r['win_rate']:.2f}%")
        print(f"    Profit Factor: {pf_str}")
        print(f"    Max Drawdown:  {r['max_drawdown_pct']:.2f}%")
        print(f"    Sharpe Ratio:  {r['sharpe_ratio']:.4f}")
        print(f"    Total Trades:  {r['total_trades']}")

    # ── Save results to JSON ──
    # Include all trades for detailed analysis
    all_results = {
        "config": {
            "cascade_threshold": CASCADE_THRESHOLD,
            "rsi_period": RSI_PERIOD,
            "rsi_long_threshold": RSI_LONG_THRESHOLD,
            "rsi_short_threshold": RSI_SHORT_THRESHOLD,
            "tp_pct": TP_PCT,
            "sl_pct": SL_PCT,
            "max_hold_bars": MAX_HOLD_BARS,
            "fee_one_way": FEE_ONE_WAY,
            "slippage_one_way": SLIPPAGE_ONE_WAY,
            "initial_capital": INITIAL_CAPITAL,
            "risk_per_trade": RISK_PER_TRADE,
            "leverage": LEVERAGE,
            "is_ratio": IS_RATIO,
            "fr_short_threshold": FR_SHORT_THRESHOLD,
            "fr_long_threshold": FR_LONG_THRESHOLD,
        },
        "data_range": {
            "price_start": str(price_df["datetime"].iloc[0]),
            "price_end": str(price_df["datetime"].iloc[-1]),
            "is_start": str(is_df["datetime"].iloc[0]),
            "is_end": str(is_df["datetime"].iloc[-1]),
            "oos_start": str(oos_df["datetime"].iloc[0]),
            "oos_end": str(oos_df["datetime"].iloc[-1]),
            "is_bars": len(is_df),
            "oos_bars": len(oos_df),
        },
        "results": results,
        "trades": {
            "liq_rev_is": res_is["trades"],
            "liq_rev_oos": res_oos["trades"],
            "liq_rev_fr_is": res_is_fr["trades"],
            "liq_rev_fr_oos": res_oos_fr["trades"],
        },
    }

    # Convert Period objects to strings for JSON serialization
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
        return obj

    all_results = make_serializable(all_results)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n[9] Results saved to: {OUTPUT_PATH}")

    # ── Monthly breakdown ──
    print("\n" + "=" * 80)
    print("MONTHLY BREAKDOWN")
    print("=" * 80)
    for key, label_name in [
        ("liq_rev_is", "LIQ-REV IS"),
        ("liq_rev_oos", "LIQ-REV OOS"),
        ("liq_rev_fr_is", "LIQ-REV+FR IS"),
        ("liq_rev_fr_oos", "LIQ-REV+FR OOS"),
    ]:
        monthly = results[key].get("monthly_breakdown", {})
        if monthly:
            print(f"\n  {label_name}:")
            for month, stats in sorted(monthly.items()):
                print(f"    {month}: trades={stats['trades']}, win_rate={stats['win_rate']}%, "
                      f"pnl={stats['total_pnl']}")

    print("\n" + "=" * 80)
    print("BACKTEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()