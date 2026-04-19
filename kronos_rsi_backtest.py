# -*- coding: utf-8 -*-
"""
Kronos RSI Backtest - Compare:
  1. RSI-only (simple mean reversion)
  2. RSI + Kronos direction filter
  3. RSI + Kronos as primary signal (Kronos predicts reversal -> RSI confirms)
"""

import sys, os, time, json
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Kronos"))

INITIAL_CASH = 200.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40

RSI_PERIOD = 14
RSI_OVERSOLD = 35.0
RSI_OVERBOUGHT = 65.0
ATR_PERIOD = 14
SL_ATR_MULT = 2.0
TP_ATR_MULT = 4.0
MAX_HOLD = 12

KRONOS_LOOKBACK = 400
KRONOS_PRED_LEN = 6
KRONOS_STEP = 12


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
    df["rsi_prev"] = df["rsi"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/ATR_PERIOD, min_periods=ATR_PERIOD).mean()

    df["rsi_long"] = (
        (df["rsi_prev"] <= RSI_OVERSOLD) & (df["rsi"] > df["rsi_prev"])
    ).astype(int)
    df["rsi_short"] = (
        (df["rsi_prev"] >= RSI_OVERBOUGHT) & (df["rsi"] < df["rsi_prev"])
    ).astype(int)
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
                    in_pos = True
                    side = "LONG"
                    entry = px
                    ts_in = ts
                    bar_in = i
                    sz = sz
                    stop = px - sl_d
            elif signals[i] == -1:
                sl_d = SL_ATR_MULT * atr
                risk = cash * RISK_PCT
                sz = min(risk / sl_d, (cash * MAX_POS_PCT) / px)
                if sz * px >= 10 and sz * px * (1 + COMM_PCT) <= cash:
                    cash -= sz * px * (1 + COMM_PCT)
                    in_pos = True
                    side = "SHORT"
                    entry = px
                    ts_in = ts
                    bar_in = i
                    sz = sz
                    stop = px + sl_d

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
                "long_wr": 0, "short_wr": 0, "sl_rate": 0, "tp_rate": 0}
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
    }


def generate_rsi_signals(df):
    signals = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        if df.iloc[i]["rsi_long"] == 1:
            signals[i] = 1
        elif df.iloc[i]["rsi_short"] == 1:
            signals[i] = -1
    return signals


def generate_kronos_rsi_signals(df, predictor):
    from model import KronosPredictor
    signals = np.zeros(len(df), dtype=int)
    kronos_dir = np.zeros(len(df), dtype=int)
    last_pred_bar = -999

    print(f"Running Kronos predictions (every {KRONOS_STEP} bars, {KRONOS_PRED_LEN}-bar forecast)...")
    total_preds = 0

    for i in range(KRONOS_LOOKBACK, len(df)):
        if i - last_pred_bar < KRONOS_STEP:
            signals[i] = 0
            continue

        last_pred_bar = i
        total_preds += 1

        try:
            start_idx = i - KRONOS_LOOKBACK
            x_df = df.iloc[start_idx:i][["open", "high", "low", "close", "volume"]].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(axis=1)
            x_timestamp = pd.Series(df.index[start_idx:i])
            future_idx = list(range(i, min(i + KRONOS_PRED_LEN, len(df))))
            if len(future_idx) < KRONOS_PRED_LEN:
                continue
            y_timestamp = pd.Series([df.index[j] for j in future_idx])

            pred_df = predictor.predict(
                df=x_df.reset_index(drop=True), x_timestamp=x_timestamp, y_timestamp=y_timestamp,
                pred_len=KRONOS_PRED_LEN, T=1.0, top_p=0.9, sample_count=3,
                verbose=False
            )

            pred_close = pred_df["close"].values
            current_close = df.iloc[i]["close"]

            avg_pred = np.mean(pred_close)
            if avg_pred > current_close * 1.001:
                direction = 1
            elif avg_pred < current_close * 0.999:
                direction = -1
            else:
                direction = 0

            for j in range(min(KRONOS_PRED_LEN, len(df) - i)):
                kronos_dir[i + j] = direction

        except Exception as e:
            if total_preds <= 3:
                print(f"  Prediction error at bar {i}: {e}")
            continue

        if total_preds % 20 == 0:
            print(f"  Processed {total_preds} predictions (bar {i}/{len(df)})...")

    print(f"Total Kronos predictions: {total_preds}")

    for i in range(len(df)):
        r = df.iloc[i]
        if r["rsi_long"] == 1 and kronos_dir[i] == 1:
            signals[i] = 1
        elif r["rsi_short"] == 1 and kronos_dir[i] == -1:
            signals[i] = -1

    return signals


