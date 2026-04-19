# グリッドボット リアルタイムUI実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GridBot の自動取引状況をリアルタイムで監視・可視化する Web UI を実装。Lightweight Charts でプロ級チャート操作、Streamlit で右パネル情報を表示。

**Architecture:** GridBot（既存）から取引状態・価格データを定期取得 → state_manager でデータ加工 → chart_builder で Lightweight Charts チャート生成 → Streamlit UI で統合表示。1 分ごと自動更新。

**Tech Stack:**
- **Frontend:** Streamlit + Lightweight Charts (JavaScript)
- **Backend:** Python (state_manager, chart_builder)
- **Data Source:** GridBot + Hyperliquid API
- **Libraries:** pandas, numpy, requests, streamlit

---

## ファイル構成（新規・修正）

```
C:\Users\user\Desktop\cursor\trade\
├── ui_config.py (新規)
│   └─ UI 設定定数（色、サイズ、更新間隔）
├── state_manager.py (新規)
│   └─ GridBot データ取得・加工（価格、グリッド状態、指標計算）
├── chart_builder.py (新規)
│   └─ Lightweight Charts HTML 生成（ローソク足、グリッドレベル、現在価格）
├── ui_server.py (新規)
│   └─ Streamlit メインアプリケーション（UI 統合）
├── test_ui.py (新規)
│   └─ UI 機能テスト
└── docs/superpowers/plans/
    └─ 2026-03-30-grid-bot-realtime-ui-implementation.md (このファイル)
```

---

## Task 1: UI 設定定数ファイル (ui_config.py)

**Files:**
- Create: `C:\Users\user\Desktop\cursor\trade\ui_config.py`

**説明:** UI 全体で使用する色・数値定数を集約。変更時に 1 箇所で管理できる。

- [ ] **Step 1: ui_config.py を作成し、色定数を定義**

```python
# UI色定義
COLOR_READY = "#5cb85c"    # 緑 (0-1%)
COLOR_WARN = "#f0ad4e"     # 黄 (1-5%)
COLOR_FAR = "#d9534f"      # 赤 (5%+)
COLOR_BUY_LEVEL = "#4a90e2"    # 買いレベル：青
COLOR_SELL_LEVEL = "#e94b3c"   # 売りレベル：赤
COLOR_CURRENT_PRICE = "#2c3e50"  # 現在価格：黒
COLOR_GRID_FILL = "#ecf0f1"    # グリッド背景

# UI設定
UPDATE_INTERVAL = 60       # 秒（1分ごと）
CHART_HEIGHT = 500         # ピクセル
CHART_CANDLES = 100        # 表示ローソク足数
RSI_PERIOD = 14
ATR_PERIOD = 14

# ゲージ判定閾値
READY_THRESHOLD = 1.0      # % (0-1%)
WARN_THRESHOLD = 5.0       # % (1-5%)

# API設定
API_TIMEOUT = 10           # 秒
MAX_RETRIES = 3
```

- [ ] **Step 2: コミット**

```bash
git add ui_config.py
git commit -m "feat: add UI configuration constants"
```

---

## Task 2: データ取得・加工層 (state_manager.py)

**Files:**
- Create: `C:\Users\user\Desktop\cursor\trade\state_manager.py`
- Depends on: `grid_bot.py`, `grid_manager.py` （既存）

**説明:** GridBot の稼働状態、現在価格、グリッドレベル、テクニカル指標を取得・計算。UI に必要なすべてのデータを提供。

- [ ] **Step 1: インポートと StateManager クラス骨組みを定義**

```python
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import requests
from ui_config import (
    UPDATE_INTERVAL, RSI_PERIOD, ATR_PERIOD,
    READY_THRESHOLD, WARN_THRESHOLD
)

logger = logging.getLogger(__name__)

class StateManager:
    """GridBot の取引状態を取得・加工する"""

    def __init__(self, grid_bot_instance=None, api_base_url="https://api.hyperliquid.xyz"):
        """
        Args:
            grid_bot_instance: GridBot インスタンス（同じプロセス内）
            api_base_url: Hyperliquid API ベース URL
        """
        self.grid_bot = grid_bot_instance
        self.api_base_url = api_base_url
        self.last_update = None
        self.current_price = None
        self.ohlcv_data = None
        self.grid_state = {}
        self.indicators = {}

    def update(self) -> Dict:
        """データを更新し、すべての状態を返す"""
        pass  # 後で実装
```

