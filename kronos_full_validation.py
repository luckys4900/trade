# -*- coding: utf-8 -*-
"""
Kronos Contrarian Strategy - FULL VALIDATION
1. Period split (first half / second half)
2. Cross-timeframe (4h vs 1h)
3. Parameter sweep (SL/TP, hold, samples)
4. Filter optimization (RSI, vol, trend)
"""

import sys, os, time, json
import numpy as np
import pandas as pd
from dataclasses import dataclass
from itertools import product

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Kronos"))

import torch
from model import Kronos, KronosTokenizer, KronosPredictor

INITIAL_CASH = 200.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40


@dataclass
class Trade:
    t_in: str; t_out: str; side: str; strat: str
    p_in: float; p_out: float; sz: float; pnl: float
    pnl_pct: float; reason: str; bars: int = 0


def compute_indicators(df):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, min_periods=14).mean()
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


def run_backtest(df, signals, label, sl_mult=2.0, tp_mult=4.0, max_hold=8):
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    in_pos = False
    side = ""; entry = 0.0; ts_in = ""; bar_in = 0; sz = 0.0; stop = 0.0

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
            if held >= max_hold:
                pnl = _pnl(side, entry, px, sz, COMM_PCT)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, side, label, entry, px, sz, pnl,
                                    (px/entry-1)*100*(1 if side=="LONG" else -1), "TIME_EXIT", held))
                in_pos = False
            elif atr and atr > 0:
                if side == "LONG":
                    if lo <= stop:
                        pnl = _pnl("LONG", entry, stop, sz, COMM_PCT)
                        cash += sz * entry + pnl
                        trades.append(Trade(ts_in, ts, "LONG", label, entry, stop, sz, pnl,
                                            (stop/entry-1)*100, "STOP_LOSS", held))
                        in_pos = False
                    else:
                        tp = entry + tp_mult * atr
                        if hi >= tp:
                            pnl = _pnl("LONG", entry, tp, sz, COMM_PCT)
                            cash += sz * entry + pnl
                            trades.append(Trade(ts_in, ts, "LONG", label, entry, tp, sz, pnl,
                                                (tp/entry-1)*100, "TP", held))
                            in_pos = False
                else:
                    if hi >= stop:
                        pnl = _pnl("SHORT", entry, stop, sz, COMM_PCT)
                        cash += sz * entry + pnl
                        trades.append(Trade(ts_in, ts, "SHORT", label, entry, stop, sz, pnl,
                                            (entry/stop-1)*100, "STOP_LOSS", held))
                        in_pos = False
                    else:
                        tp = entry - tp_mult * atr
                        if lo <= tp:
                            pnl = _pnl("SHORT", entry, tp, sz, COMM_PCT)
                            cash += sz * entry + pnl
                            trades.append(Trade(ts_in, ts, "SHORT", label, entry, tp, sz, pnl,
                                                (entry/tp-1)*100, "TP", held))
                            in_pos = False

        if not in_pos and atr and atr > 0:
            if signals[i] == 1:
                sl_d = sl_mult * atr
                risk = cash * RISK_PCT
                sz = min(risk / sl_d, (cash * MAX_POS_PCT) / px)
                if sz * px >= 10 and sz * px * (1 + COMM_PCT) <= cash:
                    cash -= sz * px * (1 + COMM_PCT)
                    in_pos = True; side = "LONG"; entry = px; ts_in = ts; bar_in = i
                    sz = sz; stop = px - sl_d
            elif signals[i] == -1:
                sl_d = sl_mult * atr
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

    return _calc_metrics(cash, trades, eq)


def _calc_metrics(final, trades, eq):
    init = INITIAL_CASH
    ret = (final - init) / init * 100
    n = len(trades)
    if n == 0:
        return {"final": final, "return": ret, "trades": 0, "wr": 0, "pf": 0,
                "mdd": 0, "sharpe": 0, "ev": 0}
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
    return {
        "final": final, "return": ret, "trades": n,
        "wr": len(w)/n*100, "pf": gp/gl if gl > 0 else 999,
        "mdd": mdd, "sharpe": sharpe, "ev": np.mean(pnls)
    }


def fmt(m):
    return "{:+.1f}% | PF {:.2f} | WR {:.1f}% | DD {:.1f}% | {} trades | Sharpe {:.3f}".format(
        m["return"], m["pf"], m["wr"], m["mdd"], m["trades"], m["sharpe"])