def generate_kronos_primary_signals(df, predictor):
    signals = np.zeros(len(df), dtype=int)
    kronos_dir = np.zeros(len(df), dtype=int)
    last_pred_bar = -999
    total_preds = 0

    print(f"Running Kronos-primary predictions...")

    for i in range(KRONOS_LOOKBACK, len(df)):
        if i - last_pred_bar < KRONOS_STEP:
            signals[i] = 0
            continue

        last_pred_bar = i
        total_preds += 1

        try:
            start_idx = i - KRONOS_LOOKBACK
            x_df = df.iloc[start_idx:i][["open", "high", "low", "close", "volume"]].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open", "high", "low", "close"]].mean(axis=1)
            x_timestamp = pd.Series(df.index[start_idx:i])
            future_idx = list(range(i, min(i + KRONOS_PRED_LEN, len(df))))
            if len(future_idx) < KRONOS_PRED_LEN:
                continue
            y_timestamp = pd.Series([df.index[j] for j in future_idx])

            pred_df = predictor.predict(
                df=x_df.reset_index(drop=True), x_timestamp=x_timestamp, y_timestamp=y_timestamp,
                pred_len=KRONOS_PRED_LEN, T=1.0, top_p=0.9, sample_count=3,
                verbose=False
            )

            pred_close = pred_df["close"].values
            current_close = df.iloc[i]["close"]
            rsi = df.iloc[i]["rsi"]

            avg_pred = np.mean(pred_close)
            first_pred = pred_close[0]
            pred_trend = first_pred - current_close

            if avg_pred > current_close * 1.002 and pred_trend > 0:
                direction = 1
            elif avg_pred < current_close * 0.998 and pred_trend < 0:
                direction = -1
            else:
                direction = 0

            for j in range(min(KRONOS_PRED_LEN, len(df) - i)):
                kronos_dir[i + j] = direction

        except Exception as e:
            if total_preds <= 3:
                print(f"  Prediction error at bar {i}: {e}")
            continue

        if total_preds % 20 == 0:
            print(f"  Processed {total_preds} predictions (bar {i}/{len(df)})...")

    print(f"Total Kronos predictions: {total_preds}")

    for i in range(len(df)):
        r = df.iloc[i]
        rsi = r["rsi"]
        rsi_prev = r["rsi_prev"]
        if kronos_dir[i] == 1 and rsi < 50 and rsi > rsi_prev:
            signals[i] = 1
        elif kronos_dir[i] == -1 and rsi > 50 and rsi < rsi_prev:
            signals[i] = -1

    return signals


def print_report(m, label):
    print(f"""
{'='*65}
  {label}
{'='*65}
  Final Value    : ${m['final_value']:,.2f}
  Total Return   : {m['total_return']:+.2f}%
  Max Drawdown   : {m['max_drawdown']:.2f}%
  Sharpe (ann.)  : {m['sharpe']:.4f}
{'-'*65}
  Trades         : {m['total_trades']}
  Win Rate       : {m['win_rate']:.1f}%
  Profit Factor  : {m['profit_factor']:.2f}
  Avg PnL        : ${m['avg_pnl']:+,.2f}
{'-'*65}
  LONG           : {m['long_trades']} (WR {m['long_wr']:.0f}%)
  SHORT          : {m['short_trades']} (WR {m['short_wr']:.0f}%)
{'-'*65}
  TP rate        : {m['tp_rate']:.1f}%
  Stop Loss rate : {m['sl_rate']:.1f}%
{'='*65}""")


