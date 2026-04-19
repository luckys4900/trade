# -*- coding: utf-8 -*-
"""
BTC Exchange Inflow Monitor
Monitors validated exchange wallet addresses for large BTC inflows.
Uses mempool.space API (free, no key required).

Usage:
    python data/btc_inflow_monitor.py --once       # Single check
    python data/btc_inflow_monitor.py --loop 60    # Every 60 seconds
"""

import os
import sys
import json
import time
import logging
import argparse
import requests
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

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

MEMPOOL_API = "https://mempool.space/api"
MIN_INFLOW_BTC = 10.0
EVENTS_FILE = os.path.join(DATA_DIR, "btc_inflow_events.json")
SEEN_FILE = os.path.join(DATA_DIR, "btc_inflow_seen_txs.json")


def setup_logger():
    logger = logging.getLogger("inflow_monitor")
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_address_txs(address, logger, limit=10):
    url = f"{MEMPOOL_API}/address/{address}/txs"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"API {r.status_code} for {address[:16]}...")
    except Exception as e:
        logger.warning(f"API error for {address[:16]}...: {e}")
    return []


def analyze_inflow(tx, exchange_label, exchange_addr):
    exchange_addr_lower = exchange_addr.lower()
    inflow_value = 0
    sender_addresses = []

    for out in tx.get("vout", []):
        scriptpubkey_addr = out.get("scriptpubkey_address", "").lower()
        if scriptpubkey_addr == exchange_addr_lower:
            inflow_value += out.get("value", 0)

    if inflow_value == 0:
        return None

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout", {})
        if prevout:
            addr = prevout.get("scriptpubkey_address", "")
            if addr and addr.lower() != exchange_addr_lower:
                sender_addresses.append(addr)

    return {
        "tx_hash": tx.get("txid", ""),
        "exchange": exchange_label,
        "exchange_addr": exchange_addr,
        "inflow_sats": inflow_value,
        "inflow_btc": round(inflow_value / 1e8, 8),
        "senders": sender_addresses[:5],
        "sender_count": len(sender_addresses),
        "block_height": tx.get("status", {}).get("block_height", 0),
        "timestamp": tx.get("status", {}).get("block_time", 0),
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


def run_once(logger):
    seen_txs = load_json(SEEN_FILE, [])
    events = load_json(EVENTS_FILE, [])
    new_events = []

    logger.info(f"Checking {len(EXCHANGE_WALLETS)} exchange wallets...")

    for label, addr in EXCHANGE_WALLETS.items():
        txs = fetch_address_txs(addr, logger, limit=5)
        time.sleep(0.6)

        for tx in txs:
            txid = tx.get("txid", "")
            if txid in seen_txs:
                continue

            result = analyze_inflow(tx, label, addr)
            if result and result["inflow_btc"] >= MIN_INFLOW_BTC:
                new_events.append(result)
                logger.info(
                    f"INFLOW: {result['inflow_btc']:.4f} BTC -> {label} "
                    f"(senders: {result['sender_count']}, tx: {txid[:16]}...)"
                )

            seen_txs.append(txid)

    if new_events:
        events.extend(new_events)
        save_json(EVENTS_FILE, events)
        logger.info(f"Saved {len(new_events)} new inflow events (total: {len(events)})")
    else:
        logger.info("No new significant inflows detected")

    save_json(SEEN_FILE, seen_txs[-5000:])
    return new_events


def main():
    parser = argparse.ArgumentParser(description="BTC Exchange Inflow Monitor")
    parser.add_argument("--once", action="store_true", help="Single check")
    parser.add_argument("--loop", type=int, default=0, help="Loop interval in seconds")
    parser.add_argument("--min-btc", type=float, default=10.0, help="Minimum inflow BTC threshold")
    args = parser.parse_args()

    global MIN_INFLOW_BTC
    MIN_INFLOW_BTC = args.min_btc

    logger = setup_logger()
    logger.info(f"BTC Inflow Monitor started (threshold: {MIN_INFLOW_BTC} BTC)")
    logger.info(f"Monitoring {len(EXCHANGE_WALLETS)} exchange wallets")

    if args.once or args.loop == 0:
        run_once(logger)
    else:
        iteration = 0
        while True:
            iteration += 1
            logger.info(f"=== Iteration {iteration} ===")
            try:
                run_once(logger)
            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}")
            logger.info(f"Sleeping {args.loop}s...")
            time.sleep(args.loop)


if __name__ == "__main__":
    main()
