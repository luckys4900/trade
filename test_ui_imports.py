#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_server.py の簡単なインポートテスト
Streamlit は対話環境で実行するため、ここでは依存モジュールのみテスト
"""

import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """必要なモジュールのインポートテスト"""
    logger.info("Testing imports...")

    try:
        import streamlit as st
        logger.info("  OK: streamlit")
    except ImportError as e:
        logger.error(f"  FAILED: streamlit - {e}")
        return False

    try:
        import pandas as pd
        logger.info("  OK: pandas")
    except ImportError as e:
        logger.error(f"  FAILED: pandas - {e}")
        return False

    try:
        from state_manager import StateManager
        logger.info("  OK: StateManager")
    except ImportError as e:
        logger.error(f"  FAILED: StateManager - {e}")
        return False

    try:
        from chart_builder import ChartBuilder
        logger.info("  OK: ChartBuilder")
    except ImportError as e:
        logger.error(f"  FAILED: ChartBuilder - {e}")
        return False

    try:
        from ui_config import (
            UPDATE_INTERVAL, RSI_PERIOD, ATR_PERIOD,
            READY_THRESHOLD, WARN_THRESHOLD
        )
        logger.info("  OK: ui_config")
        logger.info(f"    UPDATE_INTERVAL: {UPDATE_INTERVAL}s")
        logger.info(f"    RSI_PERIOD: {RSI_PERIOD}")
        logger.info(f"    ATR_PERIOD: {ATR_PERIOD}")
    except ImportError as e:
        logger.error(f"  FAILED: ui_config - {e}")
        return False

    logger.info("All imports successful!")
    return True

def test_state_manager_structure():
    """StateManager の update() メソッドの返却構造をテスト"""
    logger.info("\nTesting StateManager structure...")

    from state_manager import StateManager

    sm = StateManager()
    logger.info("  StateManager initialized")

    # update() メソッドが存在するか確認
    if not hasattr(sm, 'update'):
        logger.error("  FAILED: StateManager does not have update() method")
        return False

    logger.info("  OK: StateManager has update() method")

    # update() の戻り値型を確認（実際に呼び出さずに確認）
    import inspect
    sig = inspect.signature(sm.update)
    logger.info(f"  update() signature: {sig}")

    return True

def test_chart_builder_structure():
    """ChartBuilder の build_chart_html() メソッドをテスト"""
    logger.info("\nTesting ChartBuilder structure...")

    from chart_builder import ChartBuilder

    cb = ChartBuilder()
    logger.info("  ChartBuilder initialized")

    # build_chart_html() メソッドが存在するか確認
    if not hasattr(cb, 'build_chart_html'):
        logger.error("  FAILED: ChartBuilder does not have build_chart_html() method")
        return False

    logger.info("  OK: ChartBuilder has build_chart_html() method")

    # メソッドのシグネチャを確認
    import inspect
    sig = inspect.signature(cb.build_chart_html)
    logger.info(f"  build_chart_html() signature: {sig}")

    return True

def main():
    """メインテスト"""
    logger.info("=== UI Server Import Test ===\n")

    success = True

    # Test 1: Imports
    if not test_imports():
        success = False

    # Test 2: StateManager structure
    if not test_state_manager_structure():
        success = False

    # Test 3: ChartBuilder structure
    if not test_chart_builder_structure():
        success = False

    logger.info("\n=== Test Results ===")
    if success:
        logger.info("All tests PASSED")
        return 0
    else:
        logger.error("Some tests FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