def main():
    print("Loading BTC 4h data...")
    df = pd.read_csv("btc_usdt_4h_unified.csv", parse_dates=["datetime"], index_col="datetime").sort_index()
    df.columns = [c.lower() for c in df.columns]
    print(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")

    df = compute_indicators(df)

    print("\n" + "=" * 65)
    print("  STRATEGY 1: RSI Only (Mean Reversion)")
    print("=" * 65)
    rsi_signals = generate_rsi_signals(df)
    print(f"RSI signals: LONG={sum(rsi_signals==1)}, SHORT={sum(rsi_signals==-1)}")
    m1, t1 = run_backtest(df, rsi_signals, "RSI_Only")
    print_report(m1, "RSI Only (Mean Reversion)")

    import torch
    has_cuda = torch.cuda.is_available()
    device = "cuda:0" if has_cuda else "cpu"
    print(f"\n{'='*65}")
    print(f"  GPU: {torch.cuda.get_device_name(0) if has_cuda else 'CPU only'}")
    print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory/1024**3:.1f} GB" if has_cuda else "")
    print(f"{'='*65}")

    from model import Kronos, KronosTokenizer, KronosPredictor
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)
    total_params = sum(p.numel() for p in model.parameters())
    gpu_mem = torch.cuda.memory_allocated()/1024**3 if has_cuda else 0
    print(f"Kronos-base ({total_params/1e6:.1f}M params) ready on {device}")
    if has_cuda:
        print(f"GPU memory: {gpu_mem:.2f} GB")

    print("\n" + "=" * 65)
    print("  STRATEGY 2: RSI + Kronos Filter")
    print("=" * 65)
    t_start = time.time()
    filtered_signals = generate_kronos_rsi_signals(df, predictor)
    elapsed = time.time() - t_start
    print(f"Kronos filter signals: LONG={sum(filtered_signals==1)}, SHORT={sum(filtered_signals==-1)}")
    print(f"Prediction time: {elapsed:.0f}s")
    m2, t2 = run_backtest(df, filtered_signals, "RSI_Kronos_Filter")
    print_report(m2, "RSI + Kronos Filter")

    print("\n" + "=" * 65)
    print("  STRATEGY 3: Kronos Primary + RSI Confirm")
    print("=" * 65)
    t_start = time.time()
    primary_signals = generate_kronos_primary_signals(df, predictor)
    elapsed = time.time() - t_start
    print(f"Kronos primary signals: LONG={sum(primary_signals==1)}, SHORT={sum(primary_signals==-1)}")
    print(f"Prediction time: {elapsed:.0f}s")
    m3, t3 = run_backtest(df, primary_signals, "Kronos_Primary_RSI")
    print_report(m3, "Kronos Primary + RSI Confirm")

    print("\n" + "=" * 65)
    print("  COMPARISON SUMMARY")
    print("=" * 65)
    print(f"  {'Metric':<20} {'RSI Only':>12} {'RSI+Kronos':>12} {'Kronos+RSI':>12}")
    print(f"  {'-'*56}")
    for key in ["total_return", "win_rate", "profit_factor", "max_drawdown", "sharpe", "total_trades", "tp_rate", "sl_rate"]:
        vals = []
        for m in [m1, m2, m3]:
            v = m[key]
            if key in ["total_return", "win_rate", "max_drawdown", "tp_rate", "sl_rate"]:
                vals.append(f"{v:+.1f}%")
            elif key == "sharpe":
                vals.append(f"{v:.3f}")
            elif key == "profit_factor":
                vals.append(f"{v:.2f}")
            else:
                vals.append(f"{v:.0f}")
        print(f"  {key:<20} {vals[0]:>12} {vals[1]:>12} {vals[2]:>12}")
    print("=" * 65)

    results = {
        "RSI_Only": m1,
        "RSI_Kronos_Filter": m2,
        "Kronos_Primary_RSI": m3
    }
    with open("kronos_backtest_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to kronos_backtest_results.json")


if __name__ == "__main__":
    main()
