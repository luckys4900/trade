import sys
sys.path.insert(0, r'C:\Users\user\Desktop\cursor\trade')
import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
from rsi_swing_trader_v6 import rsi_ind, ema_ind, atr_ind

def sma_ind(series, period):
    return pd.Series(series).rolling(period, min_periods=period).mean().values

class DebugV7(Strategy):
    rsi_period: int = 14
    rsi_os: float = 30.0
    rsi_ob: float = 70.0
    ema50_period: int = 50
    ema200_period: int = 200
    atr_period: int = 14
    sl_atr: float = 2.0
    tp_atr: float = 5.0
    max_bars: int = 20
    risk_pct: float = 0.015

    def init(self):
        c = self.data.Close
        h, l, v = self.data.High, self.data.Low, self.data.Volume
        self.rsi = self.I(rsi_ind, c, self.rsi_period)
        self.ema50 = self.I(ema_ind, c, self.ema50_period)
        self.ema200 = self.I(ema_ind, c, self.ema200_period)
        self.atr = self.I(atr_ind, h, l, c, self.atr_period)
        self._entry_bar = 0
        self._debug_count = 0

    def next(self):
        if self.position:
            return

        lookback = max(self.rsi_period, self.ema50_period, self.ema200_period) + 5
        if len(self.data.Close) < lookback:
            return

        rsi_now = float(self.rsi[-1])
        rsi_prev = float(self.rsi[-2])
        c_now = float(self.data.Close[-1])
        ema50 = float(self.ema50[-1])
        atr_now = float(self.atr[-1])

        if any(np.isnan(x) for x in [rsi_now, rsi_prev, c_now, ema50, atr_now]):
            return
        if atr_now <= 0:
            return

        # Check entry conditions
        long_rsi = (rsi_prev <= self.rsi_os) and (rsi_now > self.rsi_os)
        long_ema = c_now > ema50
        short_rsi = (rsi_prev >= self.rsi_ob) and (rsi_now < self.rsi_ob)
        short_ema = c_now < ema50

        if long_rsi or short_rsi:
            self._debug_count += 1
            if self._debug_count <= 5:
                print(f"  DEBUG bar {len(self.data)}: RSI={rsi_now:.1f}(prev={rsi_prev:.1f}), C={c_now:.0f}, EMA50={ema50:.0f}")
                print(f"    long_rsi={long_rsi}, long_ema={long_ema}, short_rsi={short_rsi}, short_ema={short_ema}")

        if long_rsi and long_ema:
            self._enter("long", c_now, atr_now)
            return
        if short_rsi and short_ema:
            self._enter("short", c_now, atr_now)

    def _enter(self, direction, price, atr_now):
        sl_dist = atr_now * self.sl_atr
        tp_dist = atr_now * self.tp_atr
        eq = float(self.equity)
        if eq <= 0:
            return
        sz = max(int(round(eq * self.risk_pct / sl_dist)), 1)
        mx = int(eq * 0.95 / price)
        sz = min(sz, max(mx, 1))
        if direction == "long":
            self.buy(size=sz, sl=price - sl_dist, tp=price + tp_dist)
        else:
            self.sell(size=sz, sl=price + sl_dist, tp=price - tp_dist)
        self._entry_bar = len(self.data)


df = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_4h_1500d.csv', parse_dates=['timestamp'], index_col='timestamp')
df = df[['Open','High','Low','Close','Volume']]
df = df[~df.index.duplicated(keep='last')].sort_index()
n = len(df)
df_test = df.iloc[int(n*0.8):]

print(f"Test bars: {len(df_test)}")
bt = Backtest(df_test, DebugV7, cash=1_000_000, commission=0.0005, margin=0.05, trade_on_close=False, finalize_trades=True)
s = bt.run()
print(f"\nTrades: {s.get('# Trades', 0)}")
print(f"Return: {s.get('Return [%]', 0):+.2f}%")
