# -*- coding: utf-8 -*-
"""Test Hyperliquid API connection"""

import os
from dotenv import load_dotenv
load_dotenv()

try:
    from hyperliquid.info import Info
    
    print("Testing Hyperliquid Info API...")
    
    # Test with default URL (no base_url parameter)
    try:
        info_default = Info()
        print("Using default Info() constructor...")
        meta = info_default.meta()
        universe = meta.get('universe', [])
        print(f"OK: Found {len(universe)} symbols")
        if len(universe) > 0:
            print(f"First 3 symbols: {universe[:3]}")
    except Exception as e:
        print(f"Error with default: {e}")
    
except ImportError as e:
    print(f"Import Error: {e}")
    print("Install: pip install hyperliquid-python-sdk")
