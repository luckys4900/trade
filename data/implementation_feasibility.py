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

split_ts = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp())
MAKER_FEE = 0.00015
TAKER_FEE = 0.00045
SLIPPAGE = 0.001
TOTAL_COST = 2 * TAKER_FEE + SLIPPAGE

def get_price_change_sl_tp(ts_sec, horizon_h, sl_atr=2.0, tp_atr=5.0):
    ts_ms = ts_sec * 1000
    idx = np.searchsorted(price_ts, ts_ms)
    if idx < 14 or idx >= len(price_close) - 1:
        return None
    entry = price_close[idx]

    window_atr = price_high[max(0, idx-14):idx+1] - price_low[max(0, idx-14):idx+1]
    atr = np.mean(window_atr[-14:])
    sl_price = entry + sl_atr * atr
    tp_price = entry - tp_atr * atr

    target_ms = ts_ms + horizon_h * 3600 * 1000
    future_idx = np.searchsorted(price_ts, target_ms)
    if future_idx >= len(price_ts):
        future_idx = len(price_ts) - 1

    sl_hit = False
    tp_hit = False
    exit_price = price_close[future_idx]
    exit_idx = future_idx

    for i in range(idx + 1, min(idx + int(horizon_h / 4) + 1, len(price_high))):
        if price_high[i] >= sl_price:
            sl_hit = True
            exit_price = sl_price
            exit_idx = i
            break
        if price_low[i] <= tp_price:
            tp_hit = True
            exit_price = tp_price
            exit_idx = i
            break

    pnl_pct = (entry - exit_price) / entry * 100

    return {
        "change_pct": (price_close[future_idx] - entry) / entry * 100,
        "pnl_pct": pnl_pct,
        "sl_hit": sl_hit,
        "tp_hit": tp_hit,
        "held_bars": exit_idx - idx,
    }

def calc_stats(items, label, fee_pct):
    if not items:
        return None
    changes = [r["pnl_pct"] for r in items]
    n = len(changes)
    wins = [c for c in changes if c > 0]
    losses = [c for c in changes if c <= 0]
    wr = len(wins) / n * 100 if n > 0 else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    ev_raw = wr/100 * avg_win - (100-wr)/100 * avg_loss
    ev_net = ev_raw - fee_pct
    avg_winner = np.mean([abs(r["pnl_pct"]) for r in items if r["pnl_pct"] > 0]) if any(r["pnl_pct"] > 0 for r in items) else 0
    avg_loser = np.mean([abs(r["pnl_pct"]) for r in items if r["pnl_pct"] <= 0]) if any(r["pnl_pct"] <= 0 for r in items) else 0
    rr = avg_winner / avg_loser if avg_loser > 0 else 999
    return {
        "n": n, "wr": wr, "avg_win": avg_win, "avg_loss": avg_loss,
        "ev_raw": ev_raw, "ev_net": ev_net, "fee": fee_pct,
        "sl_hits": sum(1 for r in items if r["sl_hit"]),
        "tp_hits": sum(1 for r in items if r["tp_hit"]),
        "rr": rr,
    }

def fmt(s):
    if s is None:
        return "no data"
    return (f"n={s['n']:<4} WR={s['wr']:.1f}%  avgW={s['avg_win']:.2f}%  avgL={s['avg_loss']:.2f}%  "
            f"RR={s['rr']:.2f}  EV_raw={s['ev_raw']:+.4f}%  EV_net={s['ev_net']:+.4f}%  "
            f"SL={s['sl_hits']} TP={s['tp_hits']}")

print("=" * 120)
print("IMPLEMENTATION FEASIBILITY ANALYSIS")
print(f"Fee model: Taker {TAKER_FEE*100:.3f}% x2 + Slippage {SLIPPAGE*100:.1f}% = {TOTAL_COST*100:.3f}%")
print("=" * 120)

strategies = [
    ("ALL 50+ BTC -> SHORT 12h", {"exchange": None, "min_btc": 50, "max_btc": 99999, "horizon": 12}),
    ("ALL 50+ BTC -> SHORT 24h", {"exchange": None, "min_btc": 50, "max_btc": 99999, "horizon": 24}),
    ("ALL 100+ BTC -> SHORT 12h", {"exchange": None, "min_btc": 100, "max_btc": 99999, "horizon": 12}),
    ("ALL 500+ BTC -> SHORT 12h", {"exchange": None, "min_btc": 500, "max_btc": 99999, "horizon": 12}),
    ("gate.io 50-1000 BTC -> SHORT 12h", {"exchange": "gate.io", "min_btc": 50, "max_btc": 1000, "horizon": 12}),
    ("gate.io 50-1000 BTC -> SHORT 24h", {"exchange": "gate.io", "min_btc": 50, "max_btc": 1000, "horizon": 24}),
    ("gate.io 50-1000 BTC -> SHORT 48h", {"exchange": "gate.io", "min_btc": 50, "max_btc": 1000, "horizon": 48}),
    ("gate.io 100+ BTC -> SHORT 12h", {"exchange": "gate.io", "min_btc": 100, "max_btc": 99999, "horizon": 12}),
]

for name, cfg in strategies:
    ex = cfg["exchange"]
    filtered = [e for e in events
                if (ex is None or e["exchange"] == ex)
                and cfg["min_btc"] <= e["inflow_btc"] < cfg["max_btc"]
                and e["timestamp"] > 0]

    results = []
    for ev in filtered:
        r = get_price_change_sl_tp(ev["timestamp"], cfg["horizon"])
        if r:
            results.append({**r, "exchange": ev["exchange"], "inflow_btc": ev["inflow_btc"], "timestamp": ev["timestamp"]})

    is_data = [r for r in results if r["timestamp"] <= split_ts]
    oos_data = [r for r in results if r["timestamp"] > split_ts]

    print(f"\n--- {name} ---")
    print(f"  IS:  {fmt(calc_stats(is_data, 'IS', TOTAL_COST*100))}")
    print(f"  OOS: {fmt(calc_stats(oos_data, 'OOS', TOTAL_COST*100))}")

    is_s = calc_stats(is_data, "IS", TOTAL_COST*100)
    oos_s = calc_stats(oos_data, "OOS", TOTAL_COST*100)

    if is_s and oos_s:
        verdict = "PASS" if oos_s["ev_net"] > 0 and oos_s["n"] >= 10 else "MARGINAL" if oos_s["ev_net"] > 0 else "FAIL"
        monthly = 0
        if oos_s["n"] > 0:
            oos_days = (max(r["timestamp"] for r in oos_data) - min(r["timestamp"] for r in oos_data)) / 86400
            monthly = oos_s["n"] / max(oos_days / 30, 1)
        print(f"  VERDICT: {verdict} | OOS trades/month: {monthly:.1f}")
        if oos_s["ev_net"] > 0:
            monthly_pnl_190 = 190 * 0.015 * monthly * oos_s["ev_net"]
            monthly_pnl_5000 = 5000 * 0.015 * monthly * oos_s["ev_net"]
            print(f"  PnL est: ${monthly_pnl_190:.2f}/mo ($190) | ${monthly_pnl_5000:.2f}/mo ($5000)")

print("\n" + "=" * 120)
print("ROBINHOOD STRATEGY - CANNOT VERIFY")
print("Robinhood wallet 50+ BTC inflows stopped after 2024-12-10")
print("OOS period (2025-06+) has 0 qualifying events")
print("Robinhood likely migrated to new wallet addresses")
print("=" * 120)
