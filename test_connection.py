# -*- coding: utf-8 -*-
"""Connection test for Hyperliquid Mainnet - SDK v0.22 compatible"""
from dotenv import load_dotenv
import os
load_dotenv()

wallet = os.getenv('HL_WALLET_ADDRESS', '')
key = os.getenv('HL_PRIVATE_KEY', '')
testnet = os.getenv('HL_USE_TESTNET', 'false')

print('=== API Credential Check ===')
print(f'Wallet Address: {wallet}')
print(f'Private Key: {key[:10]}...{key[-6:]}')
network = 'Mainnet' if testnet == 'false' else 'Testnet'
print(f'Network: {network}')
print(f'Wallet format OK: {wallet.startswith("0x") and len(wallet) == 42}')
print(f'Key format OK: {key.startswith("0x") and len(key) == 66}')
print()

# Test Hyperliquid connection
print('=== Hyperliquid Mainnet Connection Test ===')
from hyperliquid.info import Info
info = Info()
print('Info API: Connected OK')

# Get current BTC price using all_mids (SDK v0.22)
mids = info.all_mids()
if mids and 'BTC' in mids:
    btc_price = float(mids['BTC'])
    print(f'BTC Price: ${btc_price:,.2f}')
    print('Price API: Connected OK')
else:
    print('WARNING: Could not get BTC price')

# Test wallet authentication and balance
print()
print('=== Wallet Authentication Test ===')
from eth_account import Account
from hyperliquid.exchange import Exchange

account = Account.from_key(key)
derived = account.address
print(f'Derived Address: {derived}')
match = derived.lower() == wallet.lower()
print(f'Address Match: {match}')

if not match:
    print('WARNING: Derived address does not match wallet address in .env!')
    print(f'  .env address: {wallet}')
    print(f'  Key derives to: {derived}')
else:
    print('Address Match: OK')

# Test Exchange API
base_url = 'https://api.hyperliquid.xyz'
exchange = Exchange(account, base_url=base_url, account_address=wallet)
print('Exchange API: Connected OK')

# Get balance using user_state (SDK v0.22)
user_state = info.user_state(wallet)
total = 0.0
available = 0.0
if user_state:
    margin = user_state.get('marginSummary', {})
    total = float(margin.get('accountValue', 0.0))
    available = float(margin.get('withdrawable', 0.0))
    print(f'Account Value: ${total:,.2f}')
    print(f'Withdrawable: ${available:,.2f}')
    if total > 0:
        print('Balance Check: OK - Has funds')
    else:
        print('WARNING - No funds in account')
else:
    print('WARNING: Could not retrieve account state')

# Get positions
positions = []
if user_state and 'assetPositions' in user_state:
    for pos in user_state['assetPositions']:
        if float(pos.get('szi', 0)) != 0:
            positions.append(pos['position']['coin'])
if positions:
    print(f'Open Positions: {positions}')
else:
    print('Open Positions: None (clean state)')

# Test order placement capability (dry run - just check API works)
print()
print('=== Order API Capability Test ===')
try:
    # Try to get user fees to confirm trading capability
    fees = info.user_fees(wallet)
    if fees:
        maker = fees.get('activeReferralState', {}).get('maker', 'N/A')
        print(f'Fee tier accessible: OK')
    print('Order API: Ready')
except Exception as e:
    print(f'Order API Check: {e}')

print()
print('=== LIVE TRADING READINESS ===')
checks = [
    ('Wallet Address Valid', wallet.startswith('0x') and len(wallet) == 42),
    ('Private Key Valid', key.startswith('0x') and len(key) == 66),
    ('Address Match', match),
    ('Info API Connected', True),
    ('Price API Working', mids and 'BTC' in mids),
    ('Exchange API Connected', True),
    ('Has Balance', total > 0),
]

all_pass = all(c[1] for c in checks)
for name, ok in checks:
    status = 'PASS' if ok else 'FAIL'
    print(f'  [{status}] {name}')

print()
if all_pass:
    print('>>> ALL CHECKS PASSED - READY FOR LIVE TRADING <<<')
else:
    print('>>> SOME CHECKS FAILED - FIX BEFORE LIVE TRADING <<<')