- [ ] **Step 2: Hyperliquid API から OHLCV データを取得するメソッドを実装**

```python
    def _fetch_ohlcv(self, symbol="BTC", timeframe="1h", limit=100) -> Optional[pd.DataFrame]:
        """
        Hyperliquid API から過去 100 本の 1h ローソク足データを取得

        Returns:
            DataFrame: columns = [timestamp, open, high, low, close, volume]
        """
        try:
            # 実装例：REST API 呼び出し
            # 詳細は Hyperliquid ドキュメント参照
            url = f"{self.api_base_url}/candles?symbol={symbol}&interval={timeframe}&limit={limit}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            if not data or "candles" not in data:
                logger.warning("No OHLCV data returned")
                return None

            df = pd.DataFrame(data["candles"])
            df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.astype({
                "open": float, "high": float, "low": float,
                "close": float, "volume": float
            })

            return df
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV: {e}")
            return None
```

- [ ] **Step 3: RSI 計算メソッドを実装**

```python
    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """
        RSI (Relative Strength Index) を計算

        Args:
            closes: 終値リスト
            period: RSI 計算期間（デフォルト 14）

        Returns:
            float: 0-100 の RSI 値
        """
        if len(closes) < period:
            return 50.0  # デフォルト：中立

        closes_series = pd.Series(closes)
        delta = closes_series.diff()

        gain = delta.clip(lower=0).ewm(alpha=1/period, min_periods=period).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/period, min_periods=period).mean()

        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)

        return float(rsi.iloc[-1])
```

- [ ] **Step 4: ATR 計算メソッドを実装**

```python
    def _calculate_atr(self, high: List[float], low: List[float], close: List[float],
                       period: int = 14) -> float:
        """
        ATR (Average True Range) を計算

        Returns:
            float: ATR 値（ドル）
        """
        if len(close) < period:
            return 0.0

        h = pd.Series(high)
        l = pd.Series(low)
        c = pd.Series(close)

        pc = c.shift(1)
        tr = pd.concat([
            h - l,
            (h - pc).abs(),
            (l - pc).abs(),
        ], axis=1).max(axis=1)

        atr = tr.ewm(alpha=1/period, min_periods=period).mean()
        return float(atr.iloc[-1])
```

- [ ] **Step 5: グリッド状態を GridBot から取得するメソッドを実装**

```python
    def _get_grid_state(self) -> Dict:
        """
        GridBot インスタンスからグリッド状態を取得

        Returns:
            dict: {
                'grid_center': float,
                'grid_range': float,
                'buy_levels': [float, ...],
                'sell_levels': [float, ...],
                'open_orders': [order_dict, ...],
                'filled_levels': set
            }
        """
        if not self.grid_bot:
            logger.warning("GridBot instance not provided")
            return {}

        try:
            grid_mgr = self.grid_bot.grid_manager
            return {
                'grid_center': grid_mgr.grid_center,
                'grid_range': grid_mgr.grid_range,
                'buy_levels': grid_mgr.buy_levels[:],
                'sell_levels': grid_mgr.sell_levels[:],
                'open_orders': list(grid_mgr.open_orders.values()),
                'filled_levels': grid_mgr.filled_levels.copy(),
            }
        except Exception as e:
            logger.error(f"Failed to get grid state: {e}")
            return {}
```

- [ ] **Step 6: 現在価格を取得するメソッドを実装**

```python
    def _fetch_current_price(self, symbol="BTC") -> Optional[float]:
        """
        Hyperliquid API から現在価格を取得

        Returns:
            float: 現在価格（ドル）
        """
        try:
            url = f"{self.api_base_url}/ticker?symbol={symbol}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()
            price = float(data.get("lastPrice", 0))
            return price
        except Exception as e:
            logger.error(f"Failed to fetch current price: {e}")
            return None
```

- [ ] **Step 7: 次のエントリーレベルと準備度を計算するメソッドを実装**

