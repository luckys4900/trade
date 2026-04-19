import requests, json, time
from datetime import datetime

addr = "3MgEAFWu1HKSnZ5ZsC8qf61ZW18xrP5pgd"
print("=== OKEx wallet: paginated TX fetch test ===")

all_txs = []
page = 0
last_txid = None

while True:
    page += 1
    if last_txid is None:
        url = f"https://mempool.space/api/address/{addr}/txs"
    else:
        url = f"https://mempool.space/api/address/{addr}/txs/chain/{last_txid}"

    try:
        r = requests.get(url, timeout=15)
        txs = r.json()
    except Exception as e:
        print(f"Page {page}: error {e}")
        break

    if not txs:
        print(f"Page {page}: empty, stopping")
        break

    all_txs.extend(txs)
    oldest_ts = txs[-1].get("status", {}).get("block_time", 0)
    oldest_bh = txs[-1].get("status", {}).get("block_height", "?")
    oldest_dt = datetime.utcfromtimestamp(oldest_ts).strftime("%Y-%m-%d") if oldest_ts else "unconfirmed"

    print(f"Page {page}: {len(txs)} txs | oldest block {oldest_bh} ({oldest_dt})")

    last_txid = txs[-1]["txid"]

    if page >= 30:
        print("Reached 30 pages, stopping")
        break

    time.sleep(0.3)

print(f"\nTotal TXs fetched: {len(all_txs)}")

dates = []
for tx in all_txs:
    ts = tx.get("status", {}).get("block_time", 0)
    if ts:
        dates.append(datetime.utcfromtimestamp(ts))

if dates:
    dates.sort()
    print(f"Date range: {dates[0].strftime('%Y-%m-%d')} ~ {dates[-1].strftime('%Y-%m-%d')}")

import time
