# best_btc_strategy.py
# pip install backtrader ccxt pandas numpy

import os
import time
import argparse
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import ccxt
import backtrader as bt


# ----------------------------
# Data Fetch
# ----------------------------
def fetch_ohlcv_df(exchange, symbol, timeframe, since_ms, limit=1000, cache_path=None):
    if cache_path and os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["datetime"])
        df = df.set_index("datetime").sort_index()
        return df

    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    all_rows = []
    since = since_ms
    n_calls = 0

    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        n_calls += 1
        if not batch:
            break

        all_rows.extend(batch)
        last_ts = batch[-1][0]
        next_since = last_ts + tf_ms
        if next_since <= since:
            break
        since = next_since

        if getattr(exchange, "enableRateLimit", False):
            time.sleep(exchange.rateLimit / 1000.0)

        if len(batch) < 1000:
            break

        if n_calls % 25 == 0:
            last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            print(f"Fetching... calls={n_calls}, last={last_dt.isoformat()}, bars={len(all_rows):,}")

    if not all_rows:
        raise RuntimeError("No OHLCV data fetched.")

    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop(columns=["ts"]).set_index("datetime").sort_index()
    df.index = df.index.tz_convert("UTC").tz_localize(None)  # backtrader: naive dt
    df["openinterest"] = 0.0

    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.reset_index().to_csv(cache_path, index=False)

    return df


# ----------------------------
# Commission: Perp-like
# ----------------------------
class PerpCommissionInfo(bt.CommInfoBase):
    params = dict(
        commission=0.0004,   # 0.04% placeholder
        leverage=3.0,        # margin model leverage
        stocklike=False,
        commtype=bt.CommInfoBase.COMM_PERC,
    )

    def get_margin(self, price):
        return price / self.p.leverage

    def _getcommission(self, size, price, pseudoexec):
        return abs(size) * price * self.p.commission


