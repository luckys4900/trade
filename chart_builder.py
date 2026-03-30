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
