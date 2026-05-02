import json
import numpy as np
from datetime import datetime, timezone

txs = json.load(open("data/robinhood_all_txs.json", "r", encoding="utf-8"))
RH_ADDR = "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2".lower()

oos_ts = 1748736000  # 2025-06-01

post_oos = []
for tx in txs:
    bt = tx.get("status", {}).get("block_time", 0)
    if bt <= oos_ts or bt == 0:
        continue

    inflow_val = 0
    has_external_sender = False
    for vout in tx.get("vout", []):
        if vout.get("scriptpubkey_address", "").lower() == RH_ADDR:
            inflow_val += vout.get("value", 0)
    for vin in tx.get("vin", []):
        prevout = vin.get("prevout", {})
        if prevout and prevout.get("scriptpubkey_address", "").lower() != RH_ADDR:
            has_external_sender = True

    if inflow_val > 0 and has_external_sender:
        btc = inflow_val / 1e8
        dt = datetime.utcfromtimestamp(bt).strftime("%Y-%m-%d %H:%M")
        post_oos.append({"dt": dt, "btc": btc, "txid": tx.get("txid", "")[:16]})

post_oos.sort(key=lambda x: -x["btc"])

print(f"OOS period (after 2025-06-01) external inflows: {len(post_oos)}")
for i in post_oos:
    print(f"  {i['dt']} | {i['btc']:.4f} BTC | {i['txid']}")

print(f"\nBy size bucket:")
for lo, hi, label in [(0, 10, "0-10"), (10, 50, "10-50"), (50, 100, "50-100"), (100, 9999, "100+")]:
    items = [i for i in post_oos if lo <= i["btc"] < hi]
    print(f"  {label} BTC: {len(items)} events")
