#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 7: Integration Test - StateManager with Hyperliquid API
"""

import logging
from state_manager import StateManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_state_manager_integration():
    """StateManager と Hyperliquid API の統合テスト"""

    print("\n" + "=" * 70)
    print("  StateManager Integration Test with Hyperliquid API")
    print("=" * 70 + "\n")

    # Step 1: StateManager作成
    print("Step 1: Creating StateManager...")
    try:
        mgr = StateManager()
        print("  OK - StateManager created\n")
    except Exception as e:
        print(f"  ERROR - Failed to create StateManager: {e}\n")
        return False

    # Step 2: 現在価格を取得
    print("Step 2: Fetching current price from Hyperliquid API...")
    price = mgr._fetch_current_price('BTC')
    if price:
        print(f"  OK - Current BTC price: ${price:,.2f}\n")
    else:
        print("  WARN - Could not fetch current price\n")

    # Step 3: OHLCV データを取得
    print("Step 3: Fetching OHLCV data from Hyperliquid API...")
    ohlcv = mgr._fetch_ohlcv('BTC', interval=3600, limit=100)
    if ohlcv is not None:
        print(f"  OK - Fetched {len(ohlcv)} candles")
        last_row = ohlcv.iloc[-1]
        print(f"  Latest candle: {last_row['timestamp']} Close: ${last_row['close']:,.2f}\n")
    else:
        print("  WARN - Could not fetch OHLCV data\n")

    # Step 4: フル状態更新
    print("Step 4: Updating full state (price, OHLCV, indicators)...")
    state = mgr.update()

    if state.get('current_price'):
        print("  OK - Full state updated")
        print(f"  Current price: ${state.get('current_price'):,.2f}")
        print(f"  RSI (14): {state.get('indicators', {}).get('rsi', 'N/A')}")
        print(f"  ATR (14): ${state.get('indicators', {}).get('atr', 'N/A'):.0f}\n")
    else:
        print("  ERROR - State update failed\n")
        return False

    # Step 5: グリッド状態（GridBot がない場合は空）
    print("Step 5: Grid state (GridBot instance not provided)...")
    grid_state = state.get('grid_state', {})
    print(f"  Buy levels: {grid_state.get('buy_levels', [])}")
    print(f"  Sell levels: {grid_state.get('sell_levels', [])}\n")

    # Step 6: テクニカル指標が正しく計算されているか確認
    print("Step 6: Verifying technical indicators...")
    indicators = state.get('indicators', {})
    rsi = indicators.get('rsi')
    atr = indicators.get('atr')

    if rsi is not None and 0 <= rsi <= 100:
        print(f"  OK - RSI is valid: {rsi:.2f}")
    else:
        print(f"  WARN - RSI invalid or None: {rsi}")

    if atr is not None and atr > 0:
        print(f"  OK - ATR is valid: ${atr:.2f}")
    else:
        print(f"  WARN - ATR invalid or None: {atr}\n")

    print("=" * 70)
    print("  Integration Test Complete")
    print("=" * 70 + "\n")

    return True


if __name__ == "__main__":
    test_state_manager_integration()
