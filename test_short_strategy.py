#!/usr/bin/env python3
"""Backtest Short Strategy using local 1h CSV data"""
import sys
sys.path.insert(0, r'C:\Users\user\Desktop\cursor\trade')

import pandas as pd
from short_strategy import ShortTradingStrategy

# Try to load 1h data
try:
    df = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_1h.csv')
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)
    print(f"Loaded 1h data: {len(df)} bars | {df['datetime'].min()} -> {df['datetime'].max()}")
except FileNotFoundError:
    print("btc_usdt_1h.csv not found, trying to generate from 4h data...")
    df_4h = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_4h_1500d.csv', parse_dates=['timestamp'])
    df_4h = df_4h.rename(columns={'timestamp': 'datetime'})
    df = df_4h[['datetime', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
    print(f"Using 4h data as proxy: {len(df)} bars")

strategy = ShortTradingStrategy()

# Test multiple periods
results_list = []
for days in [90, 180, 365, 730]:
    result = strategy.backtest(df, days=days)
    print(f"\n{'='*60}")
    print(f"  SHORT STRATEGY - {days} days")
    print(f"{'='*60}")
    print(f"  Trades     : {result['num_trades']}")
    print(f"  Win Rate   : {result['win_rate']:.1f}%")
    print(f"  Return     : {result['total_return']:+.2%}")
    print(f"  Avg PnL    : {result['avg_pnl_pct']:+.3f}%")
    print(f"  Max DD     : {result['max_drawdown']*100:.2f}%")
    
    if result['num_trades'] > 0:
        pf = sum(t['net_pnl'] for t in result['trades'] if t['net_pnl'] > 0) / abs(sum(t['net_pnl'] for t in result['trades'] if t['net_pnl'] <= 0)) if any(t['net_pnl'] <= 0 for t in result['trades']) else float('inf')
        print(f"  Profit Fct : {pf:.2f}")
        if result['total_return'] > 0:
            print(f"  >>> POSITIVE EXPECTANCY <<<")
        else:
            print(f"  >>> NEGATIVE EXPECTANCY <<<")
    else:
        print(f"  No trades")
    
    results_list.append((days, result))

print(f"\n{'='*60}")
print(f"  SHORT STRATEGY SUMMARY")
print(f"{'='*60}")
profitable = sum(1 for _, r in results_list if r['is_profitable'])
print(f"  Profitable periods: {profitable}/{len(results_list)}")
for days, r in results_list:
    status = "PASS" if r['is_profitable'] else "FAIL"
    print(f"  {status} {days:4d}d: {r['total_return']:+.2%} ({r['num_trades']} trades, WR {r['win_rate']:.1f}%)")
