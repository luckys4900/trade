# -*- coding: utf-8 -*-
"""
Kronos Strategy Backtest - Based on diagnosis findings
Edge: UP prediction + UPTREND = ~70% direction accuracy
Strategy: Go LONG only when Kronos predicts UP during UPTREND
"""

import sys, os, time, json
import numpy as np
import pandas as pd
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Kronos"))

import torch
from model import Kronos, KronosTokenizer, KronosPredictor

INITIAL_CASH = 200.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40

RSI_PERIOD = 14
ATR_PERIOD = 14
SL_ATR_MULT = 2.0
TP_ATR_MULT = 4.0
MAX_HOLD = 8

KRONOS_LOOKBACK = 400
KRONOS_PRED_LEN = 1
KRONOS_STEP = 2


@dataclass
class Trade:
    t_in: str; t_out: str; side: str; strat: str
    p_in: float; p_out: float; sz: float; pnl: float
    pnl_pct: float; reason: str; bars: int = 0


def compute_indicators(df):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    df["trend"] = "RANGE"
    df.loc[df["close"] > df["ma50"], "trend"] = "UPTREND"
    df.loc[df["close"] < df["ma50"], "trend"] = "DOWNTREND"
    df["vol_pct"] = df["close"].pct_change().abs().rolling(50).rank(pct=True) * 100
    return df


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
                if sz * px >= 10 and sz * px * (1 + COMM_PCT) <= cash:
                    cash -= sz * px * (1 + COMM_PCT)
                    in_pos = True; side = "LONG"; entry = px; ts_in = ts; bar_in = i
                    sz = sz; stop = px - sl_d
            elif signals[i] == -1:
                sl_d = SL_ATR_MULT * atr
                risk = cash * RISK_PCT
                sz = min(risk / sl_d, (cash * MAX_POS_PCT) / px)
                if sz * px >= 10 and sz * px * (1 + COMM_PCT) <= cash:
                    cash -= sz * px * (1 + COMM_PCT)
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


