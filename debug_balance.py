from dotenv import load_dotenv; load_dotenv()
import os, json, requests

wallet = os.getenv('HL_WALLET_ADDRESS')
url = 'https://api.hyperliquid.xyz/info'

# Try different dex values
dex_values = ['', 'hyperliquid', 'Hyperliquid', None]

for dex in dex_values:
    payload = {'type': 'clearinghouseState', 'user': wallet}
    if dex is not None:
        payload['dex'] = dex
    resp = requests.post(url, json=payload, timeout=15)
    print(f'dex="{dex}" - Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        ms = data.get('marginSummary', {})
        print(f'  Account Value: ${ms.get("accountValue", "N/A")}')
        print(f'  Withdrawable: ${data.get("withdrawable", "N/A")}')
        positions = data.get('assetPositions', [])
        for p in positions:
            pos = p.get('position', {})
            if float(pos.get('szi', 0)) != 0:
                print(f'  Position: {pos["coin"]} {pos["szi"]} @ {pos.get("entryPx", "N/A")}')
    else:
        print(f'  Body: {resp.text[:200]}')
    print()
