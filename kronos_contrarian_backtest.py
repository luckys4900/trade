# -*- coding: utf-8 -*-
"""
Kronos Contrarian Strategy Test
Community reports: "predictions are almost always reversed for crypto"
Test: if Kronos predicts UP -> SHORT, if DOWN -> LONG
"""

import sys, os, time, json, argparse
import numpy as np
import pandas as pd
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Kronos"))

import torch
from model import Kronos, KronosTokenizer, KronosPredictor

INITIAL_CASH = 200.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40

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
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
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


def run_kronos_predictions(df, predictor):
    pred_data = []
    last_pred_bar = -999
    total_preds = 0

    for i in range(KRONOS_LOOKBACK, len(df)):
        if i - last_pred_bar < KRONOS_STEP:
            continue
        last_pred_bar = i
        total_preds += 1

        if total_preds % 200 == 0:
            print("  Progress: {} predictions (bar {}/{})...".format(total_preds, i, len(df)))

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
                pred_len=KRONOS_PRED_LEN, T=0.8, top_p=0.6, sample_count=30,
                verbose=False
            )

            prev_close = df.iloc[i - 1]["close"]
            pred_close = pred_df.iloc[0]["close"]
            pred_high = pred_df.iloc[0]["high"]
            pred_low = pred_df.iloc[0]["low"]
            pred_dir = 1 if pred_close > prev_close else -1

            sigma = pred_high - pred_low
            ev_up = max(pred_close - prev_close, 0)
            ev_down = max(prev_close - pred_close, 0)

            pred_data.append({
                "bar": i,
                "pred_dir": pred_dir,
                "pred_close": pred_close,
                "pred_sigma": sigma,
                "rsi": df.iloc[i]["rsi"],
                "trend": df.iloc[i]["trend"],
                "vol_pct": df.iloc[i]["vol_pct"],
            })

        except Exception as e:
            continue

    print("Total predictions: {}".format(total_preds))
    return pd.DataFrame(pred_data)


def build_signal_sets(df_len, pred_df):
    signals_all = np.zeros(df_len, dtype=int)
    signals_contrarian = np.zeros(df_len, dtype=int)
    signals_trend = np.zeros(df_len, dtype=int)
    signals_contrarian_trend = np.zeros(df_len, dtype=int)

    for _, row in pred_df.iterrows():
        i = int(row["bar"])
        pred_dir = int(row["pred_dir"])
        trend = row["trend"]

        signals_all[i] = pred_dir
        signals_contrarian[i] = -pred_dir

        if pred_dir == 1 and trend == "UPTREND":
            signals_trend[i] = 1
        elif pred_dir == -1 and trend == "DOWNTREND":
            signals_trend[i] = -1

        if pred_dir == -1 and trend == "UPTREND":
            signals_contrarian_trend[i] = 1
        elif pred_dir == 1 and trend == "DOWNTREND":
            signals_contrarian_trend[i] = -1

    return {
        "direct": signals_all,
        "contrarian": signals_contrarian,
        "trend": signals_trend,
        "contrarian_trend": signals_contrarian_trend,
    }


def run_signal_suite(df, signal_sets):
    m1, _ = run_backtest(df, signal_sets["direct"], "Direct")
    m2, _ = run_backtest(df, signal_sets["contrarian"], "Contrarian")
    m3, _ = run_backtest(df, signal_sets["trend"], "Trend")
    m4, _ = run_backtest(df, signal_sets["contrarian_trend"], "ContrarianTrend")
    return {
        "direct": m1,
        "contrarian": m2,
        "trend": m3,
        "contrarian_trend": m4,
    }


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


