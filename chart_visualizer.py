#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ショート戦略のチャート可視化
1時間足のOHLCVデータと、RSI、エントリー/イグジットタイミングを表示
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from datetime import timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class ChartVisualizer:
    """チャート描画とストラテジー可視化"""

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

    def calculate_atr(self, high, low, close, period=14):
        """ATR計算"""
        h = pd.Series(high)
        l = pd.Series(low)
        c = pd.Series(close)
        pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/period, min_periods=period).mean()
        return atr.values

    def backtest_with_markers(self, df: pd.DataFrame, days: int = None):
        """バックテスト実行＆エントリー/イグジットマーカーを記録"""
        if days:
            from datetime import timedelta
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
                # 1. 利益確定: 0.5% 下がった
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

                # 2. 損切り: 1% 上がった
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

                # 3. タイムアウト: 10時間保有
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

    def plot_chart(self, result: dict, title: str = "BTC SHORT STRATEGY"):
        """チャートを描画"""
        df = result['df']
        signals = result['signals']
        rsi = result['rsi']

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={'height_ratios': [3, 1]})
        fig.suptitle(f'{title} - Last {len(df)} Hours', fontsize=14, fontweight='bold')

        # ============ キャンドルチャート ============
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        x = np.arange(len(df))
        width = 0.6

        # ローソク足の色
        colors = ['red' if closes[i] < opens[i] else 'green' for i in range(len(df))]

        # 高値と安値の線
        for i in range(len(df)):
            ax1.plot([i, i], [lows[i], highs[i]], color='gray', linewidth=0.5, alpha=0.5)

        # 始値と終値の棒
        for i in range(len(df)):
            ax1.add_patch(Rectangle((i - width/2, min(opens[i], closes[i])),
                                    width, abs(closes[i] - opens[i]),
                                    facecolor=colors[i], edgecolor='black', linewidth=0.5))

        # ============ エントリータイミング ============
        for entry in signals['entries']:
            idx = entry['idx']
            price = entry['price']
            rsi_val = entry['rsi']

            # エントリー地点をプロット
            ax1.scatter(idx, price, color='blue', s=200, marker='^', zorder=5, label='Entry (SHORT)' if idx == signals['entries'][0]['idx'] else '')
            ax1.text(idx, price + 200, f"Entry\nRSI:{rsi_val:.1f}", fontsize=8, ha='center', color='blue')

        # ============ 利確タイミング ============
        for exit_p in signals['exits_profit']:
            idx = exit_p['idx']
            price = exit_p['price']
            profit = exit_p['profit_pct']

            ax1.scatter(idx, price, color='green', s=200, marker='v', zorder=5)
            ax1.text(idx, price - 300, f"TP\n+{profit:.2%}", fontsize=8, ha='center', color='green')

        # ============ 損切りタイミング ============
        for exit_l in signals['exits_loss']:
            idx = exit_l['idx']
            price = exit_l['price']
            loss = exit_l['loss_pct']

            ax1.scatter(idx, price, color='red', s=200, marker='v', zorder=5)
            ax1.text(idx, price + 300, f"SL\n{loss:.2%}", fontsize=8, ha='center', color='red')

        # ============ ポジション保有中の背景 ============
        in_position = False
        entry_idx = None

        for entry in signals['entries']:
            entry_idx = entry['idx']
            in_position = True

            # 対応するイグジットを探す
            for exit_p in signals['exits_profit']:
                if exit_p['idx'] > entry_idx:
                    exit_idx = exit_p['idx']
                    ax1.axvspan(entry_idx, exit_idx, alpha=0.1, color='green')
                    break

            for exit_l in signals['exits_loss']:
                if exit_l['idx'] > entry_idx:
                    exit_idx = exit_l['idx']
                    ax1.axvspan(entry_idx, exit_idx, alpha=0.1, color='red')
                    break

            for exit_t in signals['exits_timeout']:
                if exit_t['idx'] > entry_idx:
                    exit_idx = exit_t['idx']
                    ax1.axvspan(entry_idx, exit_idx, alpha=0.1, color='orange')
                    break

        ax1.set_ylabel('Price (USD)', fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left')

        # ============ RSIチャート ============
        ax2.plot(x, rsi, label='RSI(14)', color='purple', linewidth=2)
        ax2.axhline(y=60, color='red', linestyle='--', linewidth=1, label='Overbought (60)')
        ax2.axhline(y=70, color='orange', linestyle='--', linewidth=1, alpha=0.5, label='Strong Overbought (70)')
        ax2.fill_between(x, 60, 100, alpha=0.1, color='red')
        ax2.set_ylabel('RSI', fontsize=10)
        ax2.set_ylim([0, 100])
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper left')

        # X軸を時刻に設定
        x_labels = [df['datetime'].iloc[i].strftime('%H:%M') if i % 6 == 0 else '' for i in range(len(df))]
        ax1.set_xticks(x)
        ax1.set_xticklabels(x_labels, rotation=45)
        ax2.set_xticks(x)
        ax2.set_xticklabels(x_labels, rotation=45)
        ax2.set_xlabel('Time (Hour)', fontsize=10)

        plt.tight_layout()
        return fig

    def save_and_show(self, fig, filename: str = "strategy_chart.png"):
        """チャートを保存して表示"""
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        logger.info(f"Chart saved: {filename}")
        plt.show()


def main():
    """メイン実行"""
    logger.info("=" * 80)
    logger.info("BTC SHORT STRATEGY - Chart Visualization")
    logger.info("=" * 80)

    # データ読み込み
    df = pd.read_csv('btc_usdt_1h.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)

    logger.info(f"Data loaded: {len(df)} candles")
    logger.info(f"Period: {df['datetime'].min()} to {df['datetime'].max()}\n")

    visualizer = ChartVisualizer()

    # バックテスト実行（直近30日）
    result = visualizer.backtest_with_markers(df, days=30)

    logger.info(f"Backtest Result (30 days):")
    logger.info(f"  Entries: {len(result['signals']['entries'])}")
    logger.info(f"  Profits: {len(result['signals']['exits_profit'])}")
    logger.info(f"  Losses: {len(result['signals']['exits_loss'])}")
    logger.info(f"  Return: {result['return']:+.2%}\n")

    # チャート描画
    fig = visualizer.plot_chart(result, title="BTC SHORT STRATEGY (Last 30 Days)")
    visualizer.save_and_show(fig, filename="short_strategy_chart.png")


if __name__ == '__main__':
    main()