```python
    def _calculate_entry_readiness(self, current_price: float, buy_levels: List[float],
                                   sell_levels: List[float]) -> Dict:
        """
        次のエントリーレベル（買い・売り）と準備度を計算

        Returns:
            dict: {
                'next_buy_level': float or None,
                'next_sell_level': float or None,
                'distance_buy_pct': float,  # 負数 = 下降が必要
                'distance_sell_pct': float,
                'buy_readiness': str,  # 'READY', 'WARN', 'FAR'
                'sell_readiness': str,
            }
        """
        # 次の買いレベル（現在価格より下）
        next_buy = [lv for lv in sorted(buy_levels, reverse=True) if lv < current_price]
        next_buy_level = next_buy[0] if next_buy else (min(buy_levels) if buy_levels else None)

        # 次の売りレベル（現在価格より上）
        next_sell = [lv for lv in sorted(sell_levels) if lv > current_price]
        next_sell_level = next_sell[0] if next_sell else (max(sell_levels) if sell_levels else None)

        # 距離をパーセンテージで計算
        distance_buy_pct = ((next_buy_level - current_price) / current_price * 100) if next_buy_level else 0
        distance_sell_pct = ((next_sell_level - current_price) / current_price * 100) if next_sell_level else 0

        # 状態判定
        def _get_readiness(distance_pct: float) -> str:
            abs_dist = abs(distance_pct)
            if abs_dist <= READY_THRESHOLD:
                return "READY"
            elif abs_dist <= WARN_THRESHOLD:
                return "WARN"
            else:
                return "FAR"

        return {
            'next_buy_level': next_buy_level,
            'next_sell_level': next_sell_level,
            'distance_buy_pct': distance_buy_pct,
            'distance_sell_pct': distance_sell_pct,
            'buy_readiness': _get_readiness(distance_buy_pct),
            'sell_readiness': _get_readiness(distance_sell_pct),
        }
```

- [ ] **Step 8: TP・SL・利益推定を計算するメソッドを実装**

```python
    def _calculate_tp_sl_profit(self, current_price: float, next_buy_level: float,
                                next_sell_level: float, atr: float) -> Dict:
        """
        TP (売りレベル)・SL (買いレベル) と利益推定を計算

        Returns:
            dict: {
                'tp_price': float,
                'sl_price': float,
                'tp_profit_usd': float,
                'tp_profit_pct': float,
                'sl_loss_usd': float,
                'sl_loss_pct': float,
                'rr_ratio': float,  # リスク・リワード比
                'estimated_hours_to_tp': float,
                'estimated_hours_to_sl': float,
            }
        """
        tp_price = next_sell_level
        sl_price = next_buy_level

        # 利益・損失計算（エントリーが現在価格と仮定）
        tp_profit_usd = tp_price - current_price
        tp_profit_pct = (tp_profit_usd / current_price) * 100

        sl_loss_usd = current_price - sl_price
        sl_loss_pct = (sl_loss_usd / current_price) * 100

        # リスク・リワード比
        rr_ratio = tp_profit_usd / sl_loss_usd if sl_loss_usd > 0 else 0

        # 時間推定（ATR ベース）
        # 推定時間 = 距離 / (ATR / 24 時間)
        atr_per_hour = atr / 24.0 if atr > 0 else 1.0
        estimated_hours_to_tp = abs(tp_profit_usd) / atr_per_hour if atr_per_hour > 0 else 0
        estimated_hours_to_sl = sl_loss_usd / atr_per_hour if atr_per_hour > 0 else 0

        return {
            'tp_price': tp_price,
            'sl_price': sl_price,
            'tp_profit_usd': tp_profit_usd,
            'tp_profit_pct': tp_profit_pct,
            'sl_loss_usd': sl_loss_usd,
            'sl_loss_pct': sl_loss_pct,
            'rr_ratio': rr_ratio,
            'estimated_hours_to_tp': estimated_hours_to_tp,
            'estimated_hours_to_sl': estimated_hours_to_sl,
        }
```

- [ ] **Step 9: メイン update() メソッドを実装**

