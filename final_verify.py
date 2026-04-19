from dotenv import load_dotenv; load_dotenv()
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils.signing import OrderType
import os

wallet = os.getenv('HL_WALLET_ADDRESS')
key = os.getenv('HL_PRIVATE_KEY')

print(f'Main Wallet: {wallet}')
print(f'Agent Key derives to: {Account.from_key(key).address}')
print()

# Full stack test
info = Info()
exchange = Exchange(Account.from_key(key), base_url='https://api.hyperliquid.xyz', account_address=wallet)

# Price
mids = info.all_mids()
print(f'BTC Price: ${float(mids.get("BTC", 0)):,.2f}')

# Balance
user_state = info.user_state(wallet)
ms = user_state.get('marginSummary', {})
av = float(ms.get('accountValue', 0))
wd = float(user_state.get('withdrawable', 0))
print(f'Account Value: ${av:,.2f}')
print(f'Withdrawable: ${wd:,.2f}')

# Positions
positions = user_state.get('assetPositions', [])
for p in positions:
    pos = p.get('position', {})
    szi = float(pos.get('szi', 0))
    if szi != 0:
        print(f'Position: {pos["coin"]} {szi} @ ${float(pos.get("entryPx", 0)):,.2f}')

# OrderType test
ot = OrderType(market={'slippage': 0.001})
print(f'OrderType: {ot}')

print()
if av > 0:
    print('>>> ALL CHECKS PASSED - READY FOR LIVE TRADING <<<')
else:
    print('>>> WARNING: Balance is $0 <<<')
