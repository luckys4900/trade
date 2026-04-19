# -*- coding: utf-8 -*-
"""Test Hyperliquid API endpoints"""

try:
    from hyperliquid.info import Info
    
    print("=" * 70)
    print("Testing different Hyperliquid API endpoints")
    print("=" * 70)
    
    # Test 1: Default (should connect to mainnet)
    print("\nTest 1: Default Info() constructor...")
    try:
        info_default = Info()
        meta = info_default.meta()
        print(f"  OK: Connected to default endpoint")
        print(f"  Symbols: {len(meta.get('universe', []))}")
    except Exception as e:
        print(f"  FAILED: {e}")
    
    # Test 2: Testnet endpoint
    print("\nTest 2: Testnet endpoint...")
    try:
        info_testnet = Info(base_url="https://api.hyperliquid.testnet/info")
        meta = info_testnet.meta()
        print(f"  OK: Connected to testnet")
        print(f"  Symbols: {len(meta.get('universe', []))}")
    except Exception as e:
        print(f"  FAILED: {e}")
    
    # Test 3: Mainnet endpoint explicitly
    print("\nTest 3: Mainnet endpoint explicitly...")
    try:
        info_mainnet = Info(base_url="https://api.hyperliquid.xyz/info")
        meta = info_mainnet.meta()
        print(f"  OK: Connected to mainnet")
        print(f"  Symbols: {len(meta.get('universe', []))}")
    except Exception as e:
        print(f"  FAILED: {e}")
    
except ImportError as e:
    print(f"Import Error: {e}")
    print("Install: pip install hyperliquid-python-sdk")
