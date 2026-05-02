# -*- coding: utf-8 -*-
"""
Fetch historical funding rate + OI data from Hyperliquid API
and run Squeeze Detection backtest.

Strategy: When OI rapidly increases while price moves in one direction,
          the market is overcrowded → fade the move (contrarian).
"""

import os
import json
import time
import logging
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

DATA_DIR = "data"
HL_API = "https://api.hyperliquid.xyz/info"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("oi_backtest")


def fetch_funding_history(coin="BTC", start_ms=None, end_ms=None):
    all_rates = []
    batch_start = start_ms or 1704067200000  # 2024-01-01

    while True:
        payload = {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": batch_start,
        }
        if end_ms:
            payload["endTime"] = end_ms

        try:
            r = requests.post(HL_API, json=payload, timeout=30)
            data = r.json()
        except Exception as e:
            logger.warning(f"Funding API error: {e}")
            break

        if not data:
            break

        all_rates.extend(data)
        logger.info(f"  Fetched {len(data)} FR entries, total {len(all_rates)}")

        if len(data) < 500:
            break

        batch_start = data[-1]["time"] + 1
        time.sleep(0.3)

    return all_rates


def fetch_oi_history_from_candles():
    logger.info("Loading BTC 4h price data...")
    price_df = pd.read_csv(f"{DATA_DIR}/btc_price_4h_cache.csv")
    price_df["datetime"] = pd.to_datetime(price_df["datetime"], utc=True)
    return price_df


def build_oi_proxy_from_volume(price_df):
    price_df = price_df.copy()
    price_df["volume_usd"] = price_df["close"] * price_df["volume"]
    price_df["vol_ma20"] = price_df["volume_usd"].rolling(20).mean()
    price_df["vol_ratio"] = price_df["volume_usd"] / price_df["vol_ma20"]
    price_df["returns"] = price_df["close"].pct_change() * 100
    price_df["atr_pct"] = (price_df["high"] - price_df["low"]) / price_df["close"] * 100
    price_df["atr_ma20"] = price_df["atr_pct"].rolling(20).mean()
    price_df["atr_ratio"] = price_df["atr_pct"] / price_df["atr_ma20"]
    price_df["range_pct"] = price_df["atr_pct"]

    for p in [14]:
        deltas = price_df["close"].diff()
        gains = deltas.where(deltas > 0, 0).rolling(p).mean()
        losses = (-deltas.where(deltas < 0, 0)).rolling(p).mean()
        rs = gains / losses.replace(0, np.nan)
        price_df[f"rsi_{p}"] = 100 - (100 / (1 + rs))

    price_df["ema21"] = price_df["close"].ewm(span=21).mean()
    price_df["ema55"] = price_df["close"].ewm(span=55).mean()
    price_df["trend"] = np.where(price_df["ema21"] > price_df["ema55"], "UP", "DOWN")

    return price_df


