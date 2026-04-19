#!/usr/bin/env python3
"""Backtest Grid Bot strategy using local data"""
import sys
sys.path.insert(0, r'C:\Users\user\Desktop\cursor\trade')

import numpy as np
import pandas as pd
from config import GRID_CONFIG
from grid_manager import GridManager

# Load 4h data
df = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_4h_1500d.csv', parse_dates=['timestamp'], index_col='timestamp')
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
df = df[~df.index.duplicated(keep='last')].sort_index()

print(f"Data: {len(df)} bars | {df.index[0]} -> {df.index[-1]}")

# Simple grid backtest simulation
class SimpleGridBacktester:
    def __init__(self, config):
        self.gm = GridManager(config)
        self.config = config
        self.maker_fee = config.get('maker_fee', 0.00015)
        
    def run(self, df, initial_capital=100000):
        cash = initial_capital
        grid_positions = []  # (entry_price, quantity, side)
        trades = []
        grid_center = None
        grid_range = None
        
        atr_period = 14
        closes = df['Close'].values
        highs = df['High'].values
        lows = df['Low'].values
        
        # Calculate ATR
        c = pd.Series(closes)
        h = pd.Series(highs)
        l = pd.Series(lows)
        pc = c.shift(1)
        tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        atr_series = tr.ewm(alpha=1/atr_period, min_periods=atr_period).mean()
        
        grid_levels = self.config.get('grid_levels', 5)
        spacing = self.config.get('grid_spacing_pct', 0.05)
        risk_pct = self.config.get('risk_pct_per_level', 0.01)
        
        for i in range(atr_period + 50, len(df)):
            price = closes[i]
            atr = atr_series.iloc[i]
            if np.isnan(atr) or atr <= 0:
                continue
            
            # Check if grid needs recalculation
            if grid_center is None or abs(price - grid_center) / grid_range > 0.2 if grid_range else True:
                # Place new grid orders
                buy_levels = []
                sell_levels = []
                for j in range(1, grid_levels + 1):
                    buy_levels.append(price * (1 - spacing * j))
                    sell_levels.append(price * (1 + spacing * j))
                
                grid_center = price
                grid_range = price * spacing * grid_levels
                
                # Simulate: check if any existing positions hit TP
                new_positions = []
                for pos in grid_positions:
                    entry, qty, side = pos
                    if side == 'buy' and price >= entry * 1.005:  # 0.5% profit
                        pnl = (price - entry) * qty - price * qty * self.maker_fee * 2
                        cash += entry * qty + pnl
                        trades.append({'entry': entry, 'exit': price, 'pnl': pnl, 'side': 'buy'})
                    elif side == 'sell' and price <= entry * 0.995:
                        pnl = (entry - price) * qty - price * qty * self.maker_fee * 2
                        cash += entry * qty + pnl
                        trades.append({'entry': entry, 'exit': price, 'pnl': pnl, 'side': 'sell'})
                    else:
                        new_positions.append(pos)
                grid_positions = new_positions
                
                # Enter new grid positions
                for bl in buy_levels:
                    if bl < price:
                        qty = (cash * risk_pct) / bl
                        if qty * bl <= cash * 0.4:
                            cash -= qty * bl * (1 + self.maker_fee)
                            grid_positions.append((bl, qty, 'buy'))
                
                for sl in sell_levels:
                    if sl > price:
                        qty = (cash * risk_pct) / sl
                        if qty * sl <= cash * 0.4:
                            cash -= qty * sl * (1 + self.maker_fee)
                            grid_positions.append((sl, qty, 'sell'))
        
        # Close remaining positions at last price
        last_price = closes[-1]
        for entry, qty, side in grid_positions:
            if side == 'buy':
                pnl = (last_price - entry) * qty - last_price * qty * self.maker_fee * 2
            else:
                pnl = (entry - last_price) * qty - last_price * qty * self.maker_fee * 2
            cash += entry * qty + pnl
            trades.append({'entry': entry, 'exit': last_price, 'pnl': pnl, 'side': side})
        
        final_value = cash
        total_return = (final_value - initial_capital) / initial_capital * 100
        n_trades = len(trades)
        
        if n_trades > 0:
            wins = [t for t in trades if t['pnl'] > 0]
            losses = [t for t in trades if t['pnl'] <= 0]
            win_rate = len(wins) / n_trades * 100
            gp = sum(t['pnl'] for t in wins)
            gl = abs(sum(t['pnl'] for t in losses))
            pf = gp / gl if gl > 0 else float('inf')
            avg_pnl = np.mean([t['pnl'] for t in trades])
        else:
            win_rate = 0
            pf = 0
            avg_pnl = 0
        
        print(f"\n{'='*60}")
        print(f"  GRID BOT BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"  Initial Capital : ${initial_capital:,.2f}")
        print(f"  Final Value     : ${final_value:,.2f}")
        print(f"  Total Return    : {total_return:+.2f}%")
        print(f"  Trades          : {n_trades}")
        print(f"  Win Rate        : {win_rate:.1f}%")
        print(f"  Profit Factor   : {pf:.2f}")
        print(f"  Avg Trade PnL   : ${avg_pnl:+,.2f}")
        
        if total_return > 0 and pf > 1.0:
            print(f"  >>> POSITIVE EXPECTANCY <<<")
        else:
            print(f"  >>> NEGATIVE/WEAK EXPECTANCY <<<")
        
        return {
            'total_return': total_return,
            'final_value': final_value,
            'trades': n_trades,
            'win_rate': win_rate,
            'profit_factor': pf
        }

config = GRID_CONFIG.copy()
config['grid_levels'] = 5
config['grid_spacing_pct'] = 0.05
config['risk_pct_per_level'] = 0.01

bt = SimpleGridBacktester(config)
result = bt.run(df)