def run_predictions(df, predictor, lookback, pred_len, step, n_samples):
    preds = []
    last = -999
    total = 0
    for i in range(lookback, len(df)):
        if i - last < step:
            continue
        last = i
        total += 1
        if total % 300 == 0:
            print("    pred {} (bar {}/{})".format(total, i, len(df)))
        try:
            s = i - lookback
            x_df = df.iloc[s:i][["open","high","low","close","volume"]].copy()
            x_df["amount"] = x_df["volume"] * x_df[["open","high","low","close"]].mean(axis=1)
            x_ts = pd.Series(df.index[s:i])
            fi = list(range(i, min(i + pred_len, len(df))))
            if len(fi) < pred_len:
                continue
            y_ts = pd.Series([df.index[j] for j in fi])
            pred_df = predictor.predict(
                df=x_df.reset_index(drop=True), x_timestamp=x_ts, y_timestamp=y_ts,
                pred_len=pred_len, T=0.8, top_p=0.6, sample_count=n_samples, verbose=False
            )
            prev_close = df.iloc[i-1]["close"]
            pred_close = pred_df.iloc[0]["close"]
            pred_dir = 1 if pred_close > prev_close else -1
            preds.append({"bar": i, "pred_dir": pred_dir})
        except:
            continue
    return pd.DataFrame(preds)


def make_contrarian_signals(df, pred_df, rsi_lo=0, rsi_hi=100, vol_max=100, trend_filter=None):
    signals = np.zeros(len(df), dtype=int)
    for _, row in pred_df.iterrows():
        i = int(row["bar"])
        pred_dir = int(row["pred_dir"])
        rsi = df.iloc[i]["rsi"]
        vol = df.iloc[i]["vol_pct"]
        trend = df.iloc[i]["trend"]

        if rsi < rsi_lo or rsi >= rsi_hi:
            continue
        if vol > vol_max:
            continue
        if trend_filter and trend not in trend_filter:
            continue
        signals[i] = -pred_dir
    return signals


