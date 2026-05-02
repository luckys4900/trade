import json
from datetime import datetime

txs = json.load(open("data/robinhood_all_txs.json", "r", encoding="utf-8"))

timestamps = []
for tx in txs:
    bt = tx.get("status", {}).get("block_time", 0)
    if bt > 0:
        timestamps.append((bt, tx.get("txid", "")))

timestamps.sort()
print(f"Total TXs with block_time: {len(timestamps)}")
print(f"Oldest: {datetime.utcfromtimestamp(timestamps[0][0]).strftime('%Y-%m-%d %H:%M')} | tx={timestamps[0][1][:16]}...")
print(f"Newest: {datetime.utcfromtimestamp(timestamps[-1][0]).strftime('%Y-%m-%d %H:%M')} | tx={timestamps[-1][1][:16]}...")

print(f"\nLast 10 TXs:")
for ts, txid in timestamps[-10:]:
    print(f"  {datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')} | tx={txid[:16]}...")

print(f"\n2025+ TXs:")
post_2025 = [(ts, txid) for ts, txid in timestamps if ts >= 1735689600]
print(f"  Count: {len(post_2025)}")
for ts, txid in post_2025[:10]:
    print(f"  {datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')} | tx={txid[:16]}...")