```python
    def update(self) -> Dict:
        """
        すべてのデータを更新し、UI に渡すデータを返す

        Returns:
            dict: UI 用の完全な状態データ
        """
        self.last_update = datetime.now()

        # 1. OHLCV データ取得
        self.ohlcv_data = self._fetch_ohlcv(symbol="BTC", timeframe="1h", limit=100)
        if self.ohlcv_data is None or len(self.ohlcv_data) < 14:
            logger.error("Not enough OHLCV data")
            return {}

        # 2. 現在価格取得
        self.current_price = self._fetch_current_price(symbol="BTC")
        if self.current_price is None:
            logger.error("Failed to fetch current price")
            return {}

        # 3. グリッド状態取得
        self.grid_state = self._get_grid_state()

        # 4. インジケーター計算
        rsi = self._calculate_rsi(self.ohlcv_data['close'].tolist(), period=RSI_PERIOD)
        atr = self._calculate_atr(
            self.ohlcv_data['high'].tolist(),
            self.ohlcv_data['low'].tolist(),
            self.ohlcv_data['close'].tolist(),
            period=ATR_PERIOD
        )

        self.indicators = {
            'rsi': rsi,
            'atr': atr,
        }

        # 5. エントリー準備度計算
        buy_levels = self.grid_state.get('buy_levels', [])
        sell_levels = self.grid_state.get('sell_levels', [])
        readiness = self._calculate_entry_readiness(self.current_price, buy_levels, sell_levels)

        # 6. TP・SL・利益計算
        next_buy = readiness.get('next_buy_level')
        next_sell = readiness.get('next_sell_level')
        tp_sl = self._calculate_tp_sl_profit(self.current_price, next_buy, next_sell, atr)

        # 7. すべてをまとめて返す
        return {
            'timestamp': self.last_update.isoformat(),
            'current_price': self.current_price,
            'ohlcv': self.ohlcv_data,
            'grid_state': self.grid_state,
            'indicators': self.indicators,
            'readiness': readiness,
            'tp_sl': tp_sl,
        }
```

- [ ] **Step 10: state_manager.py をコミット**

```bash
git add state_manager.py
git commit -m "feat: implement state manager for GridBot data acquisition"
```

---

## Task 3: Lightweight Charts ラッパー (chart_builder.py)

**Files:**
- Create: `C:\Users\user\Desktop\cursor\trade\chart_builder.py`
- Depends on: `ui_config.py`

**説明:** Lightweight Charts を使ったプロ級チャート HTML を生成。ローソク足、グリッドレベルライン、現在価格を描画。

- [ ] **Step 1: ChartBuilder クラス骨組みを定義**

```python
import json
from typing import List, Dict, Optional
import pandas as pd
from ui_config import (
    COLOR_BUY_LEVEL, COLOR_SELL_LEVEL, COLOR_CURRENT_PRICE,
    CHART_HEIGHT, CHART_CANDLES
)

logger = None  # Streamlit context で設定される

class ChartBuilder:
    """Lightweight Charts を使ったチャート HTML 生成"""

    def __init__(self, width_percent: int = 100):
        self.width_percent = width_percent
        self.chart_height = CHART_HEIGHT
        self.chart_candles = CHART_CANDLES

    def build_chart_html(self, ohlcv_df: pd.DataFrame, current_price: float,
                        buy_levels: List[float], sell_levels: List[float],
                        filled_levels: set = None) -> str:
        """
        チャート HTML を生成

        Args:
            ohlcv_df: [timestamp, open, high, low, close, volume] DataFrame
            current_price: 現在価格
            buy_levels: 買いレベル価格リスト
            sell_levels: 売りレベル価格リスト
            filled_levels: 約定済みレベルのセット

        Returns:
            str: Lightweight Charts HTML
        """
        pass  # 後で実装
```

- [ ] **Step 2: OHLCV データを Lightweight Charts フォーマットに変換**

```python
    def _format_ohlcv(self, ohlcv_df: pd.DataFrame, limit: int = None) -> List[Dict]:
        """
        DataFrame を Lightweight Charts フォーマットに変換

        Format: [{"time": "2026-03-30", "open": 67000, "high": 67500, "low": 66800, "close": 67234}, ...]
        """
        if limit:
            ohlcv_df = ohlcv_df.tail(limit)

        candles = []
        for idx, row in ohlcv_df.iterrows():
            candles.append({
                "time": row['timestamp'].strftime("%Y-%m-%d %H:%M"),
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
            })

        return candles
```

- [ ] **Step 3: グリッドレベルラインを生成するメソッド**

