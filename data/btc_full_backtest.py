# -*- coding: utf-8 -*-
"""
Full Historical Inflow Scraper + OOS Backtest
Scrapes all exchange wallet TXs via mempool.space pagination,
identifies external inflows, and runs IS/OOS validation.
"""

import os
import sys
import json
import time
import logging
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

EXCHANGE_WALLETS = {
    "Binance-1": "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
    "Binance-2": "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6",
    "Binance-3": "3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a",
    "Binance-BTCB": "3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb",
    "Robinhood": "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2",
    "Bitfinex": "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",
    "OKEx": "3MgEAFWu1HKSnZ5ZsC8qf61ZW18xrP5pgd",
    "OKX": "1CY7fykRLWXeSbKB885Kr4KjQxmDdvW923",
    "Crypto.com": "bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9",
    "BitMEX": "bc1qchctnvmdva5z9vrpxkkxck64v7nmzdtyxsrq64",
    "gate.io": "162bzZT2hJfv5Gm3ZmWfWfHJjCtMD6rHhw",
}

MIN_INFLOW_BTC = 50.0
MEMPOOL_API = "https://mempool.space/api"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("full_backtest")


def fetch_all_txs(address, max_pages=60):
    all_txs = []
    last_txid = None

    for page in range(1, max_pages + 1):
        if last_txid is None:
            url = f"{MEMPOOL_API}/address/{address}/txs"
        else:
            url = f"{MEMPOOL_API}/address/{address}/txs/chain/{last_txid}"

        try:
            r = requests.get(url, timeout=15)
            txs = r.json()
        except Exception:
            break

        if not txs:
            break

        all_txs.extend(txs)
        last_txid = txs[-1]["txid"]
        time.sleep(0.35)

    return all_txs


def analyze_inflow(tx, exchange_label, exchange_addr):
    addr_lower = exchange_addr.lower()
    inflow_value = 0
    sender_addrs = []

    for out in tx.get("vout", []):
        if out.get("scriptpubkey_address", "").lower() == addr_lower:
            inflow_value += out.get("value", 0)

    if inflow_value < MIN_INFLOW_BTC * 1e8:
        return None

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout", {})
        if prevout:
            addr = prevout.get("scriptpubkey_address", "")
            if addr and addr.lower() != addr_lower:
                sender_addrs.append(addr)

    if len(sender_addrs) == 0:
        return None

    return {
        "tx_hash": tx.get("txid", ""),
        "exchange": exchange_label,
        "inflow_btc": round(inflow_value / 1e8, 4),
        "sender_count": len(sender_addrs),
        "senders": sender_addrs[:5],
        "block_height": tx.get("status", {}).get("block_height", 0),
        "timestamp": tx.get("status", {}).get("block_time", 0),
    }


def scrape_all_wallets():
    cache_path = os.path.join(DATA_DIR, "full_inflow_events.json")

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:
            logger.info(f"Loading cached inflow events from {cache_path}")
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

    all_events = []

    for label, addr in EXCHANGE_WALLETS.items():
        logger.info(f"Scraping {label} ({addr[:16]}...)")
        txs = fetch_all_txs(addr, max_pages=60)
        logger.info(f"  Fetched {len(txs)} TXs")

        events_found = 0
        for tx in txs:
            result = analyze_inflow(tx, label, addr)
            if result:
                all_events.append(result)
                events_found += 1

        logger.info(f"  External inflows (50+ BTC): {events_found}")

    all_events.sort(key=lambda x: x["timestamp"])

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=2, ensure_ascii=False)

    logger.info(f"Total external inflows: {len(all_events)}")
    return all_events


def load_price_data():
    cache_path = os.path.join(DATA_DIR, "btc_price_4h_cache.csv")
    df = pd.read_csv(cache_path)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df


