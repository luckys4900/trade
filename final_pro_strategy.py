"""
=============================================================================
 BTC/USDT Professional Volatility Breakout Strategy
 ---------------------------------------------------
 Framework : backtrader
 Timeframe : 1H
 Market    : BTC/USDT (Binance Real Data)

 Core Logic:
   1. Market Regime Filter  – ADX(14)>20 & EMA50>EMA200
   2. Volatility Squeeze    – BB Width < rolling mean → Breakout above +2σ
   3. Volume Confirmation   – Volume > SMA(Volume,20)
   4. ATR-based Position Sizing (2% risk per trade)
   5. Split Exit: 50% at +2ATR (move stop to BE), trail rest via EMA20/SuperTrend
=============================================================================
"""

import os
import datetime as dt
import warnings

import numpy as np
import pandas as pd
import backtrader as bt
import backtrader.analyzers as btanalyzers

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────
# 1. CUSTOM INDICATORS
# ──────────────────────────────────────────────────────────────────────

class BollingerBandWidth(bt.Indicator):
    """Bollinger Band Width = (Upper - Lower) / Middle"""
    lines = ("bbwidth",)
    params = (("period", 20), ("devfactor", 2.0),)

    def __init__(self):
        bb = bt.indicators.BollingerBands(
            self.data, period=self.p.period, devfactor=self.p.devfactor
        )
        self.lines.bbwidth = (bb.top - bb.bot) / bb.mid


class SuperTrend(bt.Indicator):
    """SuperTrend indicator for trailing stop reference."""
    lines = ("supertrend", "direction")
    params = (("period", 10), ("multiplier", 3.0),)

    def __init__(self):
        self.atr = bt.indicators.ATR(period=self.p.period)

    def next(self):
        hl2 = (self.data.high[0] + self.data.low[0]) / 2.0
        up = hl2 - self.p.multiplier * self.atr[0]
        dn = hl2 + self.p.multiplier * self.atr[0]

        if len(self) < 2:
            self.lines.supertrend[0] = up
            self.lines.direction[0] = 1
            return

        prev_st = self.lines.supertrend[-1]
        prev_dir = self.lines.direction[-1]

        if prev_dir == 1:
            up = max(up, prev_st)
            if self.data.close[0] < up:
                self.lines.supertrend[0] = dn
                self.lines.direction[0] = -1
            else:
                self.lines.supertrend[0] = up
                self.lines.direction[0] = 1
        else:
            dn = min(dn, prev_st)
            if self.data.close[0] > dn:
                self.lines.supertrend[0] = up
                self.lines.direction[0] = 1
            else:
                self.lines.supertrend[0] = dn
                self.lines.direction[0] = -1


# ──────────────────────────────────────────────────────────────────────
# 2. STRATEGY
# ──────────────────────────────────────────────────────────────────────

