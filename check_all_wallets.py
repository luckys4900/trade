from dotenv import load_dotenv; load_dotenv()
import os, json, requests

# Check BOTH wallets
wallets = {
    '.env wallet': '0x8455b70a5a0d942eb9a1598a0e9e1214a3b31b55',
    'config.json wallet': '0xE2Ce93147a19c5b8B1dd222499dE0A56987E1188',
}

url = 'https://api.hyperliquid.xyz/info'

for name, wallet in wallets.items():
    print(f'=== {name}: {wallet} ===')
    payload = {'type': 'clearinghouseState', 'user': wallet}
    resp = requests.post(url, json=payload, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        ms = data.get('marginSummary', {})
        account_value = ms.get('accountValue', '0')
        withdrawable = data.get('withdrawable', '0')
        total_margin = ms.get('totalMarginUsed', '0')
        total_pos = ms.get('totalNtlPos', '0')
        print(f'  Account Value:    ${float(account_value):,.2f}')
        print(f'  Withdrawable:     ${float(withdrawable):,.2f}')
        print(f'  Margin Used:      ${float(total_margin):,.2f}')
        print(f'  Total Position:   ${float(total_pos):,.2f}')
        
        positions = data.get('assetPositions', [])
        if positions:
            for p in positions:
                pos = p.get('position', {})
                szi = float(pos.get('szi', 0))
                if szi != 0:
                    print(f'  Position: {pos["coin"]} | Size: {szi} | Entry: ${float(pos.get("entryPx", 0)):,.2f} | PnL: ${float(pos.get("unrealizedPnl", 0)):,.2f}')
        else:
            print(f'  No open positions')
    else:
        print(f'  Error: {resp.status_code} - {resp.text[:200]}')
    print()

# Also check the secret_key from config.json
with open('config.json', 'r') as f:
    config = json.load(f)

secret_key = config.get('secret_key', '')
account_address = config.get('account_address', '')

print(f'=== config.json key authentication test ===')
print(f'Secret Key: {secret_key[:10]}...{secret_key[-6:]}')
print(f'Account Address: {account_address}')

from eth_account import Account
try:
    account = Account.from_key(secret_key)
    derived = account.address
    print(f'Derived Address: {derived}')
    print(f'Match: {derived.lower() == account_address.lower()}')
    
    # Check balance for THIS wallet
    payload = {'type': 'clearinghouseState', 'user': account_address}
    resp = requests.post(url, json=payload, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        ms = data.get('marginSummary', {})
        print(f'Account Value: ${float(ms.get("accountValue", 0)):,.2f}')
        print(f'Withdrawable: ${float(data.get("withdrawable", 0)):,.2f}')
except Exception as e:
    print(f'Error: {e}')