def match_and_analyze(events, price_df, horizon_h=24):
    price_ts = price_df["timestamp"].values if "timestamp" in price_df.columns else \
        (pd.to_datetime(price_df["datetime"]).astype(np.int64) // 10**6).values
    price_close = price_df["close"].values

    results = []
    for ev in events:
        if ev["timestamp"] == 0:
            continue

        ev_ts_ms = ev["timestamp"] * 1000
        idx = np.searchsorted(price_ts, ev_ts_ms)
        if idx < 1 or idx >= len(price_ts) - 1:
            continue

        entry_price = price_close[idx]
        target_ts_ms = ev_ts_ms + horizon_h * 3600 * 1000
        future_idx = np.searchsorted(price_ts, target_ts_ms)
        if future_idx >= len(price_ts):
            continue

        future_price = price_close[future_idx]
        change_pct = (future_price - entry_price) / entry_price * 100

        results.append({
            "exchange": ev["exchange"],
            "inflow_btc": ev["inflow_btc"],
            "sender_count": ev["sender_count"],
            "timestamp": ev["timestamp"],
            "datetime": datetime.utcfromtimestamp(ev["timestamp"]).strftime("%Y-%m-%d %H:%M"),
            "change_pct": round(change_pct, 4),
            "entry_price": round(entry_price, 2),
            "future_price": round(future_price, 2),
        })

    return results


def oos_validation(results, split_date="2025-06-01"):
    split_ts = int(datetime.strptime(split_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())

    is_data = [r for r in results if r["timestamp"] <= split_ts]
    oos_data = [r for r in results if r["timestamp"] > split_ts]

    return is_data, oos_data, split_date


def calc_ev(items):
    if not items:
        return None
    changes = [r["change_pct"] for r in items]
    drops = [c for c in changes if c < 0]
    rises = [c for c in changes if c >= 0]
    n = len(changes)
    wr = len(drops) / n
    avg_win = abs(np.mean(drops)) if drops else 0
    avg_loss = np.mean(rises) if rises else 0
    ev = wr * avg_win - (1 - wr) * avg_loss
    return {"n": n, "wr": wr * 100, "avg_win": avg_win, "avg_loss": avg_loss,
            "ev": ev, "median": float(np.median(changes)), "avg": float(np.mean(changes))}


def fmt(s):
    if s is None:
        return "no data"
    return f"n={s['n']:<4} WR={s['wr']:.0f}%  avg_win={s['avg_win']:.2f}%  avg_loss={s['avg_loss']:.2f}%  EV={s['ev']:+.4f}%  median={s['median']:+.3f}%"


def main():
    events = scrape_all_wallets()
    price_df = load_price_data()

    dates = [datetime.utcfromtimestamp(e["timestamp"]).strftime("%Y-%m-%d") for e in events if e["timestamp"] > 0]
    logger.info(f"\nEvents date range: {min(dates)} ~ {max(dates)}")

    print("\n" + "=" * 70)
    print("FULL HISTORICAL INFLOW BACKTEST (SCRAPED DATA)")
    print("=" * 70)

    for horizon in [4, 8, 12, 24, 48]:
        results = match_and_analyze(events, price_df, horizon_h=horizon)
        is_data, oos_data, split_date = oos_validation(results, "2025-06-01")

        print(f"\n--- {horizon}h horizon ---")
        print(f"  Split: {split_date} | IS: {len(is_data)} events | OOS: {len(oos_data)} events")

        all_s = calc_ev(results)
        is_s = calc_ev(is_data)
        oos_s = calc_ev(oos_data)
        print(f"  ALL: {fmt(all_s)}")
        print(f"  IS:  {fmt(is_s)}")
        print(f"  OOS: {fmt(oos_s)}")

    # Final: 24h by exchange
    print("\n" + "=" * 70)
    print("24h BY EXCHANGE (IS vs OOS)")
    print("=" * 70)

    results_24 = match_and_analyze(events, price_df, horizon_h=24)
    is_24, oos_24, _ = oos_validation(results_24, "2025-06-01")

    by_ex_is = defaultdict(list)
    by_ex_oos = defaultdict(list)
    for r in is_24:
        by_ex_is[r["exchange"]].append(r)
    for r in oos_24:
        by_ex_oos[r["exchange"]].append(r)

    all_exchanges = sorted(set(list(by_ex_is.keys()) + list(by_ex_oos.keys())))
    print(f"\n{'Exchange':<16} | {'IS':^50} | {'OOS':^50} | {'Verdict'}")
    print("-" * 140)

    for ex in all_exchanges:
        is_s = calc_ev(by_ex_is.get(ex, []))
        oos_s = calc_ev(by_ex_oos.get(ex, []))
        is_str = fmt(is_s) if is_s else "no data"
        oos_str = fmt(oos_s) if oos_s else "no data"

        if is_s and oos_s:
            if oos_s["ev"] > 0 and oos_s["n"] >= 5:
                verdict = "PASS"
            elif oos_s["ev"] > 0:
                verdict = "WEAK PASS"
            else:
                verdict = "FAIL"
        else:
            verdict = "INSUFFICIENT"

        print(f"  {ex:<14} | {is_str} | {oos_str} | {verdict}")

    # Best strategy recommendation
    print("\n" + "=" * 70)
    print("BEST STRATEGY SEARCH (IS EV > 0, maximize OOS EV)")
    print("=" * 70)

    for horizon in [4, 8, 12, 24, 48]:
        results = match_and_analyze(events, price_df, horizon_h=horizon)
        is_d, oos_d, _ = oos_validation(results, "2025-06-01")

        for ex in all_exchanges:
            is_items = [r for r in is_d if r["exchange"] == ex and 50 <= r["inflow_btc"] < 1000]
            oos_items = [r for r in oos_d if r["exchange"] == ex and 50 <= r["inflow_btc"] < 1000]
            is_s = calc_ev(is_items)
            oos_s = calc_ev(oos_items)

            if is_s and oos_s and is_s["ev"] > 0 and oos_s["ev"] > 0 and oos_s["n"] >= 5:
                print(f"  {ex:<14} {horizon}h | IS: n={is_s['n']} EV={is_s['ev']:+.4f}% | OOS: n={oos_s['n']} EV={oos_s['ev']:+.4f}% WR={oos_s['wr']:.0f}% | PASS")


if __name__ == "__main__":
    main()
