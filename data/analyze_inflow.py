import json
from collections import defaultdict

events = json.load(open('data/btc_inflow_events.json', 'r', encoding='utf-8'))
print(f'Total events: {len(events)}')

print('\n=== 50+ BTC inflows (external senders) ===')
big = [e for e in events if e['inflow_btc'] >= 50 and e['sender_count'] > 0]
big.sort(key=lambda x: x['inflow_btc'], reverse=True)
for e in big[:20]:
    print(f"  {e['inflow_btc']:>10.1f} BTC -> {e['exchange']:<16} senders={e['sender_count']} tx={e['tx_hash'][:12]}... ts={e['timestamp']}")

print('\n=== By exchange (50+ BTC, external) ===')
by_ex = defaultdict(list)
for e in big:
    by_ex[e['exchange']].append(e)
for ex, evts in sorted(by_ex.items(), key=lambda x: -sum(e['inflow_btc'] for e in x[1])):
    total = sum(e['inflow_btc'] for e in evts)
    print(f'  {ex:<16}: {len(evts)} events, {total:.0f} BTC total')

print('\n=== Internal transfers (senders=0, likely cold wallet moves) ===')
internal = [e for e in events if e['sender_count'] == 0 and e['inflow_btc'] >= 1000]
for e in internal[:10]:
    print(f"  {e['inflow_btc']:>12.1f} BTC -> {e['exchange']:<16} tx={e['tx_hash'][:12]}...")

print('\n=== Summary for strategy ===')
external_50 = [e for e in events if e['inflow_btc'] >= 50 and e['sender_count'] > 0]
print(f'External inflows >= 50 BTC: {len(external_50)} events')
print(f'Internal transfers >= 1000 BTC: {len(internal)} events (exclude from signals)')
