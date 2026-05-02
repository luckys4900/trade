# -*- coding: utf-8 -*-
"""
Funding Rate Mean Reversion Backtest
Tests whether extreme funding rates on BTC/USDT perpetual futures
predict profitable mean-reversion trades.

Hypothesis: When FR is extremely positive (longs pay shorts),
            price tends to drop → SHORT entry has edge.
            When FR is extremely negative, opposite.

Uses 8h funding rate events, tests multiple entry/exit combinations
with proper IS/OOS split and fee-adjusted PnL.
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict

DATA_DIR = "data"

fr_df = pd.read_csv(f"{DATA_DIR}/btc_funding_rate.csv")
fr_df.columns = ["datetime", "funding_rate"]
fr_df["datetime"] = pd.to_datetime(fr_df["datetime"], utc=True)
fr_df["funding_rate"] = pd.to_numeric(fr_df["funding_rate"], errors="coerce")
fr_df = fr_df.dropna(subset=["funding_rate"]).reset_index(drop=True)

price_df = pd.read_csv(f"{DATA_DIR}/btc_price_4h_cache.csv")
price_df["datetime"] = pd.to_datetime(price_df["datetime"], utc=True)

price_ts = (price_df["datetime"].astype(np.int64) // 10**6).values
price_close = price_df["close"].values
price_high = price_df["high"].values
price_low = price_df["low"].values

TAKER_FEE = 0.00045
SLIPPAGE = 0.001
COST_PCT = (2 * TAKER_FEE + SLIPPAGE) * 100

print("=" * 100)
print("FUNDING RATE MEAN REVERSION BACKTEST")
print(f"FR data: {fr_df.iloc[0]['datetime'].strftime('%Y-%m-%d')} ~ {fr_df.iloc[-1]['datetime'].strftime('%Y-%m-%d')} ({len(fr_df)} hours)")
print(f"Price data: {price_df.iloc[0]['datetime'].strftime('%Y-%m-%d')} ~ {price_df.iloc[-1]['datetime'].strftime('%Y-%m-%d')} ({len(price_df)} bars)")
print(f"Cost model: Taker {TAKER_FEE*100:.3f}% x2 + Slippage {SLIPPAGE*100:.1f}% = {COST_PCT:.3f}%")
print("=" * 100)

fr_ts = (fr_df["datetime"].astype(np.int64) // 10**6).values
fr_vals = fr_df["funding_rate"].values

print(f"\nFR Distribution:")
print(f"  Mean: {fr_vals.mean():.6f} ({fr_vals.mean()*100:.4f}%)")
print(f"  Median: {np.median(fr_vals):.6f}")
print(f"  Std: {fr_vals.std():.6f}")
print(f"  Skew: {pd.Series(fr_vals).skew():.3f}")
for pct in [1, 5, 10, 90, 95, 99]:
    print(f"  {pct}th percentile: {np.percentile(fr_vals, pct):.6f}")

fr_8h = fr_df[fr_df["datetime"].dt.hour.isin([0, 8, 16])].copy().reset_index(drop=True)
print(f"\n8h funding events: {len(fr_8h)}")

def get_price_at(ts_ms):
    idx = np.searchsorted(price_ts, ts_ms)
    if idx >= len(price_close):
        return None, None
    return price_close[idx], idx

def calc_trade(entry_ts_ms, direction, horizon_bars, sl_atr_mult=2.0, tp_atr_mult=5.0):
    idx = np.searchsorted(price_ts, entry_ts_ms)
    if idx < 14 or idx + horizon_bars >= len(price_close):
        return None

    entry = price_close[idx]
    window_atr = price_high[max(0, idx-14):idx+1] - price_low[max(0, idx-14):idx+1]
    atr = np.mean(window_atr[-14:])

    if direction == "SHORT":
        sl_price = entry + sl_atr_mult * atr
        tp_price = entry - tp_atr_mult * atr
    else:
        sl_price = entry - sl_atr_mult * atr
        tp_price = entry + tp_atr_mult * atr

    exit_price = None
    exit_bar = horizon_bars

    for i in range(idx + 1, min(idx + horizon_bars + 1, len(price_close))):
        if direction == "SHORT":
            if price_high[i] >= sl_price:
                exit_price = sl_price
                exit_bar = i - idx
                break
            if price_low[i] <= tp_price:
                exit_price = tp_price
                exit_bar = i - idx
                break
        else:
            if price_low[i] <= sl_price:
                exit_price = sl_price
                exit_bar = i - idx
                break
            if price_high[i] >= tp_price:
                exit_price = tp_price
                exit_bar = i - idx
                break

    if exit_price is None:
        exit_price = price_close[min(idx + horizon_bars, len(price_close) - 1)]
        exit_bar = horizon_bars

    if direction == "SHORT":
        pnl = (entry - exit_price) / entry * 100
    else:
        pnl = (exit_price - entry) / entry * 100

    return {
        "pnl_raw": pnl,
        "pnl_net": pnl - COST_PCT,
        "held_bars": exit_bar,
        "sl_hit": exit_price == sl_price if exit_price else False,
        "tp_hit": exit_price == tp_price if exit_price else False,
    }

split_date = "2025-06-01"
split_ts = int(datetime.strptime(split_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) * 1000

results_by_threshold = []

print("\n" + "=" * 100)
print("STRATEGY 1: EXTREME POSITIVE FR → SHORT (mean reversion)")
print("=" * 100)

for fr_threshold_pct in [0.01, 0.015, 0.02, 0.03, 0.05, 0.08, 0.10]:
    fr_threshold = fr_threshold_pct / 100
    horizon = 6

    trades = []
    for _, row in fr_8h.iterrows():
        fr = row["funding_rate"]
        if fr <= fr_threshold:
            continue
        ts_ms = int(row["datetime"].timestamp() * 1000)
        result = calc_trade(ts_ms, "SHORT", horizon)
        if result:
            trades.append({**result, "timestamp": ts_ms, "fr": fr, "direction": "SHORT"})

    if not trades:
        continue

    is_trades = [t for t in trades if t["timestamp"] <= split_ts]
    oos_trades = [t for t in trades if t["timestamp"] > split_ts]

    def stats(trade_list, label):
        if not trade_list:
            return None
        pnls = [t["pnl_raw"] for t in trade_list]
        nets = [t["pnl_net"] for t in trade_list]
        n = len(pnls)
        wins = [p for p in pnls if p > 0]
        wr = len(wins) / n * 100
        ev_raw = np.mean(pnls)
        ev_net = np.mean(nets)
        sl_hits = sum(1 for t in trade_list if t["sl_hit"])
        tp_hits = sum(1 for t in trade_list if t["tp_hit"])
        avg_w = np.mean(wins) if wins else 0
        avg_l = abs(np.mean([p for p in pnls if p <= 0])) if any(p <= 0 for p in pnls) else 0
        rr = avg_w / avg_l if avg_l > 0 else 999
        return {
            "label": label, "n": n, "wr": wr, "ev_raw": ev_raw, "ev_net": ev_net,
            "sl": sl_hits, "tp": tp_hits, "avg_w": avg_w, "avg_l": avg_l, "rr": rr,
            "median_net": np.median(nets),
        }

    is_s = stats(is_trades, "IS")
    oos_s = stats(oos_trades, "OOS")

    results_by_threshold.append({
        "type": "SHORT on high FR",
        "threshold": fr_threshold_pct,
        "is_n": is_s["n"] if is_s else 0,
        "oos_n": oos_s["n"] if oos_s else 0,
        "is_ev_net": is_s["ev_net"] if is_s else None,
        "oos_ev_net": oos_s["ev_net"] if oos_s else None,
        "is_wr": is_s["wr"] if is_s else None,
        "oos_wr": oos_s["wr"] if oos_s else None,
    })

    print(f"\n  FR > {fr_threshold_pct:.3f}% (1h rate) → SHORT {horizon} bars")
    if is_s:
        print(f"    IS:  n={is_s['n']:<4} WR={is_s['wr']:.1f}% EV_raw={is_s['ev_raw']:+.4f}% EV_net={is_s['ev_net']:+.4f}% SL={is_s['sl']} TP={is_s['tp']} RR={is_s['rr']:.2f}")
    if oos_s:
        print(f"    OOS: n={oos_s['n']:<4} WR={oos_s['wr']:.1f}% EV_raw={oos_s['ev_raw']:+.4f}% EV_net={oos_s['ev_net']:+.4f}% SL={oos_s['sl']} TP={oos_s['tp']} RR={oos_s['rr']:.2f}")

print("\n" + "=" * 100)
print("STRATEGY 2: EXTREME NEGATIVE FR → LONG (mean reversion)")
print("=" * 100)

for fr_threshold_pct in [-0.005, -0.008, -0.01, -0.015, -0.02]:
    fr_threshold = fr_threshold_pct / 100
    horizon = 6

    trades = []
    for _, row in fr_8h.iterrows():
        fr = row["funding_rate"]
        if fr >= fr_threshold:
            continue
        ts_ms = int(row["datetime"].timestamp() * 1000)
        result = calc_trade(ts_ms, "LONG", horizon)
        if result:
            trades.append({**result, "timestamp": ts_ms, "fr": fr, "direction": "LONG"})

    if not trades:
        continue

    is_trades = [t for t in trades if t["timestamp"] <= split_ts]
    oos_trades = [t for t in trades if t["timestamp"] > split_ts]

    is_s = stats(is_trades, "IS") if is_trades else None
    oos_s = stats(oos_trades, "OOS") if oos_trades else None

    results_by_threshold.append({
        "type": "LONG on low FR",
        "threshold": fr_threshold_pct,
        "is_n": is_s["n"] if is_s else 0,
        "oos_n": oos_s["n"] if oos_s else 0,
        "is_ev_net": is_s["ev_net"] if is_s else None,
        "oos_ev_net": oos_s["ev_net"] if oos_s else None,
        "is_wr": is_s["wr"] if is_s else None,
        "oos_wr": oos_s["wr"] if oos_s else None,
    })

    print(f"\n  FR < {fr_threshold_pct:.3f}% → LONG {horizon} bars")
    if is_s:
        print(f"    IS:  n={is_s['n']:<4} WR={is_s['wr']:.1f}% EV_raw={is_s['ev_raw']:+.4f}% EV_net={is_s['ev_net']:+.4f}% SL={is_s['sl']} TP={is_s['tp']} RR={is_s['rr']:.2f}")
    if oos_s:
        print(f"    OOS: n={oos_s['n']:<4} WR={oos_s['wr']:.1f}% EV_raw={oos_s['ev_raw']:+.4f}% EV_net={oos_s['ev_net']:+.4f}% SL={oos_s['sl']} TP={oos_s['tp']} RR={oos_s['rr']:.2f}")

print("\n" + "=" * 100)
print("STRATEGY 3: FR Z-SCORE EXTREME → REVERSE (combined)")
print("=" * 100)

fr_8h_sorted = fr_8h.sort_values("datetime").reset_index(drop=True)
fr_8h_sorted["fr_zscore"] = (fr_8h_sorted["funding_rate"] - fr_8h_sorted["funding_rate"].rolling(90).mean()) / fr_8h_sorted["funding_rate"].rolling(90).std()

for z_thresh in [1.5, 2.0, 2.5, 3.0]:
    trades = []
    for _, row in fr_8h_sorted.iterrows():
        z = row["fr_zscore"]
        if pd.isna(z):
            continue
        ts_ms = int(row["datetime"].timestamp() * 1000)

        if z > z_thresh:
            direction = "SHORT"
        elif z < -z_thresh:
            direction = "LONG"
        else:
            continue

        result = calc_trade(ts_ms, direction, 6)
        if result:
            trades.append({**result, "timestamp": ts_ms, "fr": row["funding_rate"], "zscore": z, "direction": direction})

    is_trades = [t for t in trades if t["timestamp"] <= split_ts]
    oos_trades = [t for t in trades if t["timestamp"] > split_ts]

    is_s = stats(is_trades, "IS") if is_trades else None
    oos_s = stats(oos_trades, "OOS") if oos_trades else None

    results_by_threshold.append({
        "type": "Z-score reverse",
        "threshold": z_thresh,
        "is_n": is_s["n"] if is_s else 0,
        "oos_n": oos_s["n"] if oos_s else 0,
        "is_ev_net": is_s["ev_net"] if is_s else None,
        "oos_ev_net": oos_s["ev_net"] if oos_s else None,
        "is_wr": is_s["wr"] if is_s else None,
        "oos_wr": oos_s["wr"] if oos_s else None,
    })

    print(f"\n  |Z-score| > {z_thresh} → REVERSE, 6 bars")
    if is_s:
        print(f"    IS:  n={is_s['n']:<4} WR={is_s['wr']:.1f}% EV_raw={is_s['ev_raw']:+.4f}% EV_net={is_s['ev_net']:+.4f}% SL={is_s['sl']} TP={is_s['tp']} RR={is_s['rr']:.2f}")
    if oos_s:
        print(f"    OOS: n={oos_s['n']:<4} WR={oos_s['wr']:.1f}% EV_raw={oos_s['ev_raw']:+.4f}% EV_net={oos_s['ev_net']:+.4f}% SL={oos_s['sl']} TP={oos_s['tp']} RR={oos_s['rr']:.2f}")

print("\n" + "=" * 100)
print("STRATEGY 4: FR + FUNDING PAYMENT HARVEST (carry trade)")
print("When FR is high → enter SHORT, hold through funding payment, exit after")
print("=" * 100)

for fr_threshold_pct in [0.01, 0.02, 0.03, 0.05, 0.08, 0.10]:
    fr_threshold = fr_threshold_pct / 100
    hold_bars = 2

    trades = []
    for _, row in fr_8h.iterrows():
        fr = row["funding_rate"]
        if fr <= fr_threshold:
            continue
        ts_ms = int(row["datetime"].timestamp() * 1000)

        idx = np.searchsorted(price_ts, ts_ms)
        if idx < 14 or idx + hold_bars >= len(price_close):
            continue

        entry = price_close[idx]
        exit_p = price_close[idx + hold_bars]
        price_pnl = (entry - exit_p) / entry * 100
        funding_pnl = fr * 100 * 8
        total_pnl = price_pnl + funding_pnl - COST_PCT

        trades.append({
            "pnl_raw": price_pnl + funding_pnl,
            "pnl_net": total_pnl,
            "price_pnl": price_pnl,
            "funding_pnl": funding_pnl,
            "timestamp": ts_ms, "fr": fr, "direction": "SHORT",
            "held_bars": hold_bars, "sl_hit": False, "tp_hit": False,
        })

    is_trades = [t for t in trades if t["timestamp"] <= split_ts]
    oos_trades = [t for t in trades if t["timestamp"] > split_ts]

    is_s = stats(is_trades, "IS") if is_trades else None
    oos_s = stats(oos_trades, "OOS") if oos_trades else None

    print(f"\n  FR > {fr_threshold_pct:.3f}% → SHORT hold {hold_bars} bars + collect funding")
    if is_s:
        avg_fund = np.mean([t["funding_pnl"] for t in is_trades])
        avg_price = np.mean([t["price_pnl"] for t in is_trades])
        print(f"    IS:  n={is_s['n']:<4} WR={is_s['wr']:.1f}% EV_net={is_s['ev_net']:+.4f}% | avg_funding={avg_fund:.4f}% avg_price={avg_price:+.4f}%")
    if oos_s:
        avg_fund = np.mean([t["funding_pnl"] for t in oos_trades])
        avg_price = np.mean([t["price_pnl"] for t in oos_trades])
        print(f"    OOS: n={oos_s['n']:<4} WR={oos_s['wr']:.1f}% EV_net={oos_s['ev_net']:+.4f}% | avg_funding={avg_fund:.4f}% avg_price={avg_price:+.4f}%")

print("\n" + "=" * 100)
print("SUMMARY: BEST OOS RESULTS (EV_net > 0, sorted by OOS EV)")
print("=" * 100)

passing = [r for r in results_by_threshold if r["oos_ev_net"] is not None and r["oos_ev_net"] > 0 and r["oos_n"] >= 5]
passing.sort(key=lambda x: -x["oos_ev_net"])

if passing:
    print(f"\n{'Type':<25} {'Threshold':>10} {'IS n':>6} {'OOS n':>7} {'IS EV_net':>10} {'OOS EV_net':>11} {'IS WR':>7} {'OOS WR':>7}")
    print("-" * 90)
    for r in passing:
        print(f"  {r['type']:<23} {r['threshold']:>10.3f} {r['is_n']:>6} {r['oos_n']:>7} {r['is_ev_net']:>+10.4f}% {r['oos_ev_net']:>+11.4f}% {r['is_wr']:>6.1f}% {r['oos_wr']:>6.1f}%")
else:
    print("\n  No strategies pass OOS with EV_net > 0 and n >= 5")

all_oos = [r for r in results_by_threshold if r["oos_ev_net"] is not None and r["oos_n"] >= 3]
all_oos.sort(key=lambda x: -x["oos_ev_net"])
print(f"\nAll results (OOS n >= 3):")
for r in all_oos[:15]:
    verdict = "PASS" if r["oos_ev_net"] > 0 and r["oos_n"] >= 5 else "MARGINAL" if r["oos_ev_net"] > 0 else "FAIL"
    print(f"  {r['type']:<23} thresh={r['threshold']:>8.3f} OOS: n={r['oos_n']:<4} EV_net={r['oos_ev_net']:+.4f}% WR={r['oos_wr']:.1f}% | {verdict}")

with open(f"{DATA_DIR}/funding_rate_backtest_results.json", "w", encoding="utf-8") as f:
    json.dump(results_by_threshold, f, indent=2, ensure_ascii=False, default=str)
print(f"\nSaved to {DATA_DIR}/funding_rate_backtest_results.json")
