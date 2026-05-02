# -*- coding: utf-8 -*-
"""
Triple Top Strategy Backtest
Pine Script移植: 同一価格帯で高値3回形成、出来高増加、BB突破でロングエントリー
"""

import sys, os, json, argparse
import numpy as np
import pandas as pd
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(__file__))

from indicators.triple_top import TripleTopIndicator

INITIAL_CASH = 200.0
COMM_PCT = 0.00035
SLIPPAGE_PCT = 0.001
RISK_PCT = 0.02
MAX_POS_PCT = 0.40

ATR_PERIOD = 14
SL_ATR_MULT = 2.5
TP_ATR_MULT = 4.0
MAX_HOLD = 15


@dataclass
class Trade:
    t_in: str; t_out: str; side: str; strat: str
    p_in: float; p_out: float; sz: float; pnl: float
    pnl_pct: float; reason: str; bars: int = 0


def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG":
        return (exit_px - entry) * sz - notional * comm
    else:
        return (entry - exit_px) * sz - notional * comm


def run_backtest(df, signals, label):
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    in_pos = False
    side = ""
    entry = 0.0
    ts_in = ""
    bar_in = 0
    sz = 0.0
    stop = 0.0

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px, hi, lo, atr = r["close"], r["high"], r["low"], r["atr"]

        pv = 0
        if in_pos:
            pv = sz * px if side == "LONG" else sz * (2 * entry - px)
        equity = cash + pv
        peak_eq = max(peak_eq, equity)
        eq.append(equity)

        if in_pos:
            held = i - bar_in
            if held >= MAX_HOLD:
                pnl = _pnl(side, entry, px, sz, COMM_PCT)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, side, label, entry, px, sz, pnl,
                                    (px / entry - 1) * 100 * (1 if side == "LONG" else -1),
                                    "TIME_EXIT", held))
                in_pos = False
            elif atr and atr > 0:
                if side == "LONG":
                    if lo <= stop:
                        pnl = _pnl("LONG", entry, stop, sz, COMM_PCT)
                        cash += sz * entry + pnl
                        trades.append(Trade(ts_in, ts, "LONG", label, entry, stop, sz, pnl,
                                            (stop / entry - 1) * 100, "STOP_LOSS", held))
                        in_pos = False
                    else:
                        tp = entry + TP_ATR_MULT * atr
                        if hi >= tp:
                            pnl = _pnl("LONG", entry, tp, sz, COMM_PCT)
                            cash += sz * entry + pnl
                            trades.append(Trade(ts_in, ts, "LONG", label, entry, tp, sz, pnl,
                                                (tp / entry - 1) * 100, "TP", held))
                            in_pos = False
                else:
                    if hi >= stop:
                        pnl = _pnl("SHORT", entry, stop, sz, COMM_PCT)
                        cash += sz * entry + pnl
                        trades.append(Trade(ts_in, ts, "SHORT", label, entry, stop, sz, pnl,
                                            (entry / stop - 1) * 100, "STOP_LOSS", held))
                        in_pos = False
                    else:
                        tp = entry - TP_ATR_MULT * atr
                        if lo <= tp:
                            pnl = _pnl("SHORT", entry, tp, sz, COMM_PCT)
                            cash += sz * entry + pnl
                            trades.append(Trade(ts_in, ts, "SHORT", label, entry, tp, sz, pnl,
                                                (entry / tp - 1) * 100, "TP", held))
                            in_pos = False

        if not in_pos and atr and atr > 0:
            if signals[i] == 1:
                sl_d = SL_ATR_MULT * atr
                risk = cash * RISK_PCT
                sz = min(risk / sl_d, (cash * MAX_POS_PCT) / px)
                if sz * px >= 10 and sz * px * (1 + COMM_PCT + SLIPPAGE_PCT) <= cash:
                    cash -= sz * px * (1 + COMM_PCT + SLIPPAGE_PCT)
                    in_pos = True; side = "LONG"; entry = px; ts_in = ts; bar_in = i
                    sz = sz; stop = px - sl_d
            elif signals[i] == -1:
                sl_d = SL_ATR_MULT * atr
                risk = cash * RISK_PCT
                sz = min(risk / sl_d, (cash * MAX_POS_PCT) / px)
                if sz * px >= 10 and sz * px * (1 + COMM_PCT + SLIPPAGE_PCT) <= cash:
                    cash -= sz * px * (1 + COMM_PCT + SLIPPAGE_PCT)
                    in_pos = True; side = "SHORT"; entry = px; ts_in = ts; bar_in = i
                    sz = sz; stop = px + sl_d

    if in_pos:
        lp = df.iloc[-1]["close"]
        pnl = _pnl(side, entry, lp, sz, COMM_PCT)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, str(df.index[-1]), side, label, entry, lp, sz, pnl, 0, "EOD", 0))

    return _calc_metrics(cash, trades, eq), trades


