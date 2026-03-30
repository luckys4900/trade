import pytest
import pandas as pd
from datetime import datetime
from state_manager import StateManager
from chart_builder import ChartBuilder
from ui_config import READY_THRESHOLD, WARN_THRESHOLD

class TestStateManager:
    """StateManager のテスト"""

    def test_calculate_rsi(self):
        """RSI 計算テスト"""
        mgr = StateManager()

        # サンプルデータ：強い上昇トレンド（より多くのデータポイント）
        closes = [100 + i for i in range(50)]  # 50 個の上昇データ点
        rsi = mgr._calculate_rsi(closes, period=14)

        assert 0 <= rsi <= 100
        assert rsi >= 50  # 上昇トレンドなので中程度以上の RSI

    def test_calculate_atr(self):
        """ATR 計算テスト"""
        mgr = StateManager()

        high = [110, 111, 109, 112, 108, 113]
        low = [100, 101, 99, 102, 98, 103]
        close = [105, 106, 104, 107, 103, 108]

        atr = mgr._calculate_atr(high, low, close, period=3)

        assert atr > 0

    def test_calculate_entry_readiness_ready(self):
        """準備度計算テスト（READY）"""
        mgr = StateManager()

        current_price = 100.0
        buy_levels = [99.0, 98.0, 97.0]
        sell_levels = [101.0, 102.0, 103.0]

        readiness = mgr._calculate_entry_readiness(current_price, buy_levels, sell_levels)

        assert readiness['buy_readiness'] == 'READY'
        assert readiness['sell_readiness'] == 'READY'

    def test_calculate_entry_readiness_far(self):
        """準備度計算テスト（FAR）"""
        mgr = StateManager()

        current_price = 100.0
        buy_levels = [90.0, 89.0, 88.0]
        sell_levels = [110.0, 111.0, 112.0]

        readiness = mgr._calculate_entry_readiness(current_price, buy_levels, sell_levels)

        assert readiness['buy_readiness'] == 'FAR'
        assert readiness['sell_readiness'] == 'FAR'

class TestChartBuilder:
    """ChartBuilder のテスト"""

    def test_build_chart_html(self):
        """HTML 生成テスト"""
        builder = ChartBuilder()

        # ダミーデータ
        ohlcv_df = pd.DataFrame({
            'timestamp': pd.date_range(start='2026-01-01', periods=100, freq='1h'),
            'open': range(100, 200),
            'high': range(105, 205),
            'low': range(95, 195),
            'close': range(102, 202),
            'volume': [1000] * 100
        })

        html = builder.build_chart_html(
            ohlcv_df=ohlcv_df,
            current_price=150,
            buy_levels=[140, 130, 120],
            sell_levels=[160, 170, 180],
        )

        assert html is not None
        assert 'lightweight-charts' in html
        assert '150' in html  # 現在価格が含まれる
