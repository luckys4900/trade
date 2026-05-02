import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict

DATA_DIR = "data"

events = json.load(open(f"{DATA_DIR}/full_inflow_events.json", "r", encoding="utf-8"))
price_df = pd.read_csv(f"{DATA_DIR}/btc_price_4h_cache.csv")
price_df["datetime"] = pd.to_datetime(price_df["datetime"], utc=True)

price_ts = (pd.to_datetime(price_df["datetime"]).astype(np.int64) // 10**6).values
price_close = price_df["close"].values
price_high = price_df["high"].values
price_low = price_df["low"].values

def get_indicator_at(ts_sec):
    ts_ms = ts_sec * 1000
    idx = np.searchsorted(price_ts, ts_ms) - 1
    if idx < 14 or idx >= len(price_close):
        return None
    window = price_close[max(0, idx-55):idx+1]
    if len(window) < 14:
        return None
    deltas = np.diff(window)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-14:])
    avg_loss = np.mean(losses[-14:])
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    ema21 = np.mean(window[-21:]) if len(window) >= 21 else np.mean(window)
    ema55 = np.mean(window[-55:]) if len(window) >= 55 else np.mean(window)
    trend = "UP" if ema21 > ema55 else "DOWN"
    atr_window = price_high[max(0, idx-14):idx+1] - price_low[max(0, idx-14):idx+1]
    atr = np.mean(atr_window[-14:]) if len(atr_window) >= 14 else 0
    atr_pct = atr / price_close[idx] * 100 if price_close[idx] > 0 else 0
    hour = datetime.utcfromtimestamp(ts_sec).hour
    session = "ASIA" if 0 <= hour < 8 else "EUROPE" if 8 <= hour < 16 else "US"
    return {"rsi": rsi, "trend": trend, "atr_pct": atr_pct, "session": session, "hour": hour}

def get_price_change(ts_sec, horizon_h):
    ts_ms = ts_sec * 1000
    idx = np.searchsorted(price_ts, ts_ms)
    if idx < 1 or idx >= len(price_ts) - 1:
        return None
    entry = price_close[idx]
    target_ms = ts_ms + horizon_h * 3600 * 1000
    future_idx = np.searchsorted(price_ts, target_ms)
    if future_idx >= len(price_ts):
        return None
    future = price_close[future_idx]
    return (future - entry) / entry * 100

print("=" * 80)
print("DEEP ANALYSIS: FACTORS THAT IMPROVE INFLOW SHORT EV")
print("=" * 80)

horizon = 12
enriched = []
for ev in events:
    if ev["timestamp"] == 0:
        continue
    ind = get_indicator_at(ev["timestamp"])
    if ind is None:
        continue
    ch = get_price_change(ev["timestamp"], horizon)
    if ch is None:
        continue
    enriched.append({**ev, **ind, "change_pct": ch})

print(f"\nEnriched events: {len(enriched)}")

def stats(items, label=""):
    if not items:
        return
    changes = [r["change_pct"] for r in items]
    drops = [c for c in changes if c < 0]
    n = len(changes)
    wr = len(drops) / n * 100
    ev = (wr/100 * abs(np.mean(drops)) if drops else 0) - ((100-wr)/100 * (np.mean([c for c in changes if c >= 0]) if any(c >= 0 for c in changes) else 0))
    print(f"  {label:<45} n={n:>4} WR={wr:.0f}% EV={ev:+.4f}% avg={np.mean(changes):+.3f}%")

# === Factor 1: RSI at entry ===
print("\n--- FACTOR 1: RSI at inflow time ---")
for lo, hi in [(0, 40), (40, 50), (50, 60), (60, 70), (70, 100)]:
    items = [r for r in enriched if lo <= r["rsi"] < hi]
    stats(items, f"RSI {lo}-{hi}")

# === Factor 2: Trend ===
print("\n--- FACTOR 2: Trend direction ---")
for t in ["UP", "DOWN"]:
    items = [r for r in enriched if r["trend"] == t]
    stats(items, f"Trend={t}")

# === Factor 3: Session ===
print("\n--- FACTOR 3: Session ---")
for s in ["ASIA", "EUROPE", "US"]:
    items = [r for r in enriched if r["session"] == s]
    stats(items, f"Session={s}")

# === Factor 4: Inflow size ===
print("\n--- FACTOR 4: Inflow size buckets ---")
for lo, hi in [(50, 100), (100, 200), (200, 500), (500, 1000), (1000, 99999)]:
    items = [r for r in enriched if lo <= r["inflow_btc"] < hi]
    stats(items, f"{lo}-{hi if hi<99999 else 'inf'} BTC")