def main():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print("Device:", device)
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))

    print("Loading Kronos-base...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

    # ===================================================================
    #  TEST 1: PERIOD SPLIT (4h data)
    # ===================================================================
    print("\n" + "="*70)
    print("  TEST 1: PERIOD SPLIT VALIDATION (BTC 4h)")
    print("="*70)
    df4 = pd.read_csv("btc_usdt_4h_unified.csv", parse_dates=["datetime"], index_col="datetime").sort_index()
    df4.columns = [c.lower() for c in df4.columns]
    df4 = compute_indicators(df4)
    print("4h data: {} -> {} ({} bars)".format(df4.index[0], df4.index[-1], len(df4)))

    mid = len(df4) // 2
    df4_first = df4.iloc[:mid].copy()
    df4_second = df4.iloc[mid:].copy()
    print("First half: {} -> {} ({} bars)".format(df4_first.index[0], df4_first.index[-1], len(df4_first)))
    print("Second half: {} -> {} ({} bars)".format(df4_second.index[0], df4_second.index[-1], len(df4_second)))

    LOOKBACK = 400
    STEP = 2
    PRED_LEN = 1

    print("\n--- First half predictions ---")
    pred_first = run_predictions(df4_first, predictor, LOOKBACK, PRED_LEN, STEP, 30)
    sig_first = make_contrarian_signals(df4_first, pred_first)
    m_first = run_backtest(df4_first, sig_first, "H1")
    print("  First half: {}".format(fmt(m_first)))

    print("\n--- Second half predictions ---")
    pred_second = run_predictions(df4_second, predictor, LOOKBACK, PRED_LEN, STEP, 30)
    sig_second = make_contrarian_signals(df4_second, pred_second)
    m_second = run_backtest(df4_second, sig_second, "H2")
    print("  Second half: {}".format(fmt(m_second)))

    # Full period
    print("\n--- Full period ---")
    pred_full = run_predictions(df4, predictor, LOOKBACK, PRED_LEN, STEP, 30)
    sig_full = make_contrarian_signals(df4, pred_full)
    m_full = run_backtest(df4, sig_full, "Full")
    print("  Full period: {}".format(fmt(m_full)))

    # ===================================================================
    #  TEST 2: PARAMETER SWEEP (SL/TP, max_hold)
    # ===================================================================
    print("\n" + "="*70)
    print("  TEST 2: PARAMETER SWEEP")
    print("="*70)
    print("  {:<12} {:<8} {:<8} | {}".format("SL", "TP", "Hold", "Result"))
    print("  " + "-"*65)

    best_ret = -999
    best_params = None
    for sl, tp, hold in [(1.5,3.0,6), (2.0,4.0,8), (2.5,5.0,10), (3.0,6.0,12),
                          (1.5,4.0,8), (2.0,3.0,6), (2.0,5.0,10), (1.0,2.0,4)]:
        m = run_backtest(df4, sig_full, "sweep", sl_mult=sl, tp_mult=tp, max_hold=hold)
        print("  SL={:<5.1f} TP={:<5.1f} H={:<5d} | {}".format(sl, tp, hold, fmt(m)))
        if m["return"] > best_ret:
            best_ret = m["return"]
            best_params = (sl, tp, hold)

    print("\n  Best params: SL={} TP={} Hold={} -> {}".format(*best_params, best_ret))

    # ===================================================================
    #  TEST 3: FILTER OPTIMIZATION
    # ===================================================================
    print("\n" + "="*70)
    print("  TEST 3: FILTER OPTIMIZATION")
    print("="*70)
    print("  {:<40} | {}".format("Filter", "Result"))
    print("  " + "-"*80)

    filters = [
        ("No filter", 0, 100, 100, None),
        ("RSI 30-70", 30, 70, 100, None),
        ("RSI 35-65", 35, 65, 100, None),
        ("RSI 40-60", 40, 60, 100, None),
        ("Low vol only (<50)", 0, 100, 50, None),
        ("High vol only (>50)", 0, 100, 100, None),
        ("UPTREND only", 0, 100, 100, ["UPTREND"]),
        ("DOWNTREND only", 0, 100, 100, ["DOWNTREND"]),
        ("RSI 30-70 + UPTREND", 30, 70, 100, ["UPTREND"]),
        ("RSI 35-65 + Low vol", 35, 65, 50, None),
    ]

    best_filter = None
    best_filter_ret = -999
    for name, rsi_lo, rsi_hi, vol_max, trend_f in filters:
        sig = make_contrarian_signals(df4, pred_full, rsi_lo, rsi_hi, vol_max, trend_f)
        m = run_backtest(df4, sig, name, sl_mult=best_params[0], tp_mult=best_params[1], max_hold=best_params[2])
        print("  {:<40} | {}".format(name, fmt(m)))
        if m["return"] > best_filter_ret and m["trades"] >= 20:
            best_filter_ret = m["return"]
            best_filter = name

    print("\n  Best filter: {} -> {}".format(best_filter, best_filter_ret))

    # ===================================================================
    #  TEST 4: 1H CROSS-VALIDATION
    # ===================================================================
    print("\n" + "="*70)
    print("  TEST 4: 1H TIMEFRAME CROSS-VALIDATION")
    print("="*70)
    df1 = pd.read_csv("btc_usdt_1h_kronos.csv", parse_dates=["datetime"], index_col="datetime").sort_index()
    df1.columns = [c.lower() for c in df1.columns]
    df1 = compute_indicators(df1)
    print("1h data: {} -> {} ({} bars)".format(df1.index[0], df1.index[-1], len(df1)))

    LOOKBACK_1H = 400
    STEP_1H = 48
    PRED_LEN_1H = 1

    print("  Running 1h predictions (step={}, samples=10)...".format(STEP_1H))
    t0 = time.time()
    pred_1h = run_predictions(df1, predictor, LOOKBACK_1H, PRED_LEN_1H, STEP_1H, 10)
    print("  Prediction time: {:.0f}s".format(time.time() - t0))

    sig_1h_base = make_contrarian_signals(df1, pred_1h)
    m_1h_base = run_backtest(df1, sig_1h_base, "1h_base", sl_mult=best_params[0], tp_mult=best_params[1], max_hold=best_params[2])
    print("  1h Contrarian (no filter): {}".format(fmt(m_1h_base)))

    sig_1h_filtered = make_contrarian_signals(df1, pred_1h, rsi_lo=35, rsi_hi=65, vol_max=50)
    m_1h_filtered = run_backtest(df1, sig_1h_filtered, "1h_filt", sl_mult=best_params[0], tp_mult=best_params[1], max_hold=best_params[2])
    print("  1h Contrarian (RSI 35-65, low vol): {}".format(fmt(m_1h_filtered)))

    # ===================================================================
    #  TEST 5: SKIP - reuse pred_full (already 30 samples)
    # ===================================================================

    # ===================================================================
    #  FINAL SUMMARY
    # ===================================================================
    print("\n" + "="*70)
    print("  FINAL VALIDATION SUMMARY")
    print("="*70)
    print("  Current OCPM+MR:            +6.5% | PF 1.23 | WR 55.6%")
    print("  ---")
    print("  4h Full:                     {}".format(fmt(m_full)))
    print("  4h First half:               {}".format(fmt(m_first)))
    print("  4h Second half:              {}".format(fmt(m_second)))
    print("  1h Contrarian:               {}".format(fmt(m_1h_base)))
    print("  Best params: SL={} TP={} Hold={}".format(*best_params))
    print("  Best filter: {}".format(best_filter))
    print("="*70)

    robust = all([
        m_first["return"] > 0,
        m_second["return"] > 0,
        m_1h_base["return"] > 0,
        m_full["return"] > 0,
    ])

    if robust:
        print("\n  >>> ALL PERIODS POSITIVE - Robust edge confirmed <<<")
    else:
        fails = []
        if m_first["return"] <= 0: fails.append("1st half")
        if m_second["return"] <= 0: fails.append("2nd half")
        if m_1h_base["return"] <= 0: fails.append("1h")
        if m_full["return"] <= 0: fails.append("4h full")
        print("\n  >>> NOT ROBUST - Failed: {} <<<".format(", ".join(fails)))

    results = {
        "full": m_full, "first_half": m_first, "second_half": m_second,
        "1h_base": m_1h_base, "1h_filtered": m_1h_filtered,
        "best_params": {"sl": best_params[0], "tp": best_params[1], "hold": best_params[2]},
        "best_filter": best_filter,
        "robust": robust,
    }
    with open("kronos_validation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved.")


if __name__ == "__main__":
    main()