```python
    def _generate_level_lines(self, buy_levels: List[float], sell_levels: List[float],
                             filled_levels: set = None) -> str:
        """
        グリッドレベルラインの JavaScript コード生成

        Returns:
            str: 各レベルラインを描画する JavaScript コード
        """
        js_code = ""
        filled_levels = filled_levels or set()

        # 買いレベル（青）
        for i, price in enumerate(sorted(buy_levels)):
            style = "solid" if price not in filled_levels else "bold"
            color = COLOR_BUY_LEVEL if price not in filled_levels else "#2c3e50"
            width = 1 if style == "solid" else 2

            js_code += f"""
            chart.addLine({{
                price: {price},
                color: '{color}',
                width: {width},
                style: PriceScaleMarksAlign.Top,
            }});
            """

        # 売りレベル（赤）
        for i, price in enumerate(sorted(sell_levels)):
            style = "solid" if price not in filled_levels else "bold"
            color = COLOR_SELL_LEVEL if price not in filled_levels else "#2c3e50"
            width = 1 if style == "solid" else 2

            js_code += f"""
            chart.addLine({{
                price: {price},
                color: '{color}',
                width: {width},
                style: PriceScaleMarksAlign.Top,
            }});
            """

        return js_code
```

- [ ] **Step 4: 完全な HTML テンプレートを生成するメソッド**

```python
    def build_chart_html(self, ohlcv_df: pd.DataFrame, current_price: float,
                        buy_levels: List[float], sell_levels: List[float],
                        filled_levels: set = None) -> str:
        """チャート HTML を生成"""

        # データ準備
        candles = self._format_ohlcv(ohlcv_df, limit=self.chart_candles)
        candles_json = json.dumps(candles)

        # レベルラインコード
        level_lines_js = self._generate_level_lines(buy_levels, sell_levels, filled_levels)

        # HTML テンプレート
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                body {{ margin: 0; padding: 10px; background: #f5f5f5; }}
                #chart {{ width: {self.width_percent}%; height: {self.chart_height}px; border: 1px solid #ddd; border-radius: 4px; background: white; }}
                .info {{ margin-top: 10px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div id="chart"></div>
            <div class="info">
                <p>現在価格: ${current_price:.2f} | 青破線: 買いレベル (SL) | 赤破線: 売りレベル (TP)</p>
            </div>
            <script>
                const ChartLib = LightweightCharts;
                const chart = ChartLib.createChart(
                    document.getElementById('chart'),
                    {{
                        width: document.getElementById('chart').offsetWidth,
                        height: {self.chart_height},
                        layout: {{
                            textColor: '#333',
                            backgroundColor: '#fff',
                        }},
                        timeScale: {{
                            timeVisible: true,
                            secondsVisible: false,
                        }},
                    }}
                );

                // ローソク足シリーズ追加
                const candlestickSeries = chart.addCandlestickSeries({{
                    upColor: '#5cb85c',
                    downColor: '#d9534f',
                    borderUpColor: '#5cb85c',
                    borderDownColor: '#d9534f',
                    wickUpColor: '#5cb85c',
                    wickDownColor: '#d9534f',
                }});

                const candles = {candles_json};
                candlestickSeries.setData(candles);

                // グリッドレベルラインを追加（簡略版）
                {level_lines_js}

                // 現在価格ラインを追加
                const priceLine = {{
                    price: {current_price},
                    color: '{COLOR_CURRENT_PRICE}',
                    lineWidth: 2,
                    lineStyle: 0,
                    axisLabelVisible: true,
                    title: 'Current Price',
                }};
                candlestickSeries.createPriceLine(priceLine);

                // チャートのズーム・パン対応
                chart.timeScale().fitContent();

                // リサイズ対応
                window.addEventListener('resize', () => {{
                    const container = document.getElementById('chart');
                    chart.applyOptions({{
                        width: container.offsetWidth,
                        height: {self.chart_height},
                    }});
                }});
            </script>
        </body>
        </html>
        """

        return html
```

- [ ] **Step 5: chart_builder.py をコミット**

```bash
git add chart_builder.py
git commit -m "feat: implement lightweight charts builder"
```

---

## Task 4: Streamlit UI メインアプリケーション (ui_server.py)

**Files:**
- Create: `C:\Users\user\Desktop\cursor\trade\ui_server.py`
- Depends on: `state_manager.py`, `chart_builder.py`, `ui_config.py`

**説明:** Streamlit で UI 統合。左にチャート、右にパネル情報を配置。1 分ごと自動更新。

- [ ] **Step 1: インポートと page config を設定**

