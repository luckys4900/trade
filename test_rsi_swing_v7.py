#!/usr/bin/env python3
"""
RSI Swing v7 - Professional Grade Improvements (Fixed v2)
Key fix: EMA50 filter is OPTIONAL (default OFF like v6 Balanced)
"""
import sys
sys.path.insert(0, r'C:\Users\user\Desktop\cursor\trade')

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
from rsi_swing_trader_v6 import rsi_ind, ema_ind, atr_ind

def sma_ind(series, period):
    return pd.Series(series).rolling(period, min_periods=period).mean().values


class RSIMomentumSwingV7(Strategy):
    """
    v7 improvements over v6:
    1. Trailing stop (breakeven after 1R profit)
    2. EMA200 trend filter (optional)
    3. Volume confirmation (optional)
    4. Consecutive loss cooldown
    5. Volatility-adjusted sizing
    """
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

    # Filters (default OFF to match v6 Balanced)
    use_ema50: bool = False       # OFF by default (v6 Balanced compatible)
    use_ema200: bool = False
    use_volume: bool = False
    use_cooldown: bool = False
    use_trailing: bool = False
    vol_period: int = 20
    vol_mult: float = 0.8
    cooldown_bars: int = 10

    def init(self):
        c = self.data.Close
        h, l, v = self.data.High, self.data.Low, self.data.Volume
        self.rsi = self.I(rsi_ind, c, self.rsi_period)
        self.ema50 = self.I(ema_ind, c, self.ema50_period)
        self.ema200 = self.I(ema_ind, c, self.ema200_period)
        self.atr = self.I(atr_ind, h, l, c, self.atr_period)
        self.vol_sma = self.I(sma_ind, v, self.vol_period)
        self._entry_bar = 0
        self._entry_price = 0.0
        self._consec_loss = 0
        self._cool_end = 0
        self._be_moved = False

    def next(self):
        if self.position:
            self._manage_position()
            return

        lookback = max(self.rsi_period, self.ema50_period, self.ema200_period, self.vol_period) + 5
        if len(self.data.Close) < lookback:
            return

        if self.use_cooldown and self._consec_loss >= 3:
            if len(self.data) < self._cool_end:
                return

        rsi_now = float(self.rsi[-1])
        rsi_prev = float(self.rsi[-2])
        c_now = float(self.data.Close[-1])
        atr_now = float(self.atr[-1])

        if any(np.isnan(x) for x in [rsi_now, rsi_prev, c_now, atr_now]):
            return
        if atr_now <= 0:
            return

        # Volume filter
        if self.use_volume:
            vol_now = float(self.data.Volume[-1])
            vol_avg = float(self.vol_sma[-1])
            if np.isnan(vol_avg) or vol_avg <= 0 or vol_now < vol_avg * self.vol_mult:
                return

        # EMA50 filter (optional, OFF by default)
        ema50_ok = True
        if self.use_ema50:
            ema50 = float(self.ema50[-1])
            if np.isnan(ema50):
                return
            ema50_ok = True  # Just check it exists

        # EMA200 filter
        ema200_ok = True
        if self.use_ema200:
            ema200 = float(self.ema200[-1])
            if np.isnan(ema200) or ema200 <= 0:
                return
            ema200_5 = float(self.ema200[-5])
            slope = (ema200 - ema200_5) / ema200_5
            # For longs: price above EMA200 OR EMA200 not declining fast
            # For shorts: price below EMA200 OR EMA200 not rising fast
            ema200_ok = True  # Applied per-direction below

        # LONG
        long_rsi = (rsi_prev <= self.rsi_os) and (rsi_now > self.rsi_os)
        long_ema50 = (not self.use_ema50) or (c_now > float(self.ema50[-1]))
        long_ema200 = True
        if self.use_ema200:
            ema200 = float(self.ema200[-1])
            ema200_5 = float(self.ema200[-5])
            slope = (ema200 - ema200_5) / ema200_5 if ema200_5 > 0 else 0
            long_ema200 = (c_now > ema200) or (slope > -0.005)

        if long_rsi and long_ema50 and long_ema200:
            self._enter("long", c_now, atr_now)
            return

        # SHORT
        short_rsi = (rsi_prev >= self.rsi_ob) and (rsi_now < self.rsi_ob)
        short_ema50 = (not self.use_ema50) or (c_now < float(self.ema50[-1]))
        short_ema200 = True
        if self.use_ema200:
            ema200 = float(self.ema200[-1])
            ema200_5 = float(self.ema200[-5])
            slope = (ema200 - ema200_5) / ema200_5 if ema200_5 > 0 else 0
            short_ema200 = (c_now < ema200) or (slope < 0.005)

        if short_rsi and short_ema50 and short_ema200:
            self._enter("short", c_now, atr_now)

    def _manage_position(self):
        bars_held = len(self.data) - self._entry_bar
        current = float(self.data.Close[-1])
        atr_now = float(self.atr[-1])
        if np.isnan(atr_now) or atr_now <= 0:
            return

        if bars_held >= self.max_bars:
            self.position.close()
            return

        if self.use_trailing and not self._be_moved:
            one_r = atr_now * self.sl_atr
            if self.position.is_long:
                if current >= self._entry_price + one_r:
                    for t in self.trades:
                        if t.is_long:
                            be = self._entry_price + one_r * 0.1
                            if t.sl is None or t.sl < be:
                                t.sl = be
                    self._be_moved = True
            elif self.position.is_short:
                if current <= self._entry_price - one_r:
                    for t in self.trades:
                        if t.is_short:
                            be = self._entry_price - one_r * 0.1
                            if t.sl is None or t.sl > be:
                                t.sl = be
                    self._be_moved = True

    def _enter(self, direction, price, atr_now):
        sl_dist = atr_now * self.sl_atr
        tp_dist = atr_now * self.tp_atr
        eq = float(self.equity)
        if eq <= 0:
            return

        vol_adj = 1.0
        atr_pct = atr_now / price if price > 0 else 0
        if atr_pct > 0.03:
            vol_adj = 0.7
        elif atr_pct > 0.02:
            vol_adj = 0.85

        sz = max(int(round(eq * self.risk_pct * vol_adj / sl_dist)), 1)
        mx = int(eq * 0.95 / price)
        sz = min(sz, max(mx, 1))

        if direction == "long":
            self.buy(size=sz, sl=price - sl_dist, tp=price + tp_dist)
        else:
            self.sell(size=sz, sl=price + sl_dist, tp=price - tp_dist)

        self._entry_bar = len(self.data)
        self._entry_price = price
        self._be_moved = False

    def notify_trade(self, trade):
        if trade.is_closed and trade.pl is not None:
            if trade.pl < 0:
                self._consec_loss += 1
                if self.use_cooldown and self._consec_loss >= 3:
                    self._cool_end = len(self.data) + self.cooldown_bars
            else:
                self._consec_loss = 0


