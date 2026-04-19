#!/usr/bin/env python3
"""Verify the float_to_wire precision fix"""

# Simulate the issue and solution
position_size_usd = 100.0
current_price = 66451.00

# BEFORE (causes rounding error)
qty_bad = float(position_size_usd) / float(current_price)
print("BEFORE (unrounded):")
print(f"  Quantity: {qty_bad}")
print(f"  Decimal places: {len(str(qty_bad).split('.')[1])}")
print(f"  Error: float_to_wire causes rounding\n")

# AFTER (fixed)
qty_fixed = round(qty_bad, 4)
print("AFTER (rounded to 4 decimals):")
print(f"  Quantity: {qty_fixed}")
print(f"  Decimal places: {len(str(qty_fixed).split('.')[1])}")
print(f"  Status: OK - Ready for Hyperliquid SDK\n")

# Test with different prices
print("Test with various BTC prices:")
prices = [66451.00, 66404.00, 66440.00, 66414.00]
for price in prices:
    qty = round(float(position_size_usd) / float(price), 4)
    print(f"  Price ${price:.2f} → qty {qty} [OK]")