def _calc_metrics(final, trades, eq):
    init = INITIAL_CASH
    ret = (final - init) / init * 100
    n = len(trades)
    if n == 0:
        return {"final_value": final, "total_return": ret, "total_trades": 0,
                "win_rate": 0, "profit_factor": 0, "max_drawdown": 0, "sharpe": 0,
                "avg_pnl": 0, "long_trades": 0, "short_trades": 0,
                "long_wr": 0, "short_wr": 0, "sl_rate": 0, "tp_rate": 0,
                "expectancy": 0}
    pnls = [t.pnl for t in trades]
    w = [p for p in pnls if p > 0]
    l = [p for p in pnls if p <= 0]
    gp, gl = sum(w), abs(sum(l))
    eq_arr = np.array(eq)
    pk = np.maximum.accumulate(eq_arr)
    mdd = float(((pk - eq_arr) / pk * 100).max())
    deq = eq_arr[::6]
    sharpe = 0
    if len(deq) > 1:
        dr = np.diff(deq) / deq[:-1]
        rf = 0.045 / 365
        sharpe = float((np.mean(dr) - rf) / np.std(dr) * np.sqrt(365)) if np.std(dr) > 0 else 0
    longs = [t for t in trades if t.side == "LONG"]
    shorts = [t for t in trades if t.side == "SHORT"]
    lw = sum(1 for t in longs if t.pnl > 0)
    sw = sum(1 for t in shorts if t.pnl > 0)
    return {
        "final_value": final, "total_return": ret, "total_trades": n,
        "win_rate": len(w) / n * 100,
        "profit_factor": gp / gl if gl > 0 else float("inf"),
        "max_drawdown": mdd, "sharpe": sharpe,
        "avg_pnl": np.mean(pnls),
        "long_trades": len(longs), "short_trades": len(shorts),
        "long_wr": lw / len(longs) * 100 if longs else 0,
        "short_wr": sw / len(shorts) * 100 if shorts else 0,
        "sl_rate": sum(1 for t in trades if "STOP" in t.reason) / n * 100,
        "tp_rate": sum(1 for t in trades if "TP" in t.reason) / n * 100,
        "expectancy": np.mean(pnls),
    }


def print_report(m, label):
    print("""
===================================================================
   {}
===================================================================
   Final Value    : ${:,.2f}
   Total Return   : {:+.2f}%
   Max Drawdown   : {:.2f}%
   Sharpe (ann.)  : {:.4f}
-------------------------------------------------------------------
   Trades         : {}
   Win Rate       : {:.1f}%
   Profit Factor  : {:.2f}
   Expectancy     : ${:+,.2f}
-------------------------------------------------------------------
   LONG           : {} (WR {:.0f}%)
   SHORT          : {} (WR {:.0f}%)
-------------------------------------------------------------------
   TP rate        : {:.1f}%
   Stop Loss rate : {:.1f}%
===================================================================""".format(
        label, m["final_value"], m["total_return"], m["max_drawdown"], m["sharpe"],
        m["total_trades"], m["win_rate"], m["profit_factor"], m["expectancy"],
        m["long_trades"], m["long_wr"], m["short_trades"], m["short_wr"],
        m["tp_rate"], m["sl_rate"]))


