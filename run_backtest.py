#!/usr/bin/env python3
"""Backtest runner"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from hl_trader_v6 import HyperliquidBacktester, load_config

config = load_config()
backtester = HyperliquidBacktester(config)
metrics = backtester.run_backtest(days=180)

print("\n" + "="*70)
print(" BACKTEST RESULTS (180 days)")
print("="*70)
if "error" in metrics:
    print(f"Error: {metrics['error']}")
else:
    print(f"Total Trades: {metrics['total_trades']}")
    print(f"Win Rate: {metrics['win_rate']:.2f}%")
    print(f"Profit/Loss: ${metrics['profit_loss']:.2f} ({metrics['profit_loss_pct']:.2f}%)")
    print(f"Max Drawdown: {metrics['max_drawdown']:.2f}%")
    print(f"Final Balance: ${metrics['final_balance']:.2f}")
print("="*70)
