#!/usr/bin/env python3
"""Debug actual payload being sent"""
import json
import eth_account
from hyperliquid.exchange import Exchange
from hyperliquid.utils.signing import order_request_to_order_wire
from decimal import Decimal, ROUND_DOWN

# Load config
with open("config.json") as f:
    config = json.load(f)

secret_key = config["secret_key"]
account_address = config["account_address"]
position_size_usd = 500

# Create account and exchange
account = eth_account.Account.from_key(secret_key)
exchange = Exchange(account, "https://api.hyperliquid.xyz", account_address=account_address)

# Simulate order creation
current_price = 66027.0
qty_decimal = Decimal(str(position_size_usd)) / Decimal(str(current_price))
qty_decimal = qty_decimal.quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
qty = float(qty_decimal)

order_request = {
    "coin": "BTC",
    "is_buy": True,
    "sz": qty,
    "limit_px": float(current_price),
    "order_type": {"limit": {}},
    "reduce_only": False,
}

print("=== ORDER REQUEST ===")
print(json.dumps(order_request, indent=2, default=str))

# Get asset info
from hyperliquid.info import Info
info = Info("https://api.hyperliquid.xyz", skip_ws=True)
asset = info.name_to_asset("BTC")
print(f"\n=== ASSET INFO ===")
print(f"Asset index: {asset}")

# Convert to wire format
try:
    order_wire = order_request_to_order_wire(order_request, asset)
    print(f"\n=== ORDER WIRE ===")
    print(json.dumps(order_wire, indent=2, default=str))
except Exception as e:
    print(f"Error creating order wire: {e}")

# Try to get what would be sent
print(f"\n=== ATTEMPTING ORDER ===")
try:
    # Manually build the action to see what gets sent
    action = exchange._build_order_action(order_request, None)
    print(json.dumps(action, indent=2, default=str))
except Exception as e:
    print(f"Error building action: {e}")
    import traceback
    traceback.print_exc()
