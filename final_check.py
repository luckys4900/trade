from dotenv import load_dotenv; load_dotenv()
import os
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils.signing import OrderType

wallet = os.getenv('HL_WALLET_ADDRESS')
key = os.getenv('HL_PRIVATE_KEY')

# Verify
acct = Account.from_key(key)
print(f'Wallet: {wallet}')
print(f'Derived: {acct.address}')
print(f'Match: {acct.address.lower() == wallet.lower()}')

# Test full stack
info = Info()
mids = info.all_mids()
btc = float(mids.get('BTC', 0))
print(f'BTC Price: ${btc:,.2f}')

exchange = Exchange(acct, base_url='https://api.hyperliquid.xyz', account_address=wallet)
user_state = info.user_state(wallet)
ms = user_state.get('marginSummary', {})
av = float(ms.get('accountValue', 0))
wd = float(user_state.get('withdrawable', 0))
print(f'Account Value: ${av:,.2f}')
print(f'Withdrawable: ${wd:,.2f}')

# Test OrderType
ot = OrderType(market={'slippage': 0.001})
print(f'OrderType created: {ot}')

print()
if av > 0:
    print('>>> ALL COMPONENTS READY FOR LIVE TRADING <<<')
else:
    print('>>> WARNING: Account balance is $0. Cannot trade <<<')
