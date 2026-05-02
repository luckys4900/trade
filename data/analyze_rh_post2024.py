import json
import numpy as np
from datetime import datetime

txs = json.load(open("data/robinhood_all_txs.json", "r", encoding="utf-8"))
RH_ADDR = "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2".lower()
MIN_BTC = 50.0
split_ts = 1730419200  # 2024-11-01

post_split = [tx for tx in txs if tx.get("status", {}).get("block_time", 0) > split_ts]
print(f"TXs after 2024-11-01: {len(post_split)}")

inflows = []
outflows = []
internal = []

for tx in post_split:
    bt = tx["status"]["block_time"]
    inflow_val = 0
    outflow_val = 0
    rh_in = False
    rh_out = False
    ext_in = False
    ext_out = False

    for vout in tx.get("vout", []):
        addr = vout.get("scriptpubkey_address", "").lower()
        val = vout.get("value", 0)
        if addr == RH_ADDR:
            inflow_val += val
            rh_in = True
        else:
            ext_out = True
            outflow_val += val

    for vin in tx.get("vin", []):
        prevout = vin.get("prevout", {})
        if prevout:
            addr = prevout.get("scriptpubkey_address", "").lower()
            if addr == RH_ADDR:
                rh_out = True
            else:
                ext_in = True

    btc_in = inflow_val / 1e8
    btc_out = outflow_val / 1e8
    dt = datetime.utcfromtimestamp(bt).strftime("%Y-%m-%d %H:%M")
    txid = tx.get("txid", "")[:16]

    if rh_in and ext_in:
        direction = "INFLOW (external->RH)"
        inflows.append({"dt": dt, "btc": btc_in, "txid": txid})
    elif rh_out and ext_out:
        direction = "OUTFLOW (RH->external)"
        outflows.append({"dt": dt, "btc": btc_out, "txid": txid})
    elif rh_in and rh_out:
        direction = "INTERNAL"
        internal.append({"dt": dt, "btc": max(btc_in, btc_out), "txid": txid})
    else:
        direction = "OTHER"

    if btc_in >= MIN_BTC or btc_out >= MIN_BTC:
        print(f"  {dt} | {direction:<30} | in={btc_in:.2f} out={btc_out:.2f} | {txid}")

print(f"\n--- Summary after 2024-11-01 ---")
print(f"Inflows (external->RH): {len(inflows)}")
print(f"Outflows (RH->external): {len(outflows)}")
print(f"Internal: {len(internal)}")

inflows_50 = [i for i in inflows if i["btc"] >= MIN_BTC]
print(f"\nInflows >= 50 BTC: {len(inflows_50)}")
for i in inflows_50:
    print(f"  {i['dt']} | {i['btc']:.2f} BTC | {i['txid']}")

print(f"\n--- 2025-06-01 split ---")
oos_ts = 1748736000
is_inflows = [i for i in inflows_50 if datetime.strptime(i["dt"], "%Y-%m-%d %H:%M").timestamp() <= oos_ts]
oos_inflows = [i for i in inflows_50 if datetime.strptime(i["dt"], "%Y-%m-%d %H:%M").timestamp() > oos_ts]
print(f"IS (<=2025-06-01): {len(is_inflows)}")
print(f"OOS (>2025-06-01): {len(oos_inflows)}")
for i in oos_inflows:
    print(f"  {i['dt']} | {i['btc']:.2f} BTC | {i['txid']}")
