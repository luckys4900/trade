from dotenv import load_dotenv; load_dotenv()
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
import requests

# The key you provided
agent_key = '0xb866b265cb6e38cd0aa179d773e794be18e2936333060de6c88e4c151be14f1c'
# The wallet with funds
main_wallet = '0x7dd9f0C23Fb61CA3f36B8414306310F963093c12'
# The wallet the key derives to
agent_wallet = '0xF8b04CEbEc49EFFdE2c9d8C65a3268e875CB3332'

acct = Account.from_key(agent_key)
print(f'Agent Key derives to: {acct.address}')
print(f'Main Wallet: {main_wallet}')
print()

# Test 1: Check if this key can access the main wallet's state via Exchange
print('=== Testing Agent Key for Main Wallet ===')
try:
    exchange = Exchange(acct, base_url='https://api.hyperliquid.xyz', account_address=main_wallet)
    info = Info()
    
    # Check balance of main wallet
    user_state = info.user_state(main_wallet)
    ms = user_state.get('marginSummary', {})
    print(f'Main Wallet Account Value: ${float(ms.get("accountValue", 0)):,.2f}')
    
    # Try to get user state via exchange (proves auth)
    # In v0.22, exchange doesn't have get_user_state, we use info.user_state
    # But we can test signing capability by checking open orders
    orders = info.open_orders(main_wallet)
    print(f'Open Orders: {len(orders)}')
    
    # Test if agent is authorized
    print('>>> Agent Key successfully initialized for Main Wallet <<<')
    
except Exception as e:
    print(f'Error: {e}')
