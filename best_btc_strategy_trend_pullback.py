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
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
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

        if len(batch) < limit:
            break

        if n_calls % 25 == 0:
            last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            print(f"Fetching... calls={n_calls}, last={last_dt.isoformat()}, bars={len(all_rows):,}")

    if not all_rows:
        raise RuntimeError("No OHLCV data fetched.")

    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop(columns=["ts"]).set_index("datetime").sort_index()
    df.index = df.index.tz_convert("UTC").tz_localize(None)  # backtrader wants naive dt
    df["openinterest"] = 0.0

    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.reset_index().to_csv(cache_path, index=False)

    return df


# ----------------------------
# Commission for Perp-like margin/leverage
# ----------------------------
class PerpCommissionInfo(bt.CommInfoBase):
    """
    Approx futures/perp:
      - commission charged on notional: abs(size)*price*commission
      - margin per BTC ~= price/leverage
    """
    params = dict(
        commission=0.0004,   # 0.04% (placeholder)
        leverage=3.0,        # margin model leverage
        stocklike=False,
        commtype=bt.CommInfoBase.COMM_PERC,
    )

    def get_margin(self, price):
        return price / self.p.leverage

    def _getcommission(self, size, price, pseudoexec):
        return abs(size) * price * self.p.commission


# ----------------------------
# Strategy: Trend Pullback Scalping
# ----------------------------
class TrendPullbackScalp(bt.Strategy):
    """
    Goal: positive expectancy by avoiding mean-reversion traps.
    - 1H regime: EMA200 + EMA50 alignment + ADX filter (trend only)
    - 5m entry: pullback to EMA20 then reclaim (cross back) + small momentum confirmation
    - Exit: SL = ATR * sl_atr; TP = R-multiple (tp_r)
    - Risk: ATR-based position sizing (risk_per_trade)
    - Risk control: move SL to breakeven at +1R, time stop, daily loss lock, cooldown after stop
    """

    params = dict(
        # HTF (1H) regime
        ema_slow_1h=200,
        ema_fast_1h=50,
        adx_period_1h=14,
        min_adx_1h=18.0,         # trend strength threshold

        # LTF (5m) setup
        ema_entry_5m=20,
        atr_period_5m=14,
        min_atr_pct_5m=0.0007,   # 0.07%: low-vol chop cut
        pullback_atr=0.3,        # require pullback depth relative to ATR (touch near EMA20)
        cooldown_bars=3,         # prevent rapid re-entries

        # Exits (R-based)
        sl_atr=1.1,
        tp_r=1.5,                # take profit at 1.5R
        move_be_r=1.0,           # move stop to breakeven after +1R
        time_stop_bars=8,        # 8*5m = 40min

        # Risk
        risk_per_trade=0.003,    # 0.3% (まずDDを殺す。勝ててから上げる)
        max_notional_leverage=2.0,  # cap notional <= equity*2

        # Safety
        daily_loss_limit=0.015,  # -1.5%/dayでロック
        cooldown_after_stop=6,   # stop後は30min休む

        printlog=False,
    )

    def __init__(self):
        self.d5 = self.datas[0]
        self.d1h = self.datas[1]

        # HTF indicators
        self.ema200_1h = bt.indicators.EMA(self.d1h.close, period=self.p.ema_slow_1h)
        self.ema50_1h = bt.indicators.EMA(self.d1h.close, period=self.p.ema_fast_1h)
        self.adx_1h = bt.indicators.ADX(self.d1h, period=self.p.adx_period_1h)

        # LTF indicators
        self.ema20_5m = bt.indicators.EMA(self.d5.close, period=self.p.ema_entry_5m)
        self.atr_5m = bt.indicators.ATR(self.d5, period=self.p.atr_period_5m)

        # orders/state
        self.entry_order = None
        self.stop_order = None
        self.tp_order = None

        self.entry_bar = None
        self.entry_price = None
        self.stop_price = None
        self.r_dist = None  # 1R distance in price
        self.cooldown = 0

        # daily lock
        self.cur_day = None
        self.day_start_value = None
        self.day_locked = False

        # stats
        self.sig_long = 0
        self.sig_short = 0
        self.trades_opened = 0
        self.moved_be = 0
        self.stops = 0
        self.tps = 0
        self.timeouts = 0
        self.daily_locks = 0

    def _update_daily_lock(self):
        dt = self.d5.datetime.datetime(0)
        d = dt.date()
        if self.cur_day is None or d != self.cur_day:
            self.cur_day = d
            self.day_start_value = self.broker.getvalue()
            self.day_locked = False

        if (not self.day_locked) and (self.day_start_value is not None):
            if self.broker.getvalue() <= self.day_start_value * (1.0 - self.p.daily_loss_limit):
                self.day_locked = True
                self.daily_locks += 1
                # flatten
                if self.position.size != 0:
                    self.close()

    def _atr_pct_ok(self):
        c = float(self.d5.close[0])
        a = float(self.atr_5m[0])
        return (c > 0) and (a / c >= self.p.min_atr_pct_5m)

    def _regime_long(self):
        if len(self.d1h) < self.p.ema_slow_1h + 10:
            return False
        return (self.d1h.close[0] > self.ema200_1h[0]) and (self.ema50_1h[0] > self.ema200_1h[0]) and (self.adx_1h[0] >= self.p.min_adx_1h)

    def _regime_short(self):
        if len(self.d1h) < self.p.ema_slow_1h + 10:
            return False
        return (self.d1h.close[0] < self.ema200_1h[0]) and (self.ema50_1h[0] < self.ema200_1h[0]) and (self.adx_1h[0] >= self.p.min_adx_1h)

    def _calc_size(self, stop_dist):
        equity = self.broker.getvalue()
        risk_cash = equity * self.p.risk_per_trade
        px = float(self.d5.close[0])
        if stop_dist <= 0 or px <= 0:
            return 0.0

        size = risk_cash / stop_dist

        # cap by notional leverage
        max_notional = equity * self.p.max_notional_leverage
        size = min(size, max_notional / px)

        return max(size, 0.0)

    def _cancel_brackets(self):
        for o in [self.stop_order, self.tp_order]:
            if o is not None:
                self.cancel(o)
        self.stop_order = None
        self.tp_order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        # entry filled => place stop/TP
        if order.status == order.Completed and order == self.entry_order:
            self.entry_order = None
            self.entry_bar = len(self.d5)
            self.entry_price = order.executed.price

            atr = float(self.atr_5m[0])
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

            self.trades_opened += 1
            return

        # stop/TP filled
        if order.status == order.Completed and order in [self.stop_order, self.tp_order]:
            if order == self.stop_order:
                self.stops += 1
                self.cooldown = self.p.cooldown_after_stop
            if order == self.tp_order:
                self.tps += 1

            self._cancel_brackets()
            self.entry_bar = None
            self.entry_price = None
            self.stop_price = None
            self.r_dist = None
            return

        # cleanup
        if order.status in [order.Canceled, order.Rejected, order.Margin]:
            if order == self.entry_order:
                self.entry_order = None
            if order in [self.stop_order, self.tp_order]:
                self._cancel_brackets()

    def next(self):
        self._update_daily_lock()

        if self.cooldown > 0:
            self.cooldown -= 1

        # time stop management + BE move
        if self.position.size != 0 and self.entry_bar is not None and self.entry_price is not None and self.r_dist is not None:
            held = len(self.d5) - self.entry_bar

            # move stop to breakeven after +1R
            if self.stop_order is not None:
                if self.position.size > 0:
                    if float(self.d5.close[0]) >= self.entry_price + self.p.move_be_r * self.r_dist:
                        # move stop up to entry if still below
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
                self.entry_bar = None
                self.entry_price = None
                self.stop_price = None
                self.r_dist = None
                return

        # no new entry if locked/cooldown/in position/pending order
        if self.day_locked or self.cooldown > 0 or self.position.size != 0 or self.entry_order is not None:
            return

        if len(self.d5) < max(self.p.atr_period_5m, self.p.ema_entry_5m) + 5:
            return
        if not self._atr_pct_ok():
            return

        atr = float(self.atr_5m[0])
        ema = float(self.ema20_5m[0])
        close = float(self.d5.close[0])
        prev_close = float(self.d5.close[-1])
        low = float(self.d5.low[0])
        high = float(self.d5.high[0])

        # Pullback definition:
        #  - long: price was below EMA20 (pullback), now crosses back above EMA20 with upward momentum
        #  - and pullback depth: low <= EMA20 - pullback_atr*ATR
        pullback_depth_long = low <= (ema - self.p.pullback_atr * atr)
        cross_up = (prev_close <= ema) and (close > ema) and (close > prev_close)

        pullback_depth_short = high >= (ema + self.p.pullback_atr * atr)
        cross_dn = (prev_close >= ema) and (close < ema) and (close < prev_close)

        stop_dist = self.p.sl_atr * atr
        size = self._calc_size(stop_dist)
        if size <= 0:
            return

        if self._regime_long():
            if pullback_depth_long and cross_up:
                self.sig_long += 1
                self.entry_order = self.buy(size=size)  # market next bar open
                self.cooldown = self.p.cooldown_bars
                return

        if self._regime_short():
            if pullback_depth_short and cross_dn:
                self.sig_short += 1
                self.entry_order = self.sell(size=size)
                self.cooldown = self.p.cooldown_bars
                return

    def stop(self):
        print("\n===== Debug Summary (Trend Pullback Scalp) =====")
        print(f"Signals Long:    {self.sig_long}")
        print(f"Signals Short:   {self.sig_short}")
        print(f"Trades Opened:   {self.trades_opened}")
        print(f"TP hits:         {self.tps}")
        print(f"Stop hits:       {self.stops}")
        print(f"Time stops:      {self.timeouts}")
        print(f"Moved to BE:     {self.moved_be}")
        print(f"Daily locks:     {self.daily_locks}")


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

    # Perp-like commission/margin
    comminfo = PerpCommissionInfo(commission=commission, leverage=leverage)
    cerebro.broker.addcommissioninfo(comminfo)

    if slippage and slippage > 0:
        cerebro.broker.set_slippage_perc(perc=slippage)

    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")

    cerebro.addstrategy(TrendPullbackScalp, printlog=False)

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

    print("\n===== Backtest Report (5m Trend Pullback Scalp) =====")
    print(f"Bars:          {len(df_bt):,} ({timeframe})")
    print(f"Initial Equity:{initial_cash:,.2f}")
    print(f"Final Equity:  {final_value:,.2f}")
    print(f"Total Return:  {total_return*100:,.2f}%")
    print(f"Max Drawdown:  {max_dd*100:,.2f}%")
    print(f"Trades(closed):{closed}")
    print(f"Win Rate:      {win_rate*100:,.2f}%" if not np.isnan(win_rate) else "Win Rate: N/A")


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