def main():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print("Device:", device)
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))

    print("Loading Kronos-base...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)
    print("Model ready")

    print("Loading BTC 4h data...")
    df = pd.read_csv("btc_usdt_4h_unified.csv", parse_dates=["datetime"], index_col="datetime").sort_index()
    df.columns = [c.lower() for c in df.columns]
    print("Data: {} -> {} ({} bars)".format(df.index[0], df.index[-1], len(df)))
    df = compute_indicators(df)

    # Strategy 1: Buy & Hold baseline
    bh_return = (df.iloc[-1]["close"] / df.iloc[KRONOS_LOOKBACK]["close"] - 1) * 100
    print("\nBuy & Hold return (from bar {}): {:.1f}%".format(KRONOS_LOOKBACK, bh_return))

    # Strategy 2: Current OCPM+MR (baseline from existing backtest)
    # We just reference the known result: +6.5% return, PF 1.23, WR 55.6%

    # Strategy 3: Kronos Trend Follower
    # LONG when: Kronos predicts UP + price above MA50 (UPTREND)
    # This uses the ~70% direction accuracy edge we found
    print("\n" + "=" * 70)
    print("  KRONOS TREND FOLLOWER")
    print("  Entry: Kronos UP prediction + UPTREND (price > MA50)")
    print("=" * 70)

    signals = np.zeros(len(df), dtype=int)
    last_pred_bar = -999
    total_preds = 0

    t_start = time.time()
    for i in range(KRONOS_LOOKBACK, len(df)):
        if i - last_pred_bar < KRONOS_STEP:
            continue
        last_pred_bar = i
        total_preds += 1

        try:
            start_idx = i - KRONOS_LOOKBACK
            x_df = df.iloc[start_idx:i][["open", "high", "low", "close", "volume"]].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(axis=1)
            x_ts = pd.Series(df.index[start_idx:i])
            future_idx = list(range(i, min(i + KRONOS_PRED_LEN, len(df))))
            if len(future_idx) < KRONOS_PRED_LEN:
                continue
            y_ts = pd.Series([df.index[j] for j in future_idx])

            pred_df = predictor.predict(
                df=x_df.reset_index(drop=True), x_timestamp=x_ts, y_timestamp=y_ts,
                pred_len=KRONOS_PRED_LEN, T=1.0, top_p=0.9, sample_count=5,
                verbose=False
            )

            prev_close = df.iloc[i - 1]["close"]
            pred_close = pred_df.iloc[0]["close"]
            pred_dir = 1 if pred_close > prev_close else -1
            trend = df.iloc[i]["trend"]
            rsi = df.iloc[i]["rsi"]

            if pred_dir == 1 and trend == "UPTREND" and 40 <= rsi < 65:
                signals[i] = 1
            elif pred_dir == -1 and trend == "DOWNTREND" and 35 < rsi <= 60:
                signals[i] = -1

        except Exception as e:
            if total_preds <= 3:
                print("  Error at bar {}: {}".format(i, e))
            continue

        if total_preds % 100 == 0:
            print("  Progress: {} predictions (bar {}/{})...".format(total_preds, i, len(df)))

    elapsed = time.time() - t_start
    print("Total predictions: {}, time: {:.0f}s".format(total_preds, elapsed))
    print("Signals: LONG={}, SHORT={}".format(sum(signals == 1), sum(signals == -1)))

    m3, t3 = run_backtest(df, signals, "Kronos_Trend")
    print_report(m3, "Kronos Trend Follower (UP+UPTREND / DOWN+DOWNTREND)")

    # Strategy 4: Kronos Trend - LONG ONLY (strongest edge: 70% on UP+UPTREND)
    print("\n" + "=" * 70)
    print("  KRONOS LONG-ONLY TREND FOLLOWER")
    print("  Entry: Kronos UP prediction + UPTREND only (best edge ~70%)")
    print("=" * 70)

    signals_lo = np.zeros(len(df), dtype=int)
    last_pred_bar = -999
    total_preds = 0

    t_start = time.time()
    for i in range(KRONOS_LOOKBACK, len(df)):
        if i - last_pred_bar < KRONOS_STEP:
            continue
        last_pred_bar = i
        total_preds += 1

        try:
            start_idx = i - KRONOS_LOOKBACK
            x_df = df.iloc[start_idx:i][["open", "high", "low", "close", "volume"]].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(axis=1)
            x_ts = pd.Series(df.index[start_idx:i])
            future_idx = list(range(i, min(i + KRONOS_PRED_LEN, len(df))))
            if len(future_idx) < KRONOS_PRED_LEN:
                continue
            y_ts = pd.Series([df.index[j] for j in future_idx])

            pred_df = predictor.predict(
                df=x_df.reset_index(drop=True), x_timestamp=x_ts, y_timestamp=y_ts,
                pred_len=KRONOS_PRED_LEN, T=1.0, top_p=0.9, sample_count=5,
                verbose=False
            )

            prev_close = df.iloc[i - 1]["close"]
            pred_close = pred_df.iloc[0]["close"]
            pred_dir = 1 if pred_close > prev_close else -1
            trend = df.iloc[i]["trend"]
            rsi = df.iloc[i]["rsi"]

            if pred_dir == 1 and trend == "UPTREND" and 35 <= rsi < 65:
                signals_lo[i] = 1

        except Exception as e:
            if total_preds <= 3:
                print("  Error at bar {}: {}".format(i, e))
            continue

        if total_preds % 100 == 0:
            print("  Progress: {} predictions (bar {}/{})...".format(total_preds, i, len(df)))

    elapsed = time.time() - t_start
    print("Total predictions: {}, time: {:.0f}s".format(total_preds, elapsed))
    print("Signals: LONG={}".format(sum(signals_lo == 1)))

    m4, t4 = run_backtest(df, signals_lo, "Kronos_LongOnly")
    print_report(m4, "Kronos Long-Only Trend (UP+UPTREND, RSI 35-65)")

    # Strategy 5: Tighter RSI filter
    print("\n" + "=" * 70)
    print("  KRONOS LONG-ONLY (RSI 40-60 tight)")
    print("=" * 70)

    signals_tight = np.zeros(len(df), dtype=int)
    last_pred_bar = -999
    total_preds = 0

    t_start = time.time()
    for i in range(KRONOS_LOOKBACK, len(df)):
        if i - last_pred_bar < KRONOS_STEP:
            continue
        last_pred_bar = i
        total_preds += 1

        try:
            start_idx = i - KRONOS_LOOKBACK
            x_df = df.iloc[start_idx:i][["open", "high", "low", "close", "volume"]].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(axis=1)
            x_ts = pd.Series(df.index[start_idx:i])
            future_idx = list(range(i, min(i + KRONOS_PRED_LEN, len(df))))
            if len(future_idx) < KRONOS_PRED_LEN:
                continue
            y_ts = pd.Series([df.index[j] for j in future_idx])

            pred_df = predictor.predict(
                df=x_df.reset_index(drop=True), x_timestamp=x_ts, y_timestamp=y_ts,
                pred_len=KRONOS_PRED_LEN, T=1.0, top_p=0.9, sample_count=5,
                verbose=False
            )

            prev_close = df.iloc[i - 1]["close"]
            pred_close = pred_df.iloc[0]["close"]
            pred_dir = 1 if pred_close > prev_close else -1
            trend = df.iloc[i]["trend"]
            rsi = df.iloc[i]["rsi"]

            if pred_dir == 1 and trend == "UPTREND" and 40 <= rsi < 60:
                signals_tight[i] = 1

        except Exception as e:
            continue

        if total_preds % 100 == 0:
            print("  Progress: {} predictions...".format(total_preds))

    elapsed = time.time() - t_start
    print("Total predictions: {}, time: {:.0f}s".format(total_preds, elapsed))
    print("Signals: LONG={}".format(sum(signals_tight == 1)))

    m5, t5 = run_backtest(df, signals_tight, "Kronos_Tight")
    print_report(m5, "Kronos Long-Only (UP+UPTREND, RSI 40-60 tight)")

    # Summary
    print("\n" + "=" * 70)
    print("  FINAL COMPARISON")
    print("=" * 70)
    print("  Buy & Hold:                  {:+.1f}%".format(bh_return))
    print("  Current OCPM+MR (existing):  +6.5% (PF 1.23, WR 55.6%)")
    print("  Kronos Long+Short:           {:+.1f}% (PF {:.2f}, WR {:.1f}%)".format(
        m3["total_return"], m3["profit_factor"], m3["win_rate"]))
    print("  Kronos Long-Only (RSI35-65): {:+.1f}% (PF {:.2f}, WR {:.1f}%)".format(
        m4["total_return"], m4["profit_factor"], m4["win_rate"]))
    print("  Kronos Long-Only (RSI40-60): {:+.1f}% (PF {:.2f}, WR {:.1f}%)".format(
        m5["total_return"], m5["profit_factor"], m5["win_rate"]))
    print("=" * 70)

    results = {
        "kronos_trend": m3,
        "kronos_long_only": m4,
        "kronos_tight": m5,
        "buy_hold_return": bh_return,
    }
    with open("kronos_strategy_backtest_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved.")


if __name__ == "__main__":
    main()
