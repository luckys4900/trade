# -*- coding: utf-8 -*-
"""
Check Hyperliquid SDK version and available methods
"""

print("=" * 70)
print("Hyperliquid SDK Version Check")
print("=" * 70)
print()

try:
    from hyperliquid.info import Info
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils.types import PrivateKey
    from eth_account import Account
    from importlib_metadata import version
    
    print("Package Versions:")
    print(f"  hyperliquid-python-sdk: {version('hyperliquid-python-sdk')}")
    print(f"  eth-account: {version('eth-account')}")
    print()
    
    # Check Info class methods
    print("Info Class Methods:")
    info = Info()
    print(f"  Available attributes: {[attr for attr in dir(info) if not attr.startswith('_')]}")
    print()
    
    # Check Exchange class methods
    print("Exchange Class Methods:")
    print("  User state methods: ", end="")
    has_frontend = hasattr(info, 'frontend_user_state')
    has_old_user_state = hasattr(info, 'get_user_state')
    print(f"    - frontend_user_state: {has_frontend}")
    print(f"    - get_user_state: {has_old_user_state}")
    
    print("  Balance methods: ", end="")
    has_get_user_state = hasattr(info, 'get_user_state')
    has_front_user_state = hasattr(info, 'frontend_user_state')
    print(f"    - get_user_state (Exchange): {has_get_user_state}")
    print(f"    - frontend_user_state (Exchange): {has_front_user_state}")
    
    print("  Price methods: ", end="")
    has_l2_book = hasattr(info, 'l2_book')
    has_l3_book = hasattr(info, 'l3_book')
    has_all_mids = hasattr(info, 'all_mids')
    has_midpoint = hasattr(info, 'midpoint')
    
    print(f"    - l2_book: {has_l2_book}")
    print(f"    - l3_book: {has_l3_book}")
    print(f"    - all_mids: {has_all_mids}")
    print(f"    - midpoint: {has_midpoint}")
    
    # Check if Exchange has get_user_state method
    if hasattr(Exchange, 'get_user_state'):
        print("  EXCHANGE HAS get_user_state method")
    else:
        print("  EXCHANGE DOES NOT have get_user_state method")
    
    print()
    print("Conclusion:")
    print("Check above output and fix force_run_hl.py accordingly")
    print("=" * 70)

except ImportError as e:
    print(f"Import Error: {e}")
    print("Install hyperliquid-python-sdk and eth-account")
    print("pip install --upgrade hyperliquid-python-sdk eth-account")