def print_summary_table(summary_rows):
    print("\n" + "=" * 78)
    print("  BACKTEST SUMMARY")
    print("=" * 78)
    print("  {:<24} {:>10} {:>8} {:>8} {:>8}".format("Test", "Return", "PF", "WR", "MDD"))
    print("  " + "-" * 70)
    for label, metrics in summary_rows:
        print("  {:<24} {:>+9.1f}% {:>8.2f} {:>7.1f}% {:>7.1f}%".format(
            label,
            metrics["total_return"],
            metrics["profit_factor"],
            metrics["win_rate"],
            metrics["max_drawdown"],
        ))
    print("=" * 78)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-4h", default="btc_usdt_4h_unified.csv")
    parser.add_argument("--data-1h", default="btc_usdt_1h.csv")
    parser.add_argument("--split-date", default="2025-04-01 00:00:00")
    parser.add_argument("--recent-months", type=int, default=6)
    parser.add_argument("--report-output", default="kronos_contrarian_report.json")
    args = parser.parse_args()

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print("Device:", device)
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))

    print("Loading Kronos-base...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

    print("Loading BTC 4h data...")
    df_4h = pd.read_csv(args.data_4h, parse_dates=["datetime"], index_col="datetime").sort_index()
    df_4h.columns = [c.lower() for c in df_4h.columns]
    print("4h Data: {} -> {} ({} bars)".format(df_4h.index[0], df_4h.index[-1], len(df_4h)))
    df_4h = compute_indicators(df_4h)

    print("\nPhase 1: Running Kronos predictions on 4h data (T=0.8, samples=30)...")
    t_start = time.time()
    pred_df_4h = run_kronos_predictions(df_4h, predictor)
    elapsed_4h = time.time() - t_start
    print("4h prediction time: {:.0f}s".format(elapsed_4h))

    signals_4h = build_signal_sets(len(df_4h), pred_df_4h)
    suite_4h = run_signal_suite(df_4h, signals_4h)
    m1 = suite_4h["direct"]
    m2 = suite_4h["contrarian"]
    m3 = suite_4h["trend"]
    m4 = suite_4h["contrarian_trend"]

    print("\n" + "=" * 70)
    print("  Strategy 1: Direct (follow Kronos prediction)")
    print("=" * 70)
    print("Signals: LONG={}, SHORT={}".format(sum(signals_4h["direct"] == 1), sum(signals_4h["direct"] == -1)))
    print_report(m1, "Direct (Follow Kronos)")

    print("\n" + "=" * 70)
    print("  Strategy 2: CONTRARIAN (reverse Kronos prediction)")
    print("  Community reports: predictions are almost always reversed")
    print("=" * 70)
    print("Signals: LONG={}, SHORT={}".format(sum(signals_4h["contrarian"] == 1), sum(signals_4h["contrarian"] == -1)))
    print_report(m2, "CONTRARIAN (Reverse Kronos)")

    print("\n" + "=" * 70)
    print("  Strategy 3: Trend Follower (UP+UPTREND / DOWN+DOWNTREND)")
    print("=" * 70)
    print("Signals: LONG={}, SHORT={}".format(sum(signals_4h["trend"] == 1), sum(signals_4h["trend"] == -1)))
    print_report(m3, "Trend Follower")

    print("\n" + "=" * 70)
    print("  Strategy 4: CONTRARIAN + TREND")
    print("  Kronos predicts DOWN + UPTREND -> Go LONG (trend is king)")
    print("  Kronos predicts UP + DOWNTREND -> Go SHORT (trend is king)")
    print("=" * 70)
    print("Signals: LONG={}, SHORT={}".format(sum(signals_4h["contrarian_trend"] == 1), sum(signals_4h["contrarian_trend"] == -1)))
    print_report(m4, "CONTRARIAN + TREND (Reverse Kronos, Follow MA50)")

    split_date = pd.Timestamp(args.split_date)
    first_half = run_window_backtest(df_4h, signals_4h["contrarian"], "Contrarian_4h_FirstHalf", end=split_date)
    second_half = run_window_backtest(df_4h, signals_4h["contrarian"], "Contrarian_4h_SecondHalf", start=split_date)

    print("\nLoading BTC 1h data...")
    df_1h = pd.read_csv(args.data_1h, parse_dates=["datetime"], index_col="datetime").sort_index()
    df_1h.columns = [c.lower() for c in df_1h.columns]
    print("1h Data: {} -> {} ({} bars)".format(df_1h.index[0], df_1h.index[-1], len(df_1h)))
    df_1h = compute_indicators(df_1h)

    print("\nPhase 2: Running Kronos predictions on 1h data (recent {} months summary)...".format(args.recent_months))
    t_start = time.time()
    pred_df_1h = run_kronos_predictions(df_1h, predictor)
    elapsed_1h = time.time() - t_start
    print("1h prediction time: {:.0f}s".format(elapsed_1h))

    signals_1h = build_signal_sets(len(df_1h), pred_df_1h)
    recent_start = df_1h.index.max() - pd.DateOffset(months=args.recent_months)
    recent_1h = run_window_backtest(df_1h, signals_1h["contrarian"], "Contrarian_1h_Recent", start=recent_start)

    print("\n" + "=" * 70)
    print("  FINAL COMPARISON")
    print("=" * 70)
    print("  Current OCPM+MR (existing): +6.5% (PF 1.23, WR 55.6%)")
    print("  1. Direct follow:           {:+.1f}% (PF {:.2f}, WR {:.1f}%)".format(
        m1["total_return"], m1["profit_factor"], m1["win_rate"]))
    print("  2. CONTRARIAN (reverse):    {:+.1f}% (PF {:.2f}, WR {:.1f}%)".format(
        m2["total_return"], m2["profit_factor"], m2["win_rate"]))
    print("  3. Trend follower:          {:+.1f}% (PF {:.2f}, WR {:.1f}%)".format(
        m3["total_return"], m3["profit_factor"], m3["win_rate"]))
    print("  4. CONTRARIAN+TREND:        {:+.1f}% (PF {:.2f}, WR {:.1f}%)".format(
        m4["total_return"], m4["profit_factor"], m4["win_rate"]))
    print("=" * 70)

    winner = max([(m1, "Direct"), (m2, "Contrarian"), (m3, "Trend"), (m4, "ContrarianTrend")],
                 key=lambda x: x[0]["total_return"])
    print("\n  Best: {} -> {:+.1f}% return".format(winner[1], winner[0]["total_return"]))

    if winner[0]["total_return"] > 6.5:
        print("  *** BEATS CURRENT OCPM+MR (+6.5%) ***")
    elif winner[0]["total_return"] > 0:
        print("  Positive but below current OCPM+MR (+6.5%)")
    else:
        print("  No strategy beats current OCPM+MR")

    summary_rows = [
        ("4h Full Contrarian", m2),
        ("4h First Half", first_half),
        ("4h Second Half", second_half),
        ("1h Recent {}m".format(args.recent_months), recent_1h),
    ]
    print_summary_table(summary_rows)

    results = {"direct": m1, "contrarian": m2, "trend": m3, "contrarian_trend": m4}
    with open("kronos_contrarian_results.json", "w") as f:
        json.dump(results, f, indent=2)
    detailed_report = {
        "config": {
            "split_date": args.split_date,
            "recent_months": args.recent_months,
            "lookback": KRONOS_LOOKBACK,
            "sl_atr_mult": SL_ATR_MULT,
            "tp_atr_mult": TP_ATR_MULT,
            "max_hold_bars": MAX_HOLD,
            "sample_count": 30,
            "temperature": 0.8,
            "top_p": 0.6,
        },
        "four_hour": {
            "full_suite": results,
            "contrarian_windows": {
                "full": m2,
                "first_half": first_half,
                "second_half": second_half,
            },
        },
        "one_hour": {
            "recent_contrarian": recent_1h,
        },
    }
    with open(args.report_output, "w") as f:
        json.dump(detailed_report, f, indent=2)
    print("\nResults saved to kronos_contrarian_results.json and {}.".format(args.report_output))


if __name__ == "__main__":
    main()