# === Factor 5: Volatility ===
print("\n--- FACTOR 5: ATR (volatility) ---")
for lo, hi in [(0, 1.5), (1.5, 2.5), (2.5, 4.0), (4.0, 99)]:
    items = [r for r in enriched if lo <= r["atr_pct"] < hi]
    stats(items, f"ATR% {lo}-{hi}")

# === Factor 6: Exchange + RSI combination ===
print("\n--- FACTOR 6: Best exchange + RSI filter ---")
for ex in ["gate.io", "OKEx", "Robinhood", "Bitfinex"]:
    for rsi_lo, rsi_hi in [(50, 100), (0, 50)]:
        items = [r for r in enriched if r["exchange"] == ex and rsi_lo <= r["rsi"] < rsi_hi]
        if len(items) >= 5:
            stats(items, f"{ex} + RSI {rsi_lo}-{rsi_hi}")

# === Factor 7: Exchange + Trend ===
print("\n--- FACTOR 7: Exchange + Trend ---")
for ex in ["gate.io", "OKEx", "Robinhood"]:
    for t in ["UP", "DOWN"]:
        items = [r for r in enriched if r["exchange"] == ex and r["trend"] == t]
        if len(items) >= 5:
            stats(items, f"{ex} + {t}")

# === Factor 8: Consecutive inflows (multiple in 24h) ===
print("\n--- FACTOR 8: Consecutive inflows (24h window) ---")
by_ex_ts = defaultdict(list)
for r in enriched:
    by_ex_ts[r["exchange"]].append(r["timestamp"])

consecutive = []
single = []
for r in enriched:
    same_ex = [r2 for r2 in enriched if r2["exchange"] == r["exchange"] and abs(r2["timestamp"] - r["timestamp"]) < 86400 and r2["tx_hash"] != r["tx_hash"]]
    if len(same_ex) >= 2:
        consecutive.append(r)
    else:
        single.append(r)
stats(consecutive, f"Consecutive (3+ in 24h)")
stats(single, f"Single inflow")

# === Best combination search ===
print("\n" + "=" * 80)
print("BEST COMBINATION SEARCH (min 30 events, sorted by EV)")
print("=" * 80)

combos = []
for ex in ["gate.io", "OKEx", "Robinhood", "all"]:
    for rsi_lo, rsi_hi in [(0, 50), (50, 100), (0, 100)]:
        for trend in ["UP", "DOWN", "all"]:
            for sz_lo, sz_hi in [(50, 99999), (100, 99999), (50, 500)]:
                items = [r for r in enriched
                         if (ex == "all" or r["exchange"] == ex)
                         and rsi_lo <= r["rsi"] < rsi_hi
                         and (trend == "all" or r["trend"] == trend)
                         and sz_lo <= r["inflow_btc"] < sz_hi]
                if len(items) < 30:
                    continue
                changes = [r["change_pct"] for r in items]
                drops = [c for c in changes if c < 0]
                n = len(changes)
                wr = len(drops) / n * 100
                ev = (wr/100 * abs(np.mean(drops)) if drops else 0) - ((100-wr)/100 * (np.mean([c for c in changes if c >= 0]) if any(c >= 0 for c in changes) else 0))
                combos.append({"ex": ex, "rsi": f"{rsi_lo}-{rsi_hi}", "trend": trend, "size": f"{sz_lo}-{sz_hi}", "n": n, "wr": wr, "ev": ev, "avg": np.mean(changes)})

combos.sort(key=lambda x: -x["ev"])
for c in combos[:15]:
    print(f"  {c['ex']:<12} RSI={c['rsi']:<8} Trend={c['trend']:<5} Size={c['size']:<12} n={c['n']:>3} WR={c['wr']:.0f}% EV={c['ev']:+.4f}%")

# IS/OOS for top 3
print("\n" + "=" * 80)
print("IS/OOS CHECK FOR TOP 3 COMBINATIONS")
print("=" * 80)
split_ts = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp())

for c in combos[:3]:
    items = [r for r in enriched
             if (c["ex"] == "all" or r["exchange"] == c["ex"])
             and int(c["rsi"].split("-")[0]) <= r["rsi"] < int(c["rsi"].split("-")[1])
             and (c["trend"] == "all" or r["trend"] == c["trend"])
             and int(c["size"].split("-")[0]) <= r["inflow_btc"] < int(c["size"].split("-")[1])]
    is_items = [r for r in items if r["timestamp"] <= split_ts]
    oos_items = [r for r in items if r["timestamp"] > split_ts]
    print(f"\n  {c['ex']} RSI={c['rsi']} Trend={c['trend']} Size={c['size']}")
    stats(is_items, "  IS")
    stats(oos_items, "  OOS")
