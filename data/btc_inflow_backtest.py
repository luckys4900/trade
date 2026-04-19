# -*- coding: utf-8 -*-
"""
BTC Inflow Backtest - Price impact analysis after large exchange inflows
Matches inflow events to BTC price data and calculates post-inflow price changes.

Usage:
    python data/btc_inflow_backtest.py
"""

import os
import sys
import json
import time
import logging
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

EXCHANGE_WALLETS = {
    "Binance-1": "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
    "Binance-2": "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6",
    "Binance-3": "3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a",
    "Binance-BTCB": "3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb",
    "Binance-Pool": "bc1qx9t2l3pyny2spqpqlye8svce70nppwtaxwdrp4",
    "Robinhood": "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2",
    "Bitfinex": "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",
    "OKEx": "3MgEAFWu1HKSnZ5ZsC8qf61ZW18xrP5pgd",
    "OKX": "1CY7fykRLWXeSbKB885Kr4KjQxmDdvW923",
    "Crypto.com": "bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9",
    "Bitbank": "bc1qx2x5cqhymfcnjtg902ky6u5t5htmt7fvqztdsm028hkrvxcl4t2sjtpd9l",
    "BitMEX": "bc1qchctnvmdva5z9vrpxkkxck64v7nmzdtyxsrq64",
    "gate.io": "162bzZT2hJfv5Gm3ZmWfWfHJjCtMD6rHhw",
    "Coincheck": "bc1q4j7fcl8zx5yl56j00nkqez9zf3f6ggqchwzzcs5hjxwqhsgxvavq3qfgpr",
    "Tether": "bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfc27a4",
}

EXCLUDE_EXCHANGES = {"Tether", "Bitbank", "Coincheck"}

