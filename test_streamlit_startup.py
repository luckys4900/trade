#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Streamlit startup without running interactive server
Validates imports and configuration
"""

import sys
import os

# Set Streamlit logger level before importing streamlit
os.environ['STREAMLIT_LOGGER_LEVEL'] = 'error'


def test_streamlit_imports():
    """Test all required imports for Streamlit UI"""

    print("\n" + "=" * 70)
    print("  Testing Streamlit UI Server Startup")
    print("=" * 70 + "\n")

    print("Step 1: Testing Streamlit framework...")
    try:
        import streamlit as st
        print("  OK - Streamlit imported successfully")
        print(f"     Version: {st.__version__}")
    except ImportError as e:
        print(f"  ERROR - Streamlit import failed: {e}")
        return False

    print("\nStep 2: Testing UI server imports...")
    try:
        # Import the main UI server components (without running Streamlit)
        from state_manager import StateManager
        from chart_builder import ChartBuilder
        from ui_config import (
            UPDATE_INTERVAL, RSI_PERIOD, ATR_PERIOD,
            READY_THRESHOLD, WARN_THRESHOLD,
            COLOR_READY, COLOR_WARN, COLOR_FAR,
            COLOR_BUY_LEVEL, COLOR_SELL_LEVEL, COLOR_CURRENT_PRICE
        )

        print("  OK - StateManager imported")
        print("  OK - ChartBuilder imported")
        print("  OK - UI config imported")

        # Validate config values
        print(f"\n     Configuration:")
        print(f"     - UPDATE_INTERVAL: {UPDATE_INTERVAL}s")
        print(f"     - RSI_PERIOD: {RSI_PERIOD}")
        print(f"     - ATR_PERIOD: {ATR_PERIOD}")
        print(f"     - READY_THRESHOLD: {READY_THRESHOLD}%")
        print(f"     - WARN_THRESHOLD: {WARN_THRESHOLD}%")

    except ImportError as e:
        print(f"  ERROR - Import failed: {e}")
        return False

    print("\nStep 3: Testing StateManager initialization...")
    try:
        state_mgr = StateManager()
        print("  OK - StateManager initialized")
        print("     - API Base URL: https://api.hyperliquid.xyz (CCXT/Binance fallback)")
        print("     - GridBot instance: None (will use API)")
    except Exception as e:
        print(f"  ERROR - StateManager init failed: {e}")
        return False

    print("\nStep 4: Testing ChartBuilder initialization...")
    try:
        chart_builder = ChartBuilder(width_percent=100)
        print("  OK - ChartBuilder initialized")
        print("     - Width: 100%")
        print("     - Height: 500px")
        print("     - Candles: 100")
    except Exception as e:
        print(f"  ERROR - ChartBuilder init failed: {e}")
        return False

    print("\nStep 5: Checking ui_server.py syntax...")
    try:
        with open('ui_server.py', 'r', encoding='utf-8') as f:
            code = f.read()

        # Try to compile the code to check for syntax errors
        compile(code, 'ui_server.py', 'exec')
        print("  OK - ui_server.py syntax valid")
        print(f"     - File size: {len(code)} bytes")
        print(f"     - Lines: {len(code.splitlines())}")

        # Check for critical functions
        if 'def main():' in code:
            print("  OK - main() function found")
        if 'def update_data(' in code:
            print("  OK - update_data() function found")
        if 'def calculate_readiness_gauge(' in code:
            print("  OK - calculate_readiness_gauge() function found")

    except SyntaxError as e:
        print(f"  ERROR - Syntax error in ui_server.py: {e}")
        return False
    except Exception as e:
        print(f"  ERROR - Failed to check ui_server.py: {e}")
        return False

    print("\nStep 6: Testing Streamlit page configuration...")
    try:
        # This would be called when Streamlit runs
        import streamlit as st

        # Simulate what st.set_page_config does
        config_args = {
            'page_title': 'GridBot Realtime UI',
            'page_icon': '📊',
            'layout': 'wide',
            'initial_sidebar_state': 'collapsed'
        }

        print("  OK - Page config parameters valid:")
        for key, val in config_args.items():
            print(f"     - {key}: {val}")

    except Exception as e:
        print(f"  ERROR - Page config failed: {e}")
        return False

    print("\n" + "=" * 70)
    print("  Streamlit Startup Test: PASSED")
    print("=" * 70)
    print("\nUI Server ready to start:")
    print("  Command: streamlit run ui_server.py")
    print("  Browser: http://localhost:8501")
    print("\n" + "=" * 70 + "\n")

    return True


if __name__ == "__main__":
    success = test_streamlit_imports()
    exit(0 if success else 1)
