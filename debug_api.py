from dotenv import load_dotenv; load_dotenv()
import os, json, requests

wallet = os.getenv('HL_WALLET_ADDRESS')

url = 'https://api.hyperliquid.xyz/info'

# Test 1: userState
payload = {'type': 'userState', 'user': wallet}
resp = requests.post(url, json=payload, timeout=15)
print(f'userState - Status: {resp.status_code}')
print(f'Body: {resp.text[:1000]}')
print()

# Test 2: allMids
payload2 = {'type': 'allMids'}
resp2 = requests.post(url, json=payload2, timeout=15)
print(f'allMids - Status: {resp2.status_code}')
if resp2.status_code == 200:
    data = resp2.json()
    btc = data.get('BTC', 'N/A')
    print(f'BTC: ${btc}')
print()

# Test 3: meta
payload3 = {'type': 'meta'}
resp3 = requests.post(url, json=payload3, timeout=15)
print(f'meta - Status: {resp3.status_code}')
if resp3.status_code == 200:
    data3 = resp3.json()
    universe = data3.get('universe', [])
    print(f'Universe coins: {[c.get("name") for c in universe[:10]]}')