logger = logging.getLogger("inflow_backtest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def fetch_historical_prices(symbol="BTC/USDT", timeframe="4h", since_days=1200):
    cache_path = os.path.join(DATA_DIR, "btc_price_4h_cache.csv")
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:
            logger.info(f"Loading cached price data from {cache_path}")
            df = pd.read_csv(cache_path)
            df["datetime"] = pd.to_datetime(df["datetime"])
            return df

    logger.info(f"Fetching {symbol} {timeframe} candles from Binance...")
    import ccxt
    exchange = ccxt.binance({"enableRateLimit": True})

    since_ms = int((datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000)
    all_ohlcv = []
    current_since = since_ms

    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        current_since = ohlcv[-1][0] + 1
        if len(ohlcv) < 1000:
            break
        time.sleep(0.5)

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    df.to_csv(cache_path, index=False)
    logger.info(f"Fetched {len(df)} candles, saved to {cache_path}")
    return df


def load_events(min_btc=50, external_only=True):
    path = os.path.join(DATA_DIR, "btc_inflow_events.json")
    with open(path, "r", encoding="utf-8") as f:
        events = json.load(f)

    filtered = []
    for e in events:
        if e["inflow_btc"] < min_btc:
            continue
        if external_only and e["sender_count"] == 0:
            continue
        if e["exchange"] in EXCLUDE_EXCHANGES:
            continue
        if e["timestamp"] == 0:
            continue
        filtered.append(e)

    filtered.sort(key=lambda x: x["timestamp"])
    return filtered


def match_price_impact(events, price_df, horizons_hours=[4, 8, 12, 24, 48, 72]):
    results = []
    price_ts = price_df["timestamp"].values
    price_close = price_df["close"].values

    for ev in events:
        ev_ts_ms = ev["timestamp"] * 1000

        idx = np.searchsorted(price_ts, ev_ts_ms)
        if idx >= len(price_ts) - 1:
            continue
        if idx < 1:
            continue

        entry_price = price_close[idx]

        for h in horizons_hours:
            target_ts_ms = ev_ts_ms + h * 3600 * 1000
            future_idx = np.searchsorted(price_ts, target_ts_ms)
            if future_idx >= len(price_ts):
                continue

            future_price = price_close[future_idx]
            change_pct = (future_price - entry_price) / entry_price * 100

            results.append({
                "tx_hash": ev["tx_hash"][:16],
                "exchange": ev["exchange"],
                "inflow_btc": ev["inflow_btc"],
                "sender_count": ev["sender_count"],
                "timestamp": ev["timestamp"],
                "datetime": datetime.utcfromtimestamp(ev["timestamp"]).strftime("%Y-%m-%d %H:%M"),
                "horizon_h": h,
                "entry_price": round(entry_price, 2),
                "future_price": round(future_price, 2),
                "change_pct": round(change_pct, 4),
                "is_drop": bool(change_pct < 0),
            })

    return results


def analyze_results(results):
    if not results:
        logger.warning("No results to analyze")
        return

    logger.info("\n" + "=" * 70)
    logger.info("BTC INFLOW -> PRICE IMPACT BACKTEST RESULTS")
    logger.info("=" * 70)

    by_horizon = defaultdict(list)
    for r in results:
        by_horizon[r["horizon_h"]].append(r)

    for h in sorted(by_horizon.keys()):
        items = by_horizon[h]
        changes = [r["change_pct"] for r in items]
        drops = [r["change_pct"] for r in items if r["is_drop"]]
        rises = [r["change_pct"] for r in items if not r["is_drop"]]

        drop_rate = len(drops) / len(items) * 100
        avg_change = np.mean(changes)
        avg_drop = np.mean(drops) if drops else 0
        avg_rise = np.mean(rises) if rises else 0

        logger.info(f"\n--- {h}h horizon ({len(items)} events) ---")
        logger.info(f"  Drop rate: {drop_rate:.1f}% ({len(drops)}/{len(items)})")
        logger.info(f"  Avg change: {avg_change:+.3f}%")
        logger.info(f"  Avg drop: {avg_drop:+.3f}% | Avg rise: {avg_rise:+.3f}%")

    logger.info("\n" + "=" * 70)
    logger.info("BY INFLOW SIZE (24h horizon)")
    logger.info("=" * 70)

    h24 = [r for r in results if r["horizon_h"] == 24]
    buckets = [
        ("50-100 BTC", 50, 100),
        ("100-500 BTC", 100, 500),
        ("500-1000 BTC", 500, 1000),
        ("1000+ BTC", 1000, float("inf")),
    ]

    for label, lo, hi in buckets:
        items = [r for r in h24 if lo <= r["inflow_btc"] < hi]
        if not items:
            continue
        changes = [r["change_pct"] for r in items]
        drops = [c for c in changes if c < 0]
        drop_rate = len(drops) / len(changes) * 100
        avg = np.mean(changes)

        short_ev = drop_rate / 100 * abs(np.mean(drops)) if drops else 0
        long_ev = (100 - drop_rate) / 100 * (np.mean([c for c in changes if c >= 0]) if any(c >= 0 for c in changes) else 0)

        logger.info(f"\n  {label}: {len(items)} events")
        logger.info(f"    Drop rate: {drop_rate:.1f}% | Avg change: {avg:+.3f}%")
        logger.info(f"    Median: {np.median(changes):+.3f}% | Std: {np.std(changes):.3f}%")

    logger.info("\n" + "=" * 70)
    logger.info("BY EXCHANGE (24h horizon)")
    logger.info("=" * 70)

    by_ex = defaultdict(list)
    for r in h24:
        by_ex[r["exchange"]].append(r)

    for ex, items in sorted(by_ex.items(), key=lambda x: -len(x[1])):
        changes = [r["change_pct"] for r in items]
        drops = [c for c in changes if c < 0]
        drop_rate = len(drops) / len(changes) * 100
        logger.info(f"  {ex:<16}: {len(items):>3} events | Drop rate: {drop_rate:.0f}% | Avg: {np.mean(changes):+.3f}%")

    logger.info("\n" + "=" * 70)
    logger.info("SHORT STRATEGY EV ESTIMATE (24h horizon)")
    logger.info("=" * 70)

    for label, lo, hi in buckets:
        items = [r for r in h24 if lo <= r["inflow_btc"] < hi]
        if len(items) < 5:
            continue
        changes = [r["change_pct"] for r in items]
        drops = [c for c in changes if c < 0]
        rises = [c for c in changes if c >= 0]
        if not drops or not rises:
            continue

        wr = len(drops) / len(changes)
        avg_win = abs(np.mean(drops))
        avg_loss = np.mean(rises)
        ev = wr * avg_win - (1 - wr) * avg_loss

        logger.info(f"\n  {label}: {len(items)} events")
        logger.info(f"    Short WR (price drops): {wr*100:.1f}%")
        logger.info(f"    Avg short gain: {avg_win:.3f}% | Avg short loss: {avg_loss:.3f}%")
        logger.info(f"    EV per trade: {ev:+.4f}%")
        logger.info(f"    Verdict: {'POSITIVE' if ev > 0 else 'NEGATIVE'}")

    out_path = os.path.join(DATA_DIR, "btc_inflow_backtest_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"\nDetailed results saved to {out_path}")


def main():
    events = load_events(min_btc=50, external_only=True)
    logger.info(f"Loaded {len(events)} external inflow events (50+ BTC)")

    price_df = fetch_historical_prices()
    logger.info(f"Price data: {len(price_df)} candles from {price_df['datetime'].iloc[0]} to {price_df['datetime'].iloc[-1]}")

    results = match_price_impact(events, price_df)
    logger.info(f"Matched {len(results)} price impact data points")

    analyze_results(results)


if __name__ == "__main__":
    main()
