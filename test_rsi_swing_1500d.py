#!/usr/bin/env python3
"""Run RSI Swing v6 backtest using local 1500d CSV data"""
import sys
sys.path.insert(0, r'C:\Users\user\Desktop\cursor\trade')

import numpy as np
import pandas as pd
from backtesting import Backtest
from rsi_swing_trader_v6 import RSIMomentumSwing

# Load local CSV
df = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_4h_1500d.csv', parse_dates=['timestamp'], index_col='timestamp')
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
df = df[~df.index.duplicated(keep='last')].sort_index()

print(f"Data: {len(df)} bars | {df.index[0]} -> {df.index[-1]}")

bt = Backtest(
    df, RSIMomentumSwing,
    cash=1_000_000,
    commission=0.0005,
    margin=0.05,
    trade_on_close=False,
    exclusive_orders=False,
)

# Baseline
print("\n" + "="*75)
print("  RSI MOMENTUM SWING v6.0 - BASELINE (RSI 14, EMA 50, SL 1.5x, TP 3.0x)")
print("="*75)
stats = bt.run()
for m in ["Start", "End", "Duration", "Equity Final [$]", "Equity Peak [$]",
          "Return [%]", "Max. Drawdown [%]", "# Trades", "Win Rate [%]",
          "Profit Factor", "Sharpe Ratio", "Expectancy [%]", "SQN"]:
    if m in stats.index:
        print(f"  {m:<30s}: {stats[m]}")

nt = stats.get("# Trades", 0)
pf = stats.get("Profit Factor", 0) or 0
wr = stats.get("Win Rate [%]", 0)
r = stats.get("Return [%]", 0)
dd = stats.get("Max. Drawdown [%]", 0)

print(f"\n  Trade count: {nt}")
if nt == 0:
    print("  No trades - EMA filter too strict")
elif pf > 1.5:
    print(f"  STRONG EDGE: PF={pf:.2f} WR={wr:.1f}% Ret={r:+.2f}%")
elif pf > 1.0:
    print(f"  POSITIVE EDGE: PF={pf:.2f} WR={wr:.1f}% Ret={r:+.2f}%")
else:
    print(f"  NO EDGE: PF={pf:.2f} WR={wr:.1f}% Ret={r:+.2f}%")

# Optimized params from previous run
print("\n" + "="*75)
print("  OPTIMIZED (SL 1.5, TP 6.0, RSI 14, EMA OFF)")
print("="*75)
stats2 = bt.run(sl_atr=1.5, tp_atr=6.0, rsi_period=14, use_ema=False)
for m in ["Equity Final [$]", "Return [%]", "Max. Drawdown [%]", "# Trades",
          "Win Rate [%]", "Profit Factor", "Sharpe Ratio", "Expectancy [%]"]:
    if m in stats2.index:
        print(f"  {m:<30s}: {stats2[m]}")
