#!/usr/bin/env python3
"""Backtest for hl_rsi_swing_v6 strategy with HTML chart output."""

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

def ema_ind(series, period):
    return pd.Series(series).ewm(span=period, adjust=False).mean().values

def rsi_ind(series, period=14):
    s = pd.Series(series)
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/period, min_periods=period).mean()
    lo = (-d.clip(upper=0)).ewm(alpha=1/period, min_periods=period).mean()
    return (100 - 100 / (1 + g / lo.replace(0, np.nan))).values

def atr_ind(high, low, close, period=14):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean().values


class RSISwingLive(Strategy):
    rsi_period = 14
    rsi_os = 30.0
    rsi_ob = 70.0
    ema_period = 50
    sl_atr = 1.5
    tp_atr = 3.0
    risk_pct = 0.02
    max_bars = 20

    def init(self):
        c = self.data.Close
        h, l = self.data.High, self.data.Low
        self.rsi = self.I(rsi_ind, c, self.rsi_period)
        self.ema50 = self.I(ema_ind, c, self.ema_period)
        self.atr = self.I(atr_ind, h, l, c, 14)
        self._entry_bar = 0

    def next(self):
        if self.position:
            if len(self.data) - self._entry_bar >= self.max_bars:
                self.position.close()
            return

        if len(self.data.Close) < max(self.rsi_period, self.ema_period) + 3:
            return

        rsi_now = float(self.rsi[-1])
        rsi_prev = float(self.rsi[-2])
        c_now = float(self.data.Close[-1])
        ema_now = float(self.ema50[-1])
        atr_now = float(self.atr[-1])

        if any(np.isnan(x) for x in [rsi_now, rsi_prev, c_now, ema_now, atr_now]):
            return
        if atr_now <= 0:
            return

        long_rsi = (rsi_prev <= self.rsi_os) and (rsi_now > self.rsi_os)
        long_ema = c_now > ema_now

        if long_rsi and long_ema:
            sl_d = atr_now * self.sl_atr
            tp_d = atr_now * self.tp_atr
            eq = float(self.equity)
            if eq <= 0:
                return
            sz = max(int(round(eq * self.risk_pct / sl_d)), 1)
            mx = int(eq * 0.95 / c_now)
            sz = min(sz, max(mx, 1))
            self.buy(size=sz, sl=c_now - sl_d, tp=c_now + tp_d)
            self._entry_bar = len(self.data)

        short_rsi = (rsi_prev >= self.rsi_ob) and (rsi_now < self.rsi_ob)
        short_ema = c_now < ema_now

        if short_rsi and short_ema:
            sl_d = atr_now * self.sl_atr
            tp_d = atr_now * self.tp_atr
            eq = float(self.equity)
            if eq <= 0:
                return
            sz = max(int(round(eq * self.risk_pct / sl_d)), 1)
            mx = int(eq * 0.95 / c_now)
            sz = min(sz, max(mx, 1))
            self.sell(size=sz, sl=c_now + sl_d, tp=c_now - tp_d)
            self._entry_bar = len(self.data)


def load_data():
    try:
        import yfinance as yf
        print("Fetching BTC-USD 1h data...")
        df = yf.download("BTC-USD", period="730d", interval="1h",
                         progress=False, auto_adjust=False, group_by="column")
        if df.empty:
            raise RuntimeError("Empty")
        cols = ["Open", "High", "Low", "Close", "Volume"]
        df = df.iloc[:, :len(cols)]
        df.columns = cols[:df.shape[1]]
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        print(f"OK: {len(df)} bars (1h)")
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        print(f"yfinance failed ({e}), generating synthetic data")
        return _synth()


def _synth(days=365):
    np.random.seed(42)
    n = days * 24
    ts = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    base = 65000.0
    cl = np.zeros(n)
    cl[0] = base
    for i in range(1, n):
        ret = np.random.randn() * 0.006
        if np.random.random() < 0.02:
            ret += np.random.choice([-1, 1]) * np.random.uniform(0.02, 0.05)
        cl[i] = cl[i-1] * (1 + ret)
    op = np.roll(cl, 1)
    op[0] = cl[0]
    intr = np.abs(np.random.randn(n)) * 0.003
    hi = np.maximum(op, cl) * (1 + intr)
    lo = np.minimum(op, cl) * (1 - intr)
    vol = np.random.lognormal(10, 0.5, n)
    print(f"Synthetic: {n} bars ({days} days)")
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": cl, "Volume": vol}, index=ts)


if __name__ == "__main__":
    import os
    data = load_data()

    bt = Backtest(data, RSISwingLive,
                  cash=10_000, commission=0.0005, margin=0.05,
                  trade_on_close=False, exclusive_orders=False)

    stats = bt.run()

    print("\n" + "=" * 60)
    print("  BACKTEST RESULTS - RSI SWING v6 (SL=1.5xATR, TP=3.0xATR)")
    print("=" * 60)
    for m in ["# Trades", "Win Rate [%]", "Profit Factor",
              "Return [%]", "Max. Drawdown [%]", "Sharpe Ratio",
              "Avg. Trade [%]", "Best Trade [%]", "Worst Trade [%]"]:
        if m in stats.index:
            print(f"  {m:<25s}: {stats[m]}")

    out_html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_chart.html")
    bt.plot(open_browser=False, filename=out_html)
    print(f"\nChart saved: {out_html}")
    print("Open in Chrome to view.")