def run_window_backtest(df, signals, label, start=None, end=None):
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= df.index >= pd.Timestamp(start)
    if end is not None:
        mask &= df.index < pd.Timestamp(end)
    sub_df = df.loc[mask]
    if sub_df.empty:
        raise ValueError("No rows available for window {} -> {}".format(start, end))
    sub_signals = signals[mask.to_numpy()]
    metrics, _ = run_backtest(sub_df, sub_signals, label)
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Triple Top Strategy Backtest")
    parser.add_argument("--data", default="btc_usdt_4h_unified.csv",
                        help="Path to BTC 4h OHLCV data file")
    parser.add_argument("--output", default="triple_top_results.json",
                        help="Path to output JSON file")
    parser.add_argument("--split-date", default="2025-04-01 00:00:00",
                        help="Date to split in-sample/out-of-sample")
    parser.add_argument("--recent-months", type=int, default=6,
                        help="Number of recent months for additional test")
    parser.add_argument("--pivot-length", type=int, default=7,
                        help="Pivot length for pattern detection")
    parser.add_argument("--price-tolerance", type=float, default=0.015,
                        help="Price tolerance (1.5% = 0.015)")
    parser.add_argument("--min-high-count", type=int, default=3,
                        help="Minimum number of highs for triple top")
    parser.add_argument("--bb-period", type=int, default=20,
                        help="Bollinger Bands period")
    parser.add_argument("--bb-std", type=float, default=1.8,
                        help="Bollinger Bands standard deviation")
    parser.add_argument("--atr-period", type=int, default=14,
                        help="ATR period")
    parser.add_argument("--sl-atr-mult", type=float, default=2.5,
                        help="Stop Loss ATR multiplier")
    parser.add_argument("--tp-atr-mult", type=float, default=4.0,
                        help="Take Profit ATR multiplier")
    parser.add_argument("--max-hold", type=int, default=15,
                        help="Maximum holding period in bars")
    parser.add_argument("--volume-mult", type=float, default=2.5,
                        help="Volume multiplier threshold")
    parser.add_argument("--regime-lookback", type=int, default=50,
                        help="Volatility regime lookback period")
    parser.add_argument("--vol-pct-min", type=int, default=30,
                        help="Volatility percentile minimum")
    parser.add_argument("--vol-pct-max", type=int, default=90,
                        help="Volatility percentile maximum")
    args = parser.parse_args()

    global SL_ATR_MULT, TP_ATR_MULT, MAX_HOLD
    SL_ATR_MULT = args.sl_atr_mult
    TP_ATR_MULT = args.tp_atr_mult
    MAX_HOLD = args.max_hold

    print("Loading BTC 4h data from {}...".format(args.data))
    df = pd.read_csv(args.data, parse_dates=["datetime"], index_col="datetime").sort_index()
    df.columns = [c.lower() for c in df.columns]
    print("Data: {} -> {} ({} bars)".format(df.index[0], df.index[-1], len(df)))

    print("\nInitializing Triple Top Indicator...")
    indicator = TripleTopIndicator(
        pivot_length=args.pivot_length,
        price_tolerance=args.price_tolerance,
        min_high_count=args.min_high_count,
        bb_period=args.bb_period,
        bb_std=args.bb_std,
        atr_period=args.atr_period,
        volume_mult=args.volume_mult,
        regime_lookback=args.regime_lookback,
        vol_pct_min=args.vol_pct_min,
        vol_pct_max=args.vol_pct_max
    )

    print("Detecting triple top patterns...")
    df, signals = indicator.detect_triple_top(df)
    print("Signals: LONG={}, SHORT={}".format(sum(signals == 1), sum(signals == -1)))

    print("\nRunning backtest on full period...")
    metrics_full, trades = run_backtest(df, signals, "TripleTop")
    print_report(metrics_full, "Triple Top Strategy (Full Period)")

    split_date = pd.Timestamp(args.split_date)
    print("\nRunning in-sample (before {})...".format(split_date))
    metrics_is = run_window_backtest(df, signals, "TripleTop_IS", end=split_date)
    print_report(metrics_is, "In-Sample")

    print("\nRunning out-of-sample (after {})...".format(split_date))
    metrics_oos = run_window_backtest(df, signals, "TripleTop_OOS", start=split_date)
    print_report(metrics_oos, "Out-of-Sample")

    if args.recent_months > 0:
        print("\nRunning recent {} months...".format(args.recent_months))
        recent_start = df.index.max() - pd.DateOffset(months=args.recent_months)
        metrics_recent = run_window_backtest(df, signals, "TripleTop_Recent", start=recent_start)
        print_report(metrics_recent, "Recent {}m".format(args.recent_months))

    print("\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    print("  {:<24} {:>10} {:>8} {:>8} {:>8}".format("Period", "Return", "PF", "WR", "MDD"))
    print("  " + "-" * 70)
    print("  {:<24} {:>+9.1f}% {:>8.2f} {:>7.1f}% {:>7.1f}%".format(
        "Full Period", metrics_full["total_return"], metrics_full["profit_factor"],
        metrics_full["win_rate"], metrics_full["max_drawdown"]))
    print("  {:<24} {:>+9.1f}% {:>8.2f} {:>7.1f}% {:>7.1f}%".format(
        "In-Sample", metrics_is["total_return"], metrics_is["profit_factor"],
        metrics_is["win_rate"], metrics_is["max_drawdown"]))
    print("  {:<24} {:>+9.1f}% {:>8.2f} {:>7.1f}% {:>7.1f}%".format(
        "Out-of-Sample", metrics_oos["total_return"], metrics_oos["profit_factor"],
        metrics_oos["win_rate"], metrics_oos["max_drawdown"]))
    if args.recent_months > 0:
        print("  {:<24} {:>+9.1f}% {:>8.2f} {:>7.1f}% {:>7.1f}%".format(
            "Recent {}m".format(args.recent_months), metrics_recent["total_return"],
            metrics_recent["profit_factor"], metrics_recent["win_rate"],
            metrics_recent["max_drawdown"]))
    print("=" * 78)

    results = {
        "config": {
            "data_file": args.data,
            "split_date": args.split_date,
            "pivot_length": args.pivot_length,
            "price_tolerance": args.price_tolerance,
            "min_high_count": args.min_high_count,
            "bb_period": args.bb_period,
            "bb_std": args.bb_std,
            "atr_period": args.atr_period,
            "sl_atr_mult": args.sl_atr_mult,
            "tp_atr_mult": args.tp_atr_mult,
            "max_hold_bars": args.max_hold,
            "volume_mult": args.volume_mult,
            "regime_lookback": args.regime_lookback,
            "initial_cash": INITIAL_CASH,
            "commission": COMM_PCT,
            "slippage": SLIPPAGE_PCT,
            "risk_per_trade": RISK_PCT,
            "max_position_pct": MAX_POS_PCT,
        },
        "full_period": metrics_full,
        "in_sample": metrics_is,
        "out_of_sample": metrics_oos,
    }
    if args.recent_months > 0:
        results["recent_months"] = metrics_recent

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print("\nResults saved to {}".format(args.output))


if __name__ == "__main__":
    main()
