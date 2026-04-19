from eth_account import Account
import requests

wallet = '0xF8b04CEbEc49EFFdE2c9d8C65a3268e875CB3332'
key = '0xb866b265cb6e38cd0aa179d773e794be18e2936333060de6c88e4c151be14f1c'

# 1. Verify key matches wallet
acct = Account.from_key(key)
print(f'Derived Address: {acct.address}')
print(f'Target Address:  {wallet}')
print(f'Match: {acct.address.lower() == wallet.lower()}')
print()

# 2. Check balance
url = 'https://api.hyperliquid.xyz/info'
payload = {'type': 'clearinghouseState', 'user': wallet}
resp = requests.post(url, json=payload, timeout=15)
if resp.status_code == 200:
    data = resp.json()
    ms = data.get('marginSummary', {})
    av = float(ms.get('accountValue', 0))
    wd = float(data.get('withdrawable', 0))
    mu = float(ms.get('totalMarginUsed', 0))
    print(f'Account Value:    ${av:,.2f}')
    print(f'Withdrawable:     ${wd:,.2f}')
    print(f'Margin Used:      ${mu:,.2f}')
    positions = data.get('assetPositions', [])
    for p in positions:
        pos = p.get('position', {})
        szi = float(pos.get('szi', 0))
        if szi != 0:
            coin = pos.get('coin', '')
            entry = float(pos.get('entryPx', 0))
            print(f'Position: {coin} | Size: {szi} | Entry: ${entry:,.2f}')
else:
    print(f'Balance check error: {resp.status_code}')
