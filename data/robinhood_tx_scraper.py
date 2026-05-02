# -*- coding: utf-8 -*-
"""
Robinhood Wallet Deep Scraper
Scrapes ALL transactions from Robinhood's known BTC wallet using mempool.space
pagination. Checks both incoming (inflow) and identifies 50+ BTC external inflows.
"""

import json
import time
import logging
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

DATA_DIR = "data"
ROBINHOOD_ADDR = "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2"
MIN_INFLOW_BTC = 50.0
MEMPOOL_API = "https://mempool.space/api"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rh_scraper")


def fetch_all_txs(address, max_pages=200):
    all_txs = []
    last_txid = None
    seen_txids = set()

    for page in range(1, max_pages + 1):
        if last_txid is None:
            url = f"{MEMPOOL_API}/address/{address}/txs"
        else:
            url = f"{MEMPOOL_API}/address/{address}/txs/chain/{last_txid}"

        try:
            r = requests.get(url, timeout=20)
            txs = r.json()
        except Exception as e:
            logger.warning(f"Page {page} error: {e}")
            break

        if not txs or not isinstance(txs, list):
            break

        new_txs = [t for t in txs if t.get("txid") not in seen_txids]
        if not new_txs:
            break

        all_txs.extend(new_txs)
        for t in new_txs:
            seen_txids.add(t.get("txid"))

        last_txid = txs[-1].get("txid")
        if page % 10 == 0:
            logger.info(f"  Page {page}: total {len(all_txs)} TXs fetched")
        time.sleep(0.4)

    return all_txs


def analyze_inflow(tx, exchange_addr):
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

    ts = tx.get("status", {}).get("block_time", 0)
    return {
        "tx_hash": tx.get("txid", ""),
        "exchange": "Robinhood",
        "inflow_btc": round(inflow_value / 1e8, 4),
        "sender_count": len(sender_addrs),
        "senders": sender_addrs[:5],
        "block_height": tx.get("status", {}).get("block_height", 0),
        "timestamp": ts,
        "datetime": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts > 0 else "",
    }


def main():
    logger.info(f"=== Robinhood Deep Scraper ===")
    logger.info(f"Address: {ROBINHOOD_ADDR}")
    logger.info(f"Scraping up to 200 pages...")

    txs = fetch_all_txs(ROBINHOOD_ADDR, max_pages=200)
    logger.info(f"Total TXs fetched: {len(txs)}")

    with open(f"{DATA_DIR}/robinhood_all_txs.json", "w", encoding="utf-8") as f:
        json.dump(txs, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved to {DATA_DIR}/robinhood_all_txs.json")

    inflows = []
    for tx in txs:
        result = analyze_inflow(tx, ROBINHOOD_ADDR)
        if result:
            inflows.append(result)

    inflows.sort(key=lambda x: x["timestamp"])
    logger.info(f"External inflows (50+ BTC): {len(inflows)}")

    if inflows:
        print(f"\nDate range: {inflows[0]['datetime']} ~ {inflows[-1]['datetime']}")

        split_ts = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp())
        is_events = [e for e in inflows if e["timestamp"] <= split_ts]
        oos_events = [e for e in inflows if e["timestamp"] > split_ts]

        print(f"IS events (<=2025-06-01): {len(is_events)}")
        print(f"OOS events (>2025-06-01): {len(oos_events)}")

        if oos_events:
            print(f"\nOOS period events:")
            for e in oos_events:
                print(f"  {e['datetime']} | {e['inflow_btc']} BTC | tx={e['tx_hash'][:16]}...")

    with open(f"{DATA_DIR}/robinhood_inflow_events.json", "w", encoding="utf-8") as f:
        json.dump(inflows, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(inflows)} inflow events to {DATA_DIR}/robinhood_inflow_events.json")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total TXs: {len(txs)}")
    print(f"External inflows (50+ BTC): {len(inflows)}")
    if inflows:
        print(f"IS: {len(is_events)}, OOS: {len(oos_events)}")
        if oos_events:
            print("OOS VERIFICATION IS POSSIBLE")
        else:
            print("OOS VERIFICATION NOT POSSIBLE - all events in IS period")
            print(f"Latest event: {inflows[-1]['datetime']}")
            print("Robinhood may have changed wallet address after this date.")


if __name__ == "__main__":
    main()