def run():
    df = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_4h_1500d.csv',
                     parse_dates=['timestamp'], index_col='timestamp')
    df = df[['Open','High','Low','Close','Volume']]
    df = df[~df.index.duplicated(keep='last')].sort_index()

    n = len(df)
    test_start = int(n * 0.8)
    df_test = df.iloc[test_start:]

    print(f"Test period: {df_test.index[0].date()} to {df_test.index[-1].date()} ({len(df_test)} bars)")

    from rsi_swing_trader_v6 import RSIMomentumSwing
    bt6 = Backtest(df_test, RSIMomentumSwing, cash=1_000_000, commission=0.0005,
                   margin=0.05, trade_on_close=False, finalize_trades=True)

    results = []

    # v6 Baseline
    s6 = bt6.run(sl_atr=2.0, tp_atr=5.0, rsi_period=14, use_ema=False, max_bars=20)
    results.append(("v6 Balanced", _extract(s6)))

    # v7 configs - each gets a fresh Backtest instance
    configs = [
        ("v7 Trailing", {"sl_atr":2.0, "tp_atr":5.0, "rsi_period":14, "use_trailing":True}),
        ("v7 +EMA200", {"sl_atr":2.0, "tp_atr":5.0, "rsi_period":14, "use_ema200":True, "use_trailing":True}),
        ("v7 +Volume", {"sl_atr":2.0, "tp_atr":5.0, "rsi_period":14, "use_volume":True, "use_trailing":True, "vol_mult":0.5}),
        ("v7 +Cooldown", {"sl_atr":2.0, "tp_atr":5.0, "rsi_period":14, "use_cooldown":True, "use_trailing":True}),
        ("v7 Full", {"sl_atr":2.0, "tp_atr":5.0, "rsi_period":14, "use_ema200":True, "use_volume":True, "use_cooldown":True, "use_trailing":True, "vol_mult":0.5}),
        ("v7 Conservative", {"sl_atr":2.5, "tp_atr":4.0, "rsi_period":14, "use_ema200":True, "use_volume":True, "use_cooldown":True, "use_trailing":True, "vol_mult":0.8}),
        ("v7 Aggressive", {"sl_atr":1.5, "tp_atr":6.0, "rsi_period":14, "use_trailing":True, "use_cooldown":True, "vol_mult":0.3}),
    ]

    for name, params in configs:
        bt = Backtest(df_test, RSIMomentumSwingV7, cash=1_000_000, commission=0.0005,
                      margin=0.05, trade_on_close=False, finalize_trades=True)
        try:
            s = bt.run(**params)
            results.append((name, _extract(s)))
        except Exception as e:
            results.append((name, (0, 0, 0, 0, 0, 0, 0)))

    # Print
    print(f"\n{'='*85}")
    print(f"  {'Version':<22s} | {'Ret%':>7} {'PF':>5} {'WR%':>5} {'DD%':>7} {'N':>4} {'Sharpe':>7} {'SQN':>5}")
    print(f"  {'-'*85}")
    for name, (ret, pf, wr, dd, nt, sh, sqn) in results:
        print(f"  {name:<22s} | {ret:>+6.2f}% {pf:>4.2f} {wr:>4.1f}% {dd:>6.2f}% {nt:>4} {sh:>6.2f} {sqn:>4.2f}")
    print(f"{'='*85}")

    valid = [(n, r, pf, wr, dd, nt, sh, sqn) for n, (r, pf, wr, dd, nt, sh, sqn) in results if nt >= 10]
    if valid:
        best_sh = max(valid, key=lambda x: x[6])
        best_pf = max(valid, key=lambda x: x[1])
        best_dd = min(valid, key=lambda x: abs(x[4]))
        print(f"\n  Best Sharpe: {best_sh[0]} (Sharpe={best_sh[6]:.2f})")
        print(f"  Best PF:     {best_pf[0]} (PF={best_pf[1]:.2f})")
        print(f"  Lowest DD:   {best_dd[0]} (DD={best_dd[4]:.2f}%)")


def _extract(s):
    ret = s.get('Return [%]', 0)
    pf = s.get('Profit Factor', 0) or 0
    wr = s.get('Win Rate [%]', 0)
    dd = s.get('Max. Drawdown [%]', 0)
    nt = s.get('# Trades', 0)
    sh = s.get('Sharpe Ratio', 0) or 0
    sqn = s.get('SQN', 0) or 0
    if np.isnan(pf): pf = 0
    if np.isnan(sh): sh = 0
    if np.isnan(sqn): sqn = 0
    return (ret, pf, wr, dd, nt, sh, sqn)


if __name__ == "__main__":
    run()