```python
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import logging

from state_manager import StateManager
from chart_builder import ChartBuilder
from ui_config import (
    UPDATE_INTERVAL, COLOR_READY, COLOR_WARN, COLOR_FAR
)

# ページ設定
st.set_page_config(
    page_title="GridBot Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

logger = logging.getLogger(__name__)

# CSS スタイル
st.markdown("""
    <style>
        .metric-box {
            background: #f9f9f9;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 12px;
            margin-bottom: 8px;
        }
        .value { font-size: 18px; font-weight: bold; }
        .label { font-size: 12px; color: #888; }
    </style>
""", unsafe_allow_html=True)
```

- [ ] **Step 2: State Manager インスタンスを初期化**

```python
@st.cache_resource
def get_state_manager():
    """StateManager をキャッシュして保持"""
    return StateManager(grid_bot_instance=None)  # GridBot インスタンスは別途設定

state_mgr = get_state_manager()

# アプリケーション状態
if 'last_update' not in st.session_state:
    st.session_state.last_update = None
if 'state_data' not in st.session_state:
    st.session_state.state_data = {}
```

- [ ] **Step 3: タイトルとヘッダーを表示**

```python
st.title("📈 BTC グリッドボット リアルタイム監視")

# 更新時刻表示
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.write("BTC グリッドトレーディング自動取引システム")
with col2:
    if st.session_state.last_update:
        st.write(f"🔄 最終更新: {st.session_state.last_update.strftime('%H:%M:%S')}")
with col3:
    if st.button("🔄 手動更新"):
        st.session_state.last_update = None
```

- [ ] **Step 4: データ更新関数を定義**

```python
def update_data():
    """StateManager からデータを取得・更新"""
    try:
        data = state_mgr.update()
        if data:
            st.session_state.state_data = data
            st.session_state.last_update = datetime.now()
            return True
        else:
            st.error("⚠️ データ更新に失敗しました")
            return False
    except Exception as e:
        st.error(f"❌ エラー: {e}")
        logger.error(f"Update error: {e}")
        return False
```

- [ ] **Step 5: メインレイアウト（2 列）を構築**

```python
# データが空の場合、初回更新
if not st.session_state.state_data:
    with st.spinner("📊 データを取得中..."):
        update_data()

state_data = st.session_state.state_data

if state_data:
    # 2 列レイアウト
    col_chart, col_panel = st.columns([3, 1], gap="medium")

    # ===== 左列: チャート =====
    with col_chart:
        st.subheader("📈 BTC/USD チャート")

        # チャート生成
        chart_builder = ChartBuilder(width_percent=100)
        ohlcv = state_data.get('ohlcv')
        current_price = state_data.get('current_price', 0)
        grid_state = state_data.get('grid_state', {})
        buy_levels = grid_state.get('buy_levels', [])
        sell_levels = grid_state.get('sell_levels', [])
        filled_levels = grid_state.get('filled_levels', set())

        chart_html = chart_builder.build_chart_html(
            ohlcv, current_price, buy_levels, sell_levels, filled_levels
        )

        st.components.v1.html(chart_html, height=CHART_HEIGHT + 50)

    # ===== 右列: パネル情報 =====
    with col_panel:
        st.subheader("📊 トレード情報")

        # セクション 1: 価格情報
        st.markdown("**📍 現在価格**")
        st.metric("", f"${current_price:,.2f}")

        readiness = state_data.get('readiness', {})
        tp_sl = state_data.get('tp_sl', {})
        indicators = state_data.get('indicators', {})

        # セクション 2: TP・SL
        st.markdown("**🎯 TP (売りレベル)**")
        tp_price = tp_sl.get('tp_price', 0)
        tp_profit = tp_sl.get('tp_profit_usd', 0)
        tp_profit_pct = tp_sl.get('tp_profit_pct', 0)
        st.write(f"${tp_price:,.2f}")
        st.write(f"+${tp_profit:.2f} / +{tp_profit_pct:.2f}%")

        st.markdown("**🛑 SL (買いレベル)**")
        sl_price = tp_sl.get('sl_price', 0)
        sl_loss = tp_sl.get('sl_loss_usd', 0)
        sl_loss_pct = tp_sl.get('sl_loss_pct', 0)
        st.write(f"${sl_price:,.2f}")
        st.write(f"-${sl_loss:.2f} / -{sl_loss_pct:.2f}%")

        # セクション 3: R/R 比
        st.markdown("**📊 リスク・リワード比**")
        rr_ratio = tp_sl.get('rr_ratio', 0)
        st.write(f"1:{rr_ratio:.2f}" if rr_ratio > 0 else "N/A")

        # セクション 4: 準備度ゲージ
        st.markdown("**🔔 買い準備度**")
        buy_readiness = readiness.get('buy_readiness', 'FAR')
        distance_buy_pct = readiness.get('distance_buy_pct', 0)

        # ゲージの色を決定
        if buy_readiness == 'READY':
            color = COLOR_READY
        elif buy_readiness == 'WARN':
            color = COLOR_WARN
        else:
            color = COLOR_FAR

        st.write(f"状態: **{buy_readiness}**")
        st.write(f"距離: {abs(distance_buy_pct):.2f}%")

        # プログレスバー表示（0-100% スケール）
        progress = min(100, abs(distance_buy_pct) * 20)  # 5% = 100% スケール
        st.progress(progress / 100, text=f"{progress:.0f}%")

        # セクション 5: インジケーター
        st.markdown("**📈 インジケーター**")
        rsi = indicators.get('rsi', 50)
        atr = indicators.get('atr', 0)

        st.write(f"RSI: **{rsi:.1f}**")
        if rsi < 30:
            st.write("↓ 過度に売られている")
        elif rsi > 70:
            st.write("↑ 過度に買われている")
        else:
            st.write("→ 中立")

        st.write(f"ATR: **${atr:.2f}**")

        # セクション 6: グリッド状態
        st.markdown("**⚙️ グリッド状態**")
        st.write(f"中心: ${grid_state.get('grid_center', 0):,.2f}")
        st.write(f"レンジ: ${grid_state.get('grid_range', 0):,.2f}")
        buy_count = len(grid_state.get('buy_levels', []))
        sell_count = len(grid_state.get('sell_levels', []))
        st.write(f"買い: {buy_count} | 売り: {sell_count}")
        st.write(f"約定済み: {len(grid_state.get('filled_levels', []))}")

else:
    st.warning("⚠️ データが利用できません。GridBot が稼働していることを確認してください。")

# ===== 自動更新ロジック =====
placeholder = st.empty()

def auto_update_loop():
    """1分ごとに自動更新"""
    while True:
        time.sleep(UPDATE_INTERVAL)
        update_data()
        st.rerun()

# Streamlit で自動更新（代替案）
if st.button("自動更新を開始（開発用）"):
    auto_update_loop()
```

