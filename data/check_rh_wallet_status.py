import requests
import json

addr = "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2"
r = requests.get(f"https://mempool.space/api/address/{addr}", timeout=15)
d = r.json()

cs = d.get("chain_stats", {})
ms = d.get("mempool_stats", {})

print(f"Address: {addr}")
print(f"Funded TXOs: {cs.get('funded_txo_count', 0)}")
print(f"Spent TXOs: {cs.get('spent_txo_count', 0)}")
print(f"Funded sum: {cs.get('funded_txo_sum', 0)/1e8:.4f} BTC")
print(f"Spent sum: {cs.get('spent_txo_sum', 0)/1e8:.4f} BTC")
print(f"Current balance: {(cs.get('funded_txo_sum',0) - cs.get('spent_txo_sum',0))/1e8:.4f} BTC")
print(f"Mempool funded: {ms.get('funded_txo_count', 0)}")