class VolatilityBreakoutStrategy(bt.Strategy):
    """
    Professional BTC Volatility Breakout with:
      - Market Regime Filter (ADX + EMA cross)
      - Bollinger Squeeze → Breakout entry
      - Volume confirmation
      - ATR-based position sizing (risk parity)
      - Split exit: 50% at +2ATR, trail remainder via EMA20 / SuperTrend
    """

    params = dict(
        # Regime Filter
        adx_period=14,
        adx_threshold=20,
        ema_fast=50,
        ema_slow=200,
        # Bollinger / Squeeze
        bb_period=20,
        bb_dev=2.0,
        squeeze_lookback=120,
        # Volume
        vol_sma_period=20,
        # ATR / Risk
        atr_period=14,
        risk_pct=0.02,          # 2% of account per trade
        atr_sl_mult=2.0,        # Initial stop = 2 ATR
        atr_tp1_mult=2.0,       # TP1 = 2 ATR  (50% off)
        # Trailing
        ema_trail=20,
        supertrend_period=10,
        supertrend_mult=3.0,
        # Misc
        printlog=False,
    )

    def __init__(self):
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.p.ema_slow)
        self.adx = bt.indicators.ADX(self.data, period=self.p.adx_period)
        self.bb = bt.indicators.BollingerBands(
            self.data.close, period=self.p.bb_period, devfactor=self.p.bb_dev
        )
        self.bbw = BollingerBandWidth(
            self.data.close, period=self.p.bb_period, devfactor=self.p.bb_dev
        )
        self.bbw_sma = bt.indicators.SMA(self.bbw.bbwidth, period=self.p.squeeze_lookback)
        self.vol_sma = bt.indicators.SMA(self.data.volume, period=self.p.vol_sma_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.ema_trail_line = bt.indicators.EMA(self.data.close, period=self.p.ema_trail)
        self.supertrend = SuperTrend(
            self.data, period=self.p.supertrend_period, multiplier=self.p.supertrend_mult
        )

        self.entry_price = None
        self.initial_size = None
        self.tp1_hit = False
        self.stop_price = None
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.initial_size = order.executed.size
                self.tp1_hit = False
                self.stop_price = self.entry_price - self.p.atr_sl_mult * self.atr[0]
                if self.p.printlog:
                    print(f"  BUY  @ {order.executed.price:.2f}  size={order.executed.size:.6f}")
                    print(f"  Stop: {self.stop_price:.2f}")
            elif order.issell():
                if self.p.printlog:
                    print(f"  SELL @ {order.executed.price:.2f}  size={order.executed.size:.6f}")
        self.order = None

    def next(self):
        if self.order:
            return

        pos = self.getposition(self.data)

        # No Position → Check for Entry
        if not pos.size:
            self.entry_price = None
            self.tp1_hit = False
            self.stop_price = None

            if self.ema_fast[0] <= self.ema_slow[0]:
                return
            if self.adx[0] <= self.p.adx_threshold:
                return

            if self.bbw.bbwidth[0] >= self.bbw_sma[0]:
                return

            if self.data.close[0] <= self.bb.top[0]:
                return

            if self.data.volume[0] <= self.vol_sma[0]:
                return

            account_value = self.broker.getvalue()
            risk_amount = account_value * self.p.risk_pct
            atr_val = self.atr[0]
            if atr_val <= 0:
                return
            sl_distance = self.p.atr_sl_mult * atr_val
            size = risk_amount / sl_distance

            max_size = (self.broker.getcash() * 0.95) / self.data.close[0]
            size = min(size, max_size)
            if size <= 0:
                return

            self.order = self.buy(size=size)

        # In Position → Manage Exits
        else:
            if self.entry_price is None:
                return

            current_size = pos.size
            close = self.data.close[0]

            # Initial Stop Loss
            if self.stop_price and close <= self.stop_price:
                self.order = self.sell(size=current_size)
                return

            # TP1: +2 ATR → close 50%, move stop to BE
            tp1_level = self.entry_price + self.p.atr_tp1_mult * self.atr[0]
            if not self.tp1_hit and close >= tp1_level:
                sell_size = round(current_size * 0.5, 8)
                if sell_size > 0:
                    self.order = self.sell(size=sell_size)
                    self.tp1_hit = True
                    self.stop_price = self.entry_price
                    if self.p.printlog:
                        print(f"  [TP1] Hit at {close:.2f}, closed 50% ({sell_size:.6f})")
                        print(f"  Stop moved to BE: {self.stop_price:.2f}")
                return

            # Trailing Exit for remainder
            if self.tp1_hit:
                trail_level = max(
                    self.ema_trail_line[0],
                    self.supertrend.supertrend[0] if self.supertrend.direction[0] == 1 else -1e18,
                )
                self.stop_price = max(self.stop_price, trail_level)

                if close <= self.stop_price:
                    self.order = self.sell(size=current_size)
                    if self.p.printlog:
                        print(f"  [TRAIL] Hit at {close:.2f}, closed remainder ({current_size:.6f})")
                    return


# ──────────────────────────────────────────────────────────────────────
# 3. CUSTOM ANALYZERS
# ──────────────────────────────────────────────────────────────────────

class WinRateAnalyzer(bt.Analyzer):
    """Calculate win rate from closed trades."""

    def __init__(self):
        self.trades = []

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trades.append(trade.pnlcomm)

    def get_analysis(self):
        total = len(self.trades)
        if total == 0:
            return {"total": 0, "won": 0, "lost": 0, "winrate": 0.0}
        won = sum(1 for t in self.trades if t > 0)
        return {
            "total": total,
            "won": won,
            "lost": total - won,
            "winrate": won / total * 100,
        }


# ──────────────────────────────────────────────────────────────────────
# 4. MAIN
# ──────────────────────────────────────────────────────────────────────

def main():
    DATA_CSV = "btc_usdt_1h.csv"
    LOOKBACK_DAYS = 180

    # Fetch data from Binance
    print("=" * 70)
    print(" BTC/USDT Volatility Breakout Strategy - Backtest")
    print("=" * 70)
    print("[DATA] Fetching BTC/USDT 1H data from Binance...")

    # Check if CSV exists and is recent
    if os.path.exists(DATA_CSV):
        age_hours = (dt.datetime.now().timestamp() - os.path.getmtime(DATA_CSV)) / 3600
        if age_hours < 12:
            print(f"[INFO] Using cached CSV: {DATA_CSV} (age={age_hours:.1f}h)")
            df = pd.read_csv(DATA_CSV, parse_dates=['datetime'], index_col='datetime')
            df = df.sort_index()
        else:
            print("[INFO] CSV too old, fetching fresh data...")
            import ccxt
            exchange = ccxt.binance({"enableRateLimit": True})
            since = exchange.parse8601(
                (dt.datetime.utcnow() - dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            )

            all_ohlcv = []
            while True:
                ohlcv = exchange.fetch_ohlcv("BTC/USDT", "1h", since=since, limit=1000)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                since = ohlcv[-1][0] + 1
                if len(ohlcv) < 1000:
                    break

            df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("datetime", inplace=True)
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            df.to_csv(DATA_CSV)
            print(f"[INFO] Saved {len(df)} bars → {DATA_CSV}")
    else:
        # Fetch from Binance
        import ccxt
        exchange = ccxt.binance({"enableRateLimit": True})
        since = exchange.parse8601(
            (dt.datetime.utcnow() - dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        all_ohlcv = []
        while True:
            ohlcv = exchange.fetch_ohlcv("BTC/USDT", "1h", since=since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            if len(ohlcv) < 1000:
                break

        df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        df.to_csv(DATA_CSV)
        print(f"[INFO] Saved {len(df)} bars → {DATA_CSV}")

    print(f"[DATA] Loaded {len(df)} candles")
    print(f"[DATA] Price range: ${df['close'].min():,.2f} - ${df['close'].max():,.2f}")
    print(f"[DATA] Volume range: {df['volume'].min():.1f} - {df['volume'].max():.1f}")
    print(f"[DATA] Data range: {df.index[0]} → {df.index[-1]}")

    # Create Feed
    data = bt.feeds.PandasData(
        dataname=df,
        open='open',
        high='high',
        low='low',
        close='close',
        volume='volume',
        openinterest=-1,
    )

    # Cerebro Setup
    cerebro = bt.Cerebro()
    cerebro.adddata(data)
    cerebro.addstrategy(VolatilityBreakoutStrategy, printlog=True)

    # Broker config
    initial_cash = 100_000.0
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.001)

    # Analyzers
    cerebro.addanalyzer(btanalyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days, compression=1, riskfreerate=0.045, annualize=True)
    cerebro.addanalyzer(btanalyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(btanalyzers.Returns, _name='returns')
    cerebro.addanalyzer(WinRateAnalyzer, _name='winrate')

    print(f"\n[BACKTEST] Initial Cash: ${initial_cash:,.0f}")
    print(f"[BACKTEST] Total Bars: {len(df)}")
    print(f"[BACKTEST] Commission: 0.1% per trade")
    print("-" * 70)

    # Run
    results = cerebro.run()
    strat = results[0]

    # Extract Results
    final_value = cerebro.broker.getvalue()
    total_return = (final_value - initial_cash) / initial_cash * 100

    sharpe_dict = strat.analyzers.sharpe.get_analysis()
    sharpe = sharpe_dict.get('sharperatio', None)
    sharpe_str = f"{sharpe:.4f}" if sharpe else "N/A"

    dd = strat.analyzers.drawdown.get_analysis()
    max_dd = dd.max.drawdown

    wr = strat.analyzers.winrate.get_analysis()

    # Report
    print("\n" + "=" * 70)
    print(" PERFORMANCE REPORT")
    print("=" * 70)
    print(f"  Final Portfolio Value : ${final_value:,.2f}")
    print(f"  Total Return          : {total_return:+.2f}%")
    print(f"  Max Drawdown          : {max_dd:.2f}%")
    print(f"  Sharpe Ratio (annualized) : {sharpe_str}")
    print(f"  Total Trades          : {wr['total']}")
    print(f"  Won / Lost            : {wr['won']} / {wr['lost']}")
    print(f"  Win Rate              : {wr['winrate']:.1f}%")
    print("=" * 70)

    print(f"\n[ANALYSIS] Profit per trade: ${final_value - initial_cash:.2f}")
    print(f"[ANALYSIS] Profit factor: {final_value / initial_cash:.2f}x")

    # GO SIGN CHECK
    print("\n" + "=" * 70)
    print(" GO SIGN CHECK")
    print("=" * 70)
    go_sign = ""
    if total_return > 0 and max_dd < 10:
        go_sign = "✅ GO (実運用開始可能)"
    else:
        go_sign = "❌ STOP (改善が必要)"
    print(f"  {go_sign}")
    print(f"  Total Return: {total_return:+.2f}%")
    print(f"  Max Drawdown: {max_dd:.2f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