- [ ] **Step 6: ui_server.py をコミット**

```bash
git add ui_server.py
git commit -m "feat: implement streamlit ui server"
```

---

## Task 5: テスト・検証 (test_ui.py)

**Files:**
- Create: `C:\Users\user\Desktop\cursor\trade\test_ui.py`

**説明:** UI コンポーネントの基本動作をテスト。

- [ ] **Step 1: テストの基本構造を定義**

```python
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

        # サンプルデータ：上昇トレンド
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114]
        rsi = mgr._calculate_rsi(closes, period=14)

        assert 0 <= rsi <= 100
        assert rsi > 70  # 強い上昇なので高い RSI

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
        ohlcv = pd.DataFrame({
            'timestamp': pd.date_range(start='2026-01-01', periods=100, freq='1h'),
            'open': range(100, 200),
            'high': range(105, 205),
            'low': range(95, 195),
            'close': range(102, 202),
            'volume': [1000] * 100
        })

        html = builder.build_chart_html(
            ohlcv=ohlcv,
            current_price=150,
            buy_levels=[140, 130, 120],
            sell_levels=[160, 170, 180],
        )

        assert html is not None
        assert 'lightweight-charts' in html
        assert '150' in html  # 現在価格が含まれる
```

- [ ] **Step 2: テストを実行**

```bash
pip install pytest pandas numpy requests streamlit

pytest test_ui.py -v
```

期待される出力：
```
test_ui.py::TestStateManager::test_calculate_rsi PASSED
test_ui.py::TestStateManager::test_calculate_atr PASSED
test_ui.py::TestStateManager::test_calculate_entry_readiness_ready PASSED
test_ui.py::TestStateManager::test_calculate_entry_readiness_far PASSED
test_ui.py::TestChartBuilder::test_build_chart_html PASSED

5 passed in 0.XX s
```

- [ ] **Step 3: test_ui.py をコミット**

```bash
git add test_ui.py
git commit -m "test: add ui component tests"
```

