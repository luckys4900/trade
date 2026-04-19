import requests, json

wallet = '0x7dd9f0C23Fb61CA3f36B8414306310F963093c12'
url = 'https://api.hyperliquid.xyz/info'

print(f'=== Wallet: {wallet} ===')
print()

# 1. Perpetual account balance
payload = {'type': 'clearinghouseState', 'user': wallet}
resp = requests.post(url, json=payload, timeout=15)
if resp.status_code == 200:
    data = resp.json()
    ms = data.get('marginSummary', {})
    print(f'--- Perpetual Account ---')
    print(f'  Account Value:    ${float(ms.get("accountValue", 0)):,.2f}')
    print(f'  Withdrawable:     ${float(data.get("withdrawable", 0)):,.2f}')
    print(f'  Margin Used:      ${float(ms.get("totalMarginUsed", 0)):,.2f}')
    print(f'  Total Position:   ${float(ms.get("totalNtlPos", 0)):,.2f}')
    
    positions = data.get('assetPositions', [])
    if positions:
        for p in positions:
            pos = p.get('position', {})
            szi = float(pos.get('szi', 0))
            if szi != 0:
                pnl = float(pos.get('unrealizedPnl', 0))
                print(f'  Position: {pos["coin"]} | Size: {szi} | Entry: ${float(pos.get("entryPx", 0)):,.2f} | PnL: ${pnl:,.2f}')
    else:
        print(f'  No open positions')
else:
    print(f'  Error: {resp.status_code}')

print()

# 2. Spot account balance
payload2 = {'type': 'spotState', 'user': wallet}
resp2 = requests.post(url, json=payload2, timeout=15)
if resp2.status_code == 200:
    data2 = resp2.json()
    balances = data2.get('balances', [])
    if balances:
        print(f'--- Spot Account ---')
        for b in balances:
            coin = b.get('coin', 'Unknown')
            total = float(b.get('total', 0))
            hold = float(b.get('hold', 0))
            if total > 0:
                print(f'  {coin}: {total:,.4f} (available: {total - hold:,.4f})')
    else:
        print(f'--- Spot Account ---')
        print(f'  No balances')
else:
    print(f'Spot Error: {resp2.status_code}')

print()

# 3. Recent trade history
payload3 = {'type': 'userFills', 'user': wallet}
resp3 = requests.post(url, json=payload3, timeout=15)
if resp3.status_code == 200:
    fills = resp3.json()
    print(f'--- Recent Trades ---')
    print(f'  Total fills: {len(fills)}')
    if fills:
        for f in fills[:5]:
            print(f'  {f.get("coin", "")} | {f.get("side", "")} | {f.get("sz", "")} @ ${float(f.get("px", 0)):,.2f} | Time: {f.get("time", "")}')
else:
    print(f'Trade history error: {resp3.status_code}')