def main():
    fr_path = f"{DATA_DIR}/hl_funding_history.json"
    if os.path.exists(fr_path):
        logger.info(f"Loading cached funding history from {fr_path}")
        fr_data = json.load(open(fr_path, "r", encoding="utf-8"))
    else:
        logger.info("Fetching funding history from Hyperliquid...")
        fr_data = fetch_funding_history("BTC")
        with open(fr_path, "w", encoding="utf-8") as f:
            json.dump(fr_data, f, indent=2)
        logger.info(f"Saved {len(fr_data)} entries to {fr_path}")

    fr_df = pd.DataFrame(fr_data)
    fr_df["time"] = pd.to_datetime(fr_df["time"], unit="ms", utc=True)
    fr_df["fundingRate"] = pd.to_numeric(fr_df["fundingRate"], errors="coerce")
    fr_df = fr_df.dropna(subset=["fundingRate"]).sort_values("time").reset_index(drop=True)
    fr_df["fr_pct"] = fr_df["fundingRate"] * 100

    logger.info(f"Funding history: {len(fr_df)} entries, {fr_df['time'].iloc[0]} ~ {fr_df['time'].iloc[-1]}")

    price_df = fetch_oi_history_from_candles()
    price_df = build_oi_proxy_from_volume(price_df)

    price_ts = (price_df["datetime"].astype(np.int64) // 10**6).values
    price_close = price_df["close"].values
    price_high = price_df["high"].values
    price_low = price_df["low"].values

    TAKER_FEE = 0.00045
    SLIPPAGE = 0.001
    COST_PCT = (2 * TAKER_FEE + SLIPPAGE) * 100

    split_ts_ms = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)

    print("\n" + "=" * 100)
    print("COMBINED STRATEGY BACKTEST: FUNDING RATE + VOLUME ANOMALY + RSI")
    print("=" * 100)

    # Align FR to 4h bars
    fr_4h = fr_df[fr_df["time"].dt.hour.isin([0, 4, 8, 12, 16, 20])].copy()
    logger.info(f"4h FR events: {len(fr_4h)}")

    fr_by_ts = {}
    for _, row in fr_4h.iterrows():
        ts_key = int(row["time"].timestamp())
        fr_by_ts[ts_key] = row["fr_pct"]

    def get_fr_at(ts_ms):
        ts_sec = ts_ms // 1000
        best_key = min(fr_by_ts.keys(), key=lambda k: abs(k - ts_sec)) if fr_by_ts else None
        if best_key and abs(best_key - ts_sec) < 14400:
            return fr_by_ts[best_key]
        return None

    def calc_trade(entry_idx, direction, horizon_bars, sl_atr_mult=2.0, tp_atr_mult=5.0):
        if entry_idx < 14 or entry_idx + horizon_bars >= len(price_close):
            return None

        entry = price_close[entry_idx]
        atr_window = price_high[max(0, entry_idx-14):entry_idx+1] - price_low[max(0, entry_idx-14):entry_idx+1]
        atr = np.mean(atr_window[-14:])

        if direction == "SHORT":
            sl_price = entry + sl_atr_mult * atr
            tp_price = entry - tp_atr_mult * atr
        else:
            sl_price = entry - sl_atr_mult * atr
            tp_price = entry + tp_atr_mult * atr

        exit_price = None
        for i in range(entry_idx + 1, min(entry_idx + horizon_bars + 1, len(price_close))):
            if direction == "SHORT":
                if price_high[i] >= sl_price:
                    exit_price = sl_price
                    break
                if price_low[i] <= tp_price:
                    exit_price = tp_price
                    break
            else:
                if price_low[i] <= sl_price:
                    exit_price = sl_price
                    break
                if price_high[i] >= tp_price:
                    exit_price = tp_price
                    break

        if exit_price is None:
            exit_price = price_close[min(entry_idx + horizon_bars, len(price_close) - 1)]

        if direction == "SHORT":
            pnl = (entry - exit_price) / entry * 100
        else:
            pnl = (exit_price - entry) / entry * 100

        return {"pnl_raw": pnl, "pnl_net": pnl - COST_PCT}

    def stats(items):
        if not items:
            return None
        raws = [t["pnl_raw"] for t in items]
        nets = [t["pnl_net"] for t in items]
        n = len(raws)
        wins = [r for r in raws if r > 0]
        wr = len(wins) / n * 100
        return {
            "n": n, "wr": wr,
            "ev_raw": np.mean(raws), "ev_net": np.mean(nets),
            "median_net": np.median(nets),
            "avg_w": np.mean(wins) if wins else 0,
            "avg_l": abs(np.mean([r for r in raws if r <= 0])) if any(r <= 0 for r in raws) else 0,
        }

    def fmt(s):
        if not s:
            return "no data"
        rr = s["avg_w"] / s["avg_l"] if s["avg_l"] > 0 else 999
        return f"n={s['n']:<4} WR={s['wr']:.1f}% EV_raw={s['ev_raw']:+.4f}% EV_net={s['ev_net']:+.4f}% RR={rr:.2f}"

    strategies = []

    # Strategy: High volume spike + overextended RSI + extreme FR → fade
    print("\n--- STRATEGY: Volume Spike + RSI Extreme + FR Extreme → FADE ---")

    for vol_thresh in [2.0, 2.5, 3.0]:
        for rsi_lo, rsi_hi, direction, label in [
            (70, 101, "SHORT", "RSI>70"),
            (75, 101, "SHORT", "RSI>75"),
            (80, 101, "SHORT", "RSI>80"),
            (0, 30, "LONG", "RSI<30"),
            (0, 25, "LONG", "RSI<25"),
        ]:
            for fr_cond, fr_label in [
                (lambda fr: fr is not None and fr > 0.005, "FR>0.005%"),
                (lambda fr: fr is not None and fr > 0.01, "FR>0.01%"),
                (lambda fr: True, "any_FR"),
            ]:
                trades_is = []
                trades_oos = []

                for idx in range(55, len(price_df) - 12):
                    row = price_df.iloc[idx]
                    ts_ms = int(row["datetime"].timestamp() * 1000)

                    if not (rsi_lo <= row.get("rsi_14", 50) < rsi_hi):
                        continue
                    if not (row.get("vol_ratio", 1) >= vol_thresh):
                        continue

                    fr = get_fr_at(ts_ms)
                    if not fr_cond(fr):
                        continue

                    result = calc_trade(idx, direction, 6)
                    if not result:
                        continue

                    if ts_ms <= split_ts_ms:
                        trades_is.append(result)
                    else:
                        trades_oos.append(result)

                is_s = stats(trades_is)
                oos_s = stats(trades_oos)

                if (is_s and is_s["n"] >= 3) or (oos_s and oos_s["n"] >= 3):
                    strategies.append({
                        "label": f"Vol>{vol_thresh}x + {label} + {fr_label} → {direction}",
                        "is_s": is_s, "oos_s": oos_s,
                    })

    # Strategy: ATR spike (squeeze detection) + trend exhaustion
    print("\n--- STRATEGY: ATR Squeeze + Trend Exhaustion → FADE ---")

    for atr_thresh in [2.0, 2.5, 3.0]:
        for bars_up in [3, 4, 5]:
            trades_is = []
            trades_oos = []

            for idx in range(55, len(price_df) - 12):
                row = price_df.iloc[idx]
                ts_ms = int(row["datetime"].timestamp() * 1000)

                if row.get("atr_ratio", 1) < atr_thresh:
                    continue

                recent_closes = price_df["close"].iloc[max(0, idx-bars_up):idx+1].values
                if len(recent_closes) < bars_up + 1:
                    continue
                all_up = all(recent_closes[i] < recent_closes[i+1] for i in range(len(recent_closes)-1))
                all_down = all(recent_closes[i] > recent_closes[i+1] for i in range(len(recent_closes)-1))

                if all_up:
                    direction = "SHORT"
                elif all_down:
                    direction = "LONG"
                else:
                    continue

                result = calc_trade(idx, direction, 6)
                if not result:
                    continue

                if ts_ms <= split_ts_ms:
                    trades_is.append(result)
                else:
                    trades_oos.append(result)

            is_s = stats(trades_is)
            oos_s = stats(trades_oos)

            if (is_s and is_s["n"] >= 3) or (oos_s and oos_s["n"] >= 3):
                strategies.append({
                    "label": f"ATR>{atr_thresh}x + {bars_up}bar_streak → FADE",
                    "is_s": is_s, "oos_s": oos_s,
                })

    # Strategy: Large body candle (>2x ATR) → mean reversion
    print("\n--- STRATEGY: Large Body Candle → Mean Reversion ---")

    for body_mult in [1.5, 2.0, 2.5, 3.0]:
        trades_is = []
        trades_oos = []

        for idx in range(55, len(price_df) - 12):
            row = price_df.iloc[idx]
            ts_ms = int(row["datetime"].timestamp() * 1000)

            body = abs(row["close"] - row["open"])
            atr_window = price_high[max(0, idx-14):idx+1] - price_low[max(0, idx-14):idx+1]
            atr = np.mean(atr_window[-14:])

            if body < body_mult * atr:
                continue

            direction = "SHORT" if row["close"] > row["open"] else "LONG"

            result = calc_trade(idx, direction, 6)
            if not result:
                continue

            if ts_ms <= split_ts_ms:
                trades_is.append(result)
            else:
                trades_oos.append(result)

        is_s = stats(trades_is)
        oos_s = stats(trades_oos)

        if (is_s and is_s["n"] >= 3) or (oos_s and oos_s["n"] >= 3):
            strategies.append({
                "label": f"Body>{body_mult}x_ATR → FADE direction",
                "is_s": is_s, "oos_s": oos_s,
            })

    # Print all results
    print("\n" + "=" * 100)
    print("ALL STRATEGY RESULTS (sorted by OOS EV_net)")
    print("=" * 100)

    strategies_with_oos = [(s, s["oos_s"]["ev_net"]) for s in strategies if s["oos_s"] and s["oos_s"]["n"] >= 3]
    strategies_with_oos.sort(key=lambda x: -x[1])

    for s, _ in strategies_with_oos[:30]:
        is_s = s["is_s"]
        oos_s = s["oos_s"]
        print(f"\n  {s['label']}")
        if is_s:
            print(f"    IS:  {fmt(is_s)}")
        print(f"    OOS: {fmt(oos_s)}")
        verdict = "PASS" if oos_s["ev_net"] > 0 and oos_s["n"] >= 5 else "MARGINAL" if oos_s["ev_net"] > 0 else "FAIL"
        print(f"    → {verdict}")

    # Best summary
    print("\n" + "=" * 100)
    print("BEST OOS STRATEGIES (EV_net > 0, n >= 5)")
    print("=" * 100)

    best = [(s, s["oos_s"]["ev_net"]) for s in strategies
            if s["oos_s"] and s["oos_s"]["ev_net"] > 0 and s["oos_s"]["n"] >= 5]
    best.sort(key=lambda x: -x[1])

    if best:
        print(f"\n{'Strategy':<55} {'IS n':>5} {'OOS n':>6} {'IS EV_net':>10} {'OOS EV_net':>11} {'IS WR':>7} {'OOS WR':>7}")
        print("-" * 110)
        for s, _ in best[:20]:
            oos_s = s["oos_s"]
            is_s = s["is_s"]
            is_n = is_s["n"] if is_s else 0
            is_ev = is_s["ev_net"] if is_s else 0
            is_wr = is_s["wr"] if is_s else 0
            print(f"  {s['label']:<53} {is_n:>5} {oos_s['n']:>6} {is_ev:>+10.4f}% {oos_s['ev_net']:>+11.4f}% {is_wr:>6.1f}% {oos_s['wr']:>6.1f}%")
    else:
        print("\n  No strategies with OOS EV_net > 0 and n >= 5")


if __name__ == "__main__":
    main()