---

## Task 6: Streamlit サーバー起動テスト

**説明:** Streamlit UI が正常に起動・動作することを確認。

- [ ] **Step 1: 必要ライブラリをインストール**

```bash
pip install streamlit plotly pandas numpy requests hyperliquid
```

- [ ] **Step 2: Streamlit サーバーを起動**

```bash
streamlit run ui_server.py
```

期待される出力：
```
You can now view your Streamlit app in your browser.

  URL: http://localhost:8501

  If you don't see the browser automatically open, go here: http://localhost:8501
```

- [ ] **Step 3: ブラウザで確認**

Chrome で `http://localhost:8501` を開く。以下が表示されること：
- ✅ タイトル「BTC グリッドボット リアルタイム監視」
- ✅ 左側：チャート（Lightweight Charts）
- ✅ 右側：パネル（現在価格、TP・SL、準備度ゲージ、インジケーター）
- ✅ マウスホイールズーム、ドラッグパン可能
- ✅ 1 分ごとに自動更新（または手動ボタン）

- [ ] **Step 4: 動作確認ログ**

```
Streamlit app に以下が表示されることを確認：
- 📈 BTC/USD チャート（ローソク足 + グリッドレベルライン表示）
- 📍 現在価格: $67,234
- 🎯 TP価格、SL価格、利益額
- 📊 準備度ゲージ（READY/WARN/FAR）
- 📈 RSI、ATR
- ⚙️ グリッド状態
```

---

## Task 7: GridBot との統合確認

**説明:** GridBot が稼働している状態で、UI が正常にデータを取得・表示することを確認。

- [ ] **Step 1: GridBot を起動**

```bash
# 別ターミナルで
python grid_bot.py
```

- [ ] **Step 2: state_manager.py の GridBot インスタンス設定を確認**

`ui_server.py` の以下の行を修正して GridBot インスタンスを渡す：

```python
# 修正前
state_mgr = StateManager(grid_bot_instance=None)

# 修正後（同じプロセス内で GridBot を実行している場合）
from grid_bot import BTC_GridBot
grid_bot_instance = BTC_GridBot(GRID_CONFIG)  # または既存インスタンスを参照
state_mgr = StateManager(grid_bot_instance=grid_bot_instance)
```

- [ ] **Step 3: UI サーバーとの動作確認**

```bash
streamlit run ui_server.py
```

ブラウザで以下を確認：
- ✅ 現在価格がリアルタイムで更新される
- ✅ グリッドレベルが正確に表示される
- ✅ 準備度ゲージが現在価格と同期
- ✅ 1 分ごとに自動更新される

- [ ] **Step 4: 最終コミット**

```bash
git add .
git commit -m "feat: complete grid bot real-time ui implementation"
```

---

## Self-Review

**Spec 照合:**
- ✅ Task 1-3: 右サイドパネル型レイアウト（ui_server.py）
- ✅ Task 2-4: READY/WARN/FAR ゲージ表示（state_manager + ui_server.py）
- ✅ Task 2-4: TP・SL・R/R比表示（state_manager + ui_server.py）
- ✅ Task 3: Lightweight Charts チャート（chart_builder.py）
- ✅ Task 4-6: 1分ごと自動更新（ui_server.py）
- ✅ Task 5-7: テスト・検証

**プレースホルダー確認:**
- ✅ すべてのメソッドに実装コード含む
- ✅ test cases に assert 含む
- ✅ テスト実行コマンド明記
- ✅ 期待される出力を記述

**型・メソッド一貫性:**
- ✅ `StateManager.update()` → Dict return
- ✅ `ChartBuilder.build_chart_html()` → str return
- ✅ 色定数は ui_config.py で一元管理

---

## 実装完了条件

すべての Task が完了し、以下が達成されること：

1. ✅ `ui_config.py`, `state_manager.py`, `chart_builder.py`, `ui_server.py`, `test_ui.py` が作成される
2. ✅ `pytest test_ui.py` で全テスト PASS
3. ✅ `streamlit run ui_server.py` で UI が起動
4. ✅ Chrome で `http://localhost:8501` に接続でき、チャート + 右パネルが表示される
5. ✅ マウス操作（ズーム・パン）が正常に動作
6. ✅ 1 分ごと自動更新が確認される
7. ✅ GridBot との連携で現在価格・グリッド状態がリアルタイム同期される