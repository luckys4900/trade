#!/usr/bin/env python3
"""Diagnose Hyperliquid API issue"""
import json
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
import eth_account

# Load config
with open("config.json") as f:
    config = json.load(f)

secret_key = config.get("secret_key")
account_address = config.get("account_address")

print("=== API DIAGNOSIS ===\n")

# 1. Check eth account
print("1. Checking Ethereum Account...")
try:
    account = eth_account.Account.from_key(secret_key)
    print(f"   Account created: {account.address}")
    print(f"   Config address: {account_address}")
    print(f"   Match: {account.address.lower() == account_address.lower()}")
except Exception as e:
    print(f"   ERROR: {e}")

# 2. Check Info connection
print("\n2. Checking Info API connection...")
try:
    info = Info("https://api.hyperliquid.xyz", skip_ws=True)
    print(f"   Info object created")
    # Try to get user info
    user_info = info.user_state(account_address)
    print(f"   User state retrieved: {type(user_info)}")
except Exception as e:
    print(f"   ERROR: {e}")

# 3. Check Exchange connection
print("\n3. Checking Exchange API connection...")
try:
    account = eth_account.Account.from_key(secret_key)
    exchange = Exchange(account, "https://api.hyperliquid.xyz", account_address=account_address)
    print(f"   Exchange object created")
except Exception as e:
    print(f"   ERROR: {e}")

# 4. Test order structure
print("\n4. Testing order structure...")
try:
    from hyperliquid.utils.signing import order_request_to_order_wire
    
    test_order = {
        "coin": "BTC",
        "is_buy": True,
        "sz": 0.0075,
        "limit_px": 65960,
        "order_type": {"limit": {}},
        "reduce_only": False,
    }
    
    info = Info("https://api.hyperliquid.xyz", skip_ws=True)
    asset_info = info.name_to_asset("BTC")
    print(f"   Asset info for BTC: {asset_info}")
    
    # Try to convert to wire format
    order_wire = order_request_to_order_wire(test_order, asset_info)
    print(f"   Order wire created successfully")
    print(f"   Wire structure: {type(order_wire)}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n=== END DIAGNOSIS ===")
