import sys
sys.path.insert(0, r'C:\Users\user\Desktop\cursor\trade')
import numpy as np
import pandas as pd
from backtesting import Backtest
from test_rsi_swing_v7 import RSIMomentumSwingV7

df = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_4h_1500d.csv', parse_dates=['timestamp'], index_col='timestamp')
df = df[['Open','High','Low','Close','Volume']]
df = df[~df.index.duplicated(keep='last')].sort_index()
n = len(df)
df_test = df.iloc[int(n*0.8):]

print(f"Test bars: {len(df_test)}")

# Test with minimal params (same as v6 baseline)
bt = Backtest(df_test, RSIMomentumSwingV7, cash=1_000_000, commission=0.0005, margin=0.05, trade_on_close=False, finalize_trades=True)
s = bt.run(sl_atr=2.0, tp_atr=5.0, rsi_period=14, use_trailing=False, use_ema200=False, use_volume=False, use_cooldown=False)
print(f"v7 baseline (all filters OFF): Trades={s.get('# Trades', 0)}, Return={s.get('Return [%]', 0):+.2f}%")

# Now test with trailing only
bt2 = Backtest(df_test, RSIMomentumSwingV7, cash=1_000_000, commission=0.0005, margin=0.05, trade_on_close=False, finalize_trades=True)
s2 = bt2.run(sl_atr=2.0, tp_atr=5.0, rsi_period=14, use_trailing=True, use_ema200=False, use_volume=False, use_cooldown=False)
print(f"v7 +trailing: Trades={s2.get('# Trades', 0)}, Return={s2.get('Return [%]', 0):+.2f}%")
