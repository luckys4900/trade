import json
from datetime import datetime, timezone

events = json.load(open("data/full_inflow_events.json", "r", encoding="utf-8"))
rh = [e for e in events if e["exchange"] == "Robinhood"]
split_ts = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp())
is_rh = [e for e in rh if e["timestamp"] <= split_ts]
oos_rh = [e for e in rh if e["timestamp"] > split_ts]

print(f"Total events: {len(events)}")
print(f"Robinhood events: {len(rh)}")
print(f"Robinhood IS: {len(is_rh)}, OOS: {len(oos_rh)}")
if rh:
    print(f"Date range: {datetime.utcfromtimestamp(rh[0]['timestamp']).strftime('%Y-%m-%d')} ~ {datetime.utcfromtimestamp(rh[-1]['timestamp']).strftime('%Y-%m-%d')}")
    print(f"\nLast 5 Robinhood events:")
    for e in rh[-5:]:
        dt = datetime.utcfromtimestamp(e["timestamp"]).strftime("%Y-%m-%d %H:%M")
        print(f"  {dt} | {e['inflow_btc']} BTC | tx={e['tx_hash'][:16]}...")