# ----------------------------
# Strategy
# ----------------------------
class RSI2TrendPullbackScalp(bt.Strategy):
    """
    5m scalping with robust edge:
      - Regime: 1H EMA200 direction only
      - Entry: 5m RSI(2) extreme pullback + 5m EMA50 direction filter
      - Exit: ATR stop, R-multiple TP, move stop to breakeven at +1R
      - Safety: cooldown after trades, daily lock (realized-ish: only when flat)
    """

    params = dict(
        # HTF regime (1H)
        ema200_1h=200,

        # LTF filters (5m)
        ema50_5m=50,
        rsi_period=2,
        rsi_long=10.0,          # RSI(2) <= 10 buy pullback
        rsi_short=90.0,         # RSI(2) >= 90 sell pullback
        atr_period=14,
        min_atr_pct=0.0006,     # 0.06%: low-vol chop cut (tune 0.0005-0.0010)

        # Exits
        sl_atr=1.0,             # stop distance = 1.0 * ATR
        tp_r=1.6,               # TP = 1.6R (tune 1.4-2.0)
        move_be_r=1.0,          # after +1R, move stop to entry
        time_stop_bars=10,      # 50 minutes max hold

        # Risk
        risk_per_trade=0.003,   # 0.3% (勝てるまで増やさない)
        max_notional_leverage=2.0,

        # Safety
        cooldown_bars=3,        # after entry, wait N bars before next signal
        cooldown_after_stop=6,  # after stop, wait 30min
        daily_loss_limit=0.02,  # -2% day (flat-only lock)

        printlog=False,
    )

    def __init__(self):
        self.d5 = self.datas[0]
        self.d1h = self.datas[1]

        # HTF
        self.ema200_1h = bt.indicators.EMA(self.d1h.close, period=self.p.ema200_1h)

        # LTF
        self.ema50_5m = bt.indicators.EMA(self.d5.close, period=self.p.ema50_5m)
        self.rsi2 = bt.indicators.RSI(self.d5.close, period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(self.d5, period=self.p.atr_period)

        # orders/state
        self.entry_order = None
        self.stop_order = None
        self.tp_order = None

        self.entry_price = None
        self.entry_bar = None
        self.stop_price = None
        self.r_dist = None
        self.cooldown = 0

        # daily lock (flat-only)
        self.cur_day = None
        self.day_start_value = None
        self.day_locked = False

        # stats
        self.sig_long = 0
        self.sig_short = 0
        self.opened = 0
        self.tps = 0
        self.stops = 0
        self.timeouts = 0
        self.moved_be = 0
        self.daily_locks = 0

    def _atr_ok(self):
        c = float(self.d5.close[0])
        a = float(self.atr[0])
        return (c > 0) and (a / c >= self.p.min_atr_pct)

    def _regime_long(self):
        if len(self.d1h) < self.p.ema200_1h + 5:
            return False
        return float(self.d1h.close[0]) > float(self.ema200_1h[0])

    def _regime_short(self):
        if len(self.d1h) < self.p.ema200_1h + 5:
            return False
        return float(self.d1h.close[0]) < float(self.ema200_1h[0])

    def _calc_size(self, stop_dist):
        equity = self.broker.getvalue()
        risk_cash = equity * self.p.risk_per_trade
        px = float(self.d5.close[0])
        if stop_dist <= 0 or px <= 0:
            return 0.0

        size = risk_cash / stop_dist  # BTC

        # cap notional
        max_notional = equity * self.p.max_notional_leverage
        size = min(size, max_notional / px)

        return max(size, 0.0)

    def _update_daily_lock(self):
        dt = self.d5.datetime.datetime(0)
        d = dt.date()
        if self.cur_day is None or d != self.cur_day:
            self.cur_day = d
            self.day_start_value = self.broker.getvalue()
            self.day_locked = False

        # flat-only lock (avoid killing good trades due to intratrade drawdown)
        if self.position.size == 0 and (not self.day_locked) and (self.day_start_value is not None):
            if self.broker.getvalue() <= self.day_start_value * (1.0 - self.p.daily_loss_limit):
                self.day_locked = True
                self.daily_locks += 1

    def _cancel_brackets(self):
        for o in [self.stop_order, self.tp_order]:
            if o is not None:
                self.cancel(o)
        self.stop_order = None
        self.tp_order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed and order == self.entry_order:
            self.entry_order = None
            self.entry_price = order.executed.price
            self.entry_bar = len(self.d5)

            atr = float(self.atr[0])
            stop_dist = self.p.sl_atr * atr
            self.r_dist = stop_dist

            if self.position.size > 0:
                self.stop_price = self.entry_price - stop_dist
                tp_price = self.entry_price + self.p.tp_r * stop_dist
                self.stop_order = self.sell(exectype=bt.Order.Stop, price=self.stop_price)
                self.tp_order = self.sell(exectype=bt.Order.Limit, price=tp_price)
            else:
                self.stop_price = self.entry_price + stop_dist
                tp_price = self.entry_price - self.p.tp_r * stop_dist
                self.stop_order = self.buy(exectype=bt.Order.Stop, price=self.stop_price)
                self.tp_order = self.buy(exectype=bt.Order.Limit, price=tp_price)

            self.opened += 1
            return

        if order.status == order.Completed and order in [self.stop_order, self.tp_order]:
            if order == self.stop_order:
                self.stops += 1
                self.cooldown = self.p.cooldown_after_stop
            else:
                self.tps += 1

            self._cancel_brackets()
            self.entry_price = None
            self.entry_bar = None
            self.stop_price = None
            self.r_dist = None
            return

        if order.status in [order.Canceled, order.Rejected, order.Margin]:
            if order == self.entry_order:
                self.entry_order = None
            if order in [self.stop_order, self.tp_order]:
                self._cancel_brackets()

    def next(self):
        self._update_daily_lock()

        if self.cooldown > 0:
            self.cooldown -= 1

        # manage BE move + time stop
        if self.position.size != 0 and self.entry_price is not None and self.r_dist is not None and self.stop_order is not None:
            held = len(self.d5) - (self.entry_bar if self.entry_bar is not None else len(self.d5))

            # move stop to breakeven at +1R (use close as trigger)
            if self.position.size > 0:
                if float(self.d5.close[0]) >= self.entry_price + self.p.move_be_r * self.r_dist:
                    if self.stop_price is not None and self.stop_price < self.entry_price:
                        self.cancel(self.stop_order)
                        self.stop_price = self.entry_price
                        self.stop_order = self.sell(exectype=bt.Order.Stop, price=self.stop_price)
                        self.moved_be += 1
            else:
                if float(self.d5.close[0]) <= self.entry_price - self.p.move_be_r * self.r_dist:
                    if self.stop_price is not None and self.stop_price > self.entry_price:
                        self.cancel(self.stop_order)
                        self.stop_price = self.entry_price
                        self.stop_order = self.buy(exectype=bt.Order.Stop, price=self.stop_price)
                        self.moved_be += 1

            if held >= self.p.time_stop_bars:
                self.timeouts += 1
                self._cancel_brackets()
                self.close()
                self.entry_price = None
                self.entry_bar = None
                self.stop_price = None
                self.r_dist = None
                return

        # no entries if locked/cooldown/in-position/pending
        if self.day_locked or self.cooldown > 0 or self.position.size != 0 or self.entry_order is not None:
            return

        if len(self.d5) < max(self.p.ema50_5m, self.p.atr_period, self.p.rsi_period) + 5:
            return
        if not self._atr_ok():
            return

        close = float(self.d5.close[0])
        ema50 = float(self.ema50_5m[0])
        rsi = float(self.rsi2[0])
        atr = float(self.atr[0])

        stop_dist = self.p.sl_atr * atr
        size = self._calc_size(stop_dist)
        if size <= 0:
            return

        # LONG: HTF up + LTF above EMA50 + RSI2 extreme oversold
        if self._regime_long() and close > ema50 and rsi <= self.p.rsi_long:
            self.sig_long += 1
            self.entry_order = self.buy(size=size)  # market next bar open
            self.cooldown = self.p.cooldown_bars
            return

        # SHORT: HTF down + LTF below EMA50 + RSI2 extreme overbought
        if self._regime_short() and close < ema50 and rsi >= self.p.rsi_short:
            self.sig_short += 1
            self.entry_order = self.sell(size=size)
            self.cooldown = self.p.cooldown_bars
            return

    def stop(self):
        print("\n===== Debug Summary (RSI2 Trend Pullback Scalp) =====")
        print(f"Signals Long:   {self.sig_long}")
        print(f"Signals Short:  {self.sig_short}")
        print(f"Trades Opened:  {self.opened}")
        print(f"TP hits:        {self.tps}")
        print(f"Stop hits:      {self.stops}")
        print(f"Time stops:     {self.timeouts}")
        print(f"Moved to BE:    {self.moved_be}")
        print(f"Daily locks:    {self.daily_locks}")


# ----------------------------
# Runner
# ----------------------------
def run_backtest(days, symbol, timeframe, cache, commission, slippage, leverage):
    ex = ccxt.binanceusdm({"enableRateLimit": True})

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    since_ms = int(start.timestamp() * 1000)

    cache_path = None
    if cache:
        safe_symbol = symbol.replace("/", "").replace(":", "_")
        cache_path = f"data/{safe_symbol}_{timeframe}_{days}d.csv"

    print(f"Fetching OHLCV {symbol} {timeframe} for ~{days} days ...")
    df = fetch_ohlcv_df(ex, symbol=symbol, timeframe=timeframe, since_ms=since_ms, limit=1000, cache_path=cache_path)

    df_bt = df[["open", "high", "low", "close", "volume", "openinterest"]].copy()
    data5 = bt.feeds.PandasData(dataname=df_bt)

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data5, name="BTC_PERP_5m")
    cerebro.resampledata(
        data5,
        timeframe=bt.TimeFrame.Minutes,
        compression=60,
        bar2edge=True,
        rightedge=True,
        adjbartime=True,
        name="BTC_PERP_1h",
    )

    initial_cash = 100_000.0
    cerebro.broker.setcash(initial_cash)

    comminfo = PerpCommissionInfo(commission=commission, leverage=leverage)
    cerebro.broker.addcommissioninfo(comminfo)

    if slippage and slippage > 0:
        cerebro.broker.set_slippage_perc(perc=slippage)

    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")

    cerebro.addstrategy(RSI2TrendPullbackScalp, printlog=False)

    results = cerebro.run(maxcpus=1)
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    total_return = final_value / initial_cash - 1.0

    dd = strat.analyzers.dd.get_analysis()
    max_dd = dd["max"]["drawdown"] / 100.0

    ta = strat.analyzers.ta.get_analysis()
    closed = ta.get("total", {}).get("closed", 0)
    won = ta.get("won", {}).get("total", 0)
    win_rate = (won / closed) if closed else float("nan")

    print("\n===== Backtest Report (5m RSI2 Trend Pullback Scalp) =====")
    print(f"Bars:           {len(df_bt):,} ({timeframe})")
    print(f"Initial Equity: {initial_cash:,.2f}")
    print(f"Final Equity:   {final_value:,.2f}")
    print(f"Total Return:   {total_return*100:,.2f}%")
    print(f"Max Drawdown:   {max_dd*100:,.2f}%")
    print(f"Trades(closed): {closed}")
    print(f"Win Rate:       {win_rate*100:,.2f}%" if not np.isnan(win_rate) else "Win Rate: N/A")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=730)
    p.add_argument("--symbol", type=str, default="BTC/USDT:USDT")
    p.add_argument("--timeframe", type=str, default="5m")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--commission", type=float, default=0.0004, help="0.0004=0.04% placeholder")
    p.add_argument("--slippage", type=float, default=0.00005, help="0.00005=0.005%")
    p.add_argument("--leverage", type=float, default=3.0, help="margin model leverage in backtest")
    args = p.parse_args()

    run_backtest(
        days=args.days,
        symbol=args.symbol,
        timeframe=args.timeframe,
        cache=(not args.no_cache),
        commission=args.commission,
        slippage=args.slippage,
        leverage=args.leverage,
    )


if __name__ == "__main__":
    main()
