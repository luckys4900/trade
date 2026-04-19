#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
インタラクティブなショート戦略チャート
Plotly を使用したズーム・パン機能付き
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class InteractiveChartVisualizer:
    """Plotly を使用したインタラクティブチャート"""

    def __init__(self):
        self.MAKER_FEE = 0.00015
        self.SLIPPAGE = 0.001

    def calculate_rsi(self, closes, period=14):
        """RSI計算"""
        delta = pd.Series(closes).diff()
        gain = delta.clip(lower=0).ewm(alpha=1/period, min_periods=period).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/period, min_periods=period).mean()
        rs = gain / loss.replace(0, np.nan)
        return (100 - 100 / (1 + rs)).values

    def backtest_with_markers(self, df: pd.DataFrame, days: int = None):
        """バックテスト実行＆マーカーを記録"""
        if days:
            end_date = df['datetime'].max()
            start_date = end_date - timedelta(days=days)
            df = df[df['datetime'] >= start_date].copy()

        df = df.reset_index(drop=True)

        initial_balance = 100000
        balance = initial_balance
        trades = []
        signals = {
            'entries': [],
            'exits_profit': [],
            'exits_loss': [],
            'exits_timeout': []
        }

        in_position = False
        position_entry_price = None
        position_entry_idx = None

        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        rsi = self.calculate_rsi(closes)

        for i in range(14, len(df)):
            current_price = closes[i]
            high = highs[i]
            low = lows[i]
            curr_rsi = rsi[i]
            prev_rsi = rsi[i-1]

            # ショートエントリー
            if not in_position and curr_rsi > 60 and prev_rsi <= 60:
                entry_price = current_price * (1 + self.SLIPPAGE)
                position_entry_price = entry_price
                position_entry_idx = i
                in_position = True

                signals['entries'].append({
                    'idx': i,
                    'datetime': df['datetime'].iloc[i],
                    'price': entry_price,
                    'rsi': curr_rsi
                })
                continue

            # ポジション保有中の決済ロジック
            if in_position:
                # 1. 利益確定
                profit_pct = (position_entry_price - low) / position_entry_price
                if profit_pct >= 0.005:
                    exit_price = low * (1 - self.SLIPPAGE)
                    gross_pnl = (position_entry_price - exit_price)
                    fee_cost = position_entry_price * self.MAKER_FEE * 2
                    net_pnl = gross_pnl - fee_cost

                    balance += net_pnl
                    trades.append({'entry': position_entry_price, 'exit': exit_price, 'type': 'profit'})

                    signals['exits_profit'].append({
                        'idx': i,
                        'datetime': df['datetime'].iloc[i],
                        'price': exit_price,
                        'profit_pct': profit_pct
                    })
                    in_position = False

                # 2. 損切り
                elif high >= position_entry_price * 1.01:
                    exit_price = high * (1 + self.SLIPPAGE)
                    gross_loss = position_entry_price - exit_price
                    fee_cost = position_entry_price * self.MAKER_FEE * 2

                    balance -= (gross_loss + fee_cost)
                    trades.append({'entry': position_entry_price, 'exit': exit_price, 'type': 'loss'})

                    signals['exits_loss'].append({
                        'idx': i,
                        'datetime': df['datetime'].iloc[i],
                        'price': exit_price,
                        'loss_pct': (exit_price - position_entry_price) / position_entry_price
                    })
                    in_position = False

                # 3. タイムアウト
                elif (i - position_entry_idx) >= 10:
                    exit_price = current_price * (1 - self.SLIPPAGE)
                    gross_pnl = position_entry_price - exit_price
                    fee_cost = position_entry_price * self.MAKER_FEE * 2
                    net_pnl = gross_pnl - fee_cost

                    balance += net_pnl
                    trades.append({'entry': position_entry_price, 'exit': exit_price, 'type': 'timeout'})

                    signals['exits_timeout'].append({
                        'idx': i,
                        'datetime': df['datetime'].iloc[i],
                        'price': exit_price,
                        'hold_bars': i - position_entry_idx
                    })
                    in_position = False

        return {
            'df': df,
            'signals': signals,
            'rsi': rsi,
            'trades': trades,
            'final_balance': balance,
            'return': (balance - initial_balance) / initial_balance
        }

    def plot_interactive_chart(self, result: dict, title: str = "BTC SHORT STRATEGY"):
        """Plotlyを使用したインタラクティブチャート描画"""
        df = result['df']
        signals = result['signals']
        rsi = result['rsi']

        # サブプロット作成（キャンドルチャート + RSI）
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3],
            subplot_titles=("Price & Entries", "RSI(14)")
        )

        # ============ キャンドルチャート ============
        fig.add_trace(
            go.Candlestick(
                x=df['datetime'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='BTC/USDT',
                increasing_line_color='green',
                decreasing_line_color='red'
            ),
            row=1, col=1
        )

        # ============ エントリーシグナル ============
        for entry in signals['entries']:
            fig.add_trace(
                go.Scatter(
                    x=[entry['datetime']],
                    y=[entry['price']],
                    mode='markers',
                    marker=dict(
                        size=15,
                        color='blue',
                        symbol='triangle-up',
                        line=dict(color='darkblue', width=2)
                    ),
                    name='Entry (SHORT)',
                    hovertemplate=f"<b>Entry</b><br>Time: %{{x}}<br>Price: ${entry['price']:,.2f}<br>RSI: {entry['rsi']:.1f}<extra></extra>",
                    showlegend=(entry == signals['entries'][0]) if signals['entries'] else False
                ),
                row=1, col=1
            )

        # ============ 利確シグナル ============
        for exit_p in signals['exits_profit']:
            fig.add_trace(
                go.Scatter(
                    x=[exit_p['datetime']],
                    y=[exit_p['price']],
                    mode='markers',
                    marker=dict(
                        size=12,
                        color='green',
                        symbol='triangle-down',
                        line=dict(color='darkgreen', width=2)
                    ),
                    name='Take Profit',
                    hovertemplate=f"<b>TP</b><br>Time: %{{x}}<br>Price: ${exit_p['price']:,.2f}<br>Profit: +{exit_p['profit_pct']*100:.2f}%<extra></extra>",
                    showlegend=(exit_p == signals['exits_profit'][0]) if signals['exits_profit'] else False
                ),
                row=1, col=1
            )

        # ============ 損切りシグナル ============
        for exit_l in signals['exits_loss']:
            fig.add_trace(
                go.Scatter(
                    x=[exit_l['datetime']],
                    y=[exit_l['price']],
                    mode='markers',
                    marker=dict(
                        size=12,
                        color='red',
                        symbol='triangle-down',
                        line=dict(color='darkred', width=2)
                    ),
                    name='Stop Loss',
                    hovertemplate=f"<b>SL</b><br>Time: %{{x}}<br>Price: ${exit_l['price']:,.2f}<br>Loss: {exit_l['loss_pct']*100:.2f}%<extra></extra>",
                    showlegend=(exit_l == signals['exits_loss'][0]) if signals['exits_loss'] else False
                ),
                row=1, col=1
            )

        # ============ RSIチャート ============
        fig.add_trace(
            go.Scatter(
                x=df['datetime'],
                y=rsi,
                name='RSI(14)',
                line=dict(color='purple', width=2),
                hovertemplate="<b>RSI</b><br>Time: %{x}<br>Value: %{y:.1f}<extra></extra>"
            ),
            row=2, col=1
        )

        # RSI過買いレベル（60）
        fig.add_hline(
            y=60,
            line_dash="dash",
            line_color="red",
            name='Overbought (60)',
            row=2, col=1
        )

        # RSI強い過買いレベル（70）
        fig.add_hline(
            y=70,
            line_dash="dot",
            line_color="orange",
            name='Strong Overbought (70)',
            row=2, col=1
        )

        # 背景色：過買いゾーン
        fig.add_hrect(
            y0=60, y1=100,
            fillcolor="red", opacity=0.1,
            row=2, col=1,
            layer="below"
        )

        # ============ レイアウト設定 ============
        fig.update_layout(
            title_text=f"{title} - Interactive Chart (Zoom & Pan Enabled)",
            height=900,
            hovermode='x unified',
            template='plotly_dark',
            font=dict(size=10),
            xaxis_rangeslider_visible=False
        )

        # X軸設定
        fig.update_xaxes(title_text="Time", row=2, col=1)
        fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
        fig.update_yaxes(title_text="RSI", row=2, col=1)

        return fig

    def save_interactive_chart(self, fig, filename: str = "short_strategy_interactive.html"):
        """インタラクティブチャートをHTMLで保存"""
        fig.write_html(filename)
        logger.info(f"Interactive chart saved: {filename}")
        logger.info(f"Open this file in your web browser to zoom, pan, and interact with the chart!")
        return filename


def main():
    """メイン実行"""
    logger.info("=" * 80)
    logger.info("BTC SHORT STRATEGY - Interactive Chart Visualization")
    logger.info("=" * 80)

    # データ読み込み
    df = pd.read_csv('btc_usdt_1h.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)

    logger.info(f"Data loaded: {len(df)} candles")
    logger.info(f"Period: {df['datetime'].min()} to {df['datetime'].max()}\n")

    visualizer = InteractiveChartVisualizer()

    # 複数の期間でチャート作成
    periods = [7, 14, 30]

    for days in periods:
        logger.info(f"\nGenerating {days}-day interactive chart...")

        result = visualizer.backtest_with_markers(df, days=days)

        entries = len(result['signals']['entries'])
        profits = len(result['signals']['exits_profit'])
        losses = len(result['signals']['exits_loss'])
        ret = result['return']

        logger.info(f"  Entries: {entries}")
        logger.info(f"  Profits: {profits} | Losses: {losses}")
        logger.info(f"  Return: {ret:+.2%}")

        # チャート描画
        fig = visualizer.plot_interactive_chart(result, title=f"BTC SHORT STRATEGY ({days} Days)")

        # HTML保存
        filename = f"short_strategy_{days}days.html"
        visualizer.save_interactive_chart(fig, filename=filename)

    logger.info("\n" + "=" * 80)
    logger.info("All interactive charts generated successfully!")
    logger.info("=" * 80)
    logger.info("\nAvailable files:")
    logger.info("  - short_strategy_7days.html")
    logger.info("  - short_strategy_14days.html")
    logger.info("  - short_strategy_30days.html")
    logger.info("\nOpen these HTML files in your web browser to interact with the charts!")


if __name__ == '__main__':
    main()
