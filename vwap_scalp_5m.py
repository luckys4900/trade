# 5m Scalping (2y target):
#   VWAP Pullback (mean reversion) + 1H EMA200 trend filter
#   Entry: Limit (maker-like) with timeout; no chasing market
#   Take Profit: fixed VWAP reversion (limit at entry VWAP)
#   Stop Loss: ATR-based stop (stop-market)
#   Time Stop: short (default 30 minutes)
# Risk: ATR-based sizing, 2% risk per trade
# Report: Total Return, Max Drawdown, Win Rate

import os
import time
import argparse
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import ccxt
import backtrader as bt


# ----------------------------
# CCXT: fetch OHLCV with pagination + CSV cache
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
    # backtrader expects naive datetime index; treat as UTC naive
    df.index = df.index.tz_convert("UTC").tz_localize(None)
    df["openinterest"] = 0.0

    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.reset_index().to_csv(cache_path, index=False)

    return df


# ----------------------------
# Indicators
# ----------------------------
class SessionVWAP(bt.Indicator):
    """
    Daily-anchored (UTC day) VWAP:
      VWAP = sum(typical_price * volume) / sum(volume)
    """
    lines = ("vwap",)

    def __init__(self):
        self._cum_pv = 0.0
        self._cum_v = 0.0
        self._cur_date = None

    def next(self):
        dt = self.data.datetime.datetime(0)  # naive UTC
        d = dt.date()
        if self._cur_date is None or d != self._cur_date:
            self._cur_date = d
            self._cum_pv = 0.0
            self._cum_v = 0.0

        tp = (self.data.high[0] + self.data.low[0] + self.data.close[0]) / 3.0
        v = float(self.data.volume[0])
        self._cum_pv += tp * v
        self._cum_v += v
        self.lines.vwap[0] = (self._cum_pv / self._cum_v) if self._cum_v > 0 else float(self.data.close[0])


# ----------------------------
# Strategy
# ----------------------------
class VWAPPullbackScalpPro(bt.Strategy):
    """
    5m scalp:
      - Only trade in 1H trend direction (EMA200 + slope)
      - Wait for overshoot from VWAP by ATR multiple
      - Require reclaim toward VWAP (avoid knife)
      - Enter via LIMIT with short timeout (maker-like); do not chase
      - TP fixed at entry VWAP (limit)
      - SL ATR-based (stop-market)
      - Time-stop short
    """

    params = dict(
        # HTF trend filter (1H)
        ema_period=200,
        ema_slope_lookback=3,

        # 5m volatility + setup
        atr_period=14,
        min_atr_pct=0.0010,          # 0.10%
        entry_overshoot_atr=0.8,     # overshoot from VWAP in ATR units
        reclaim_buffer_atr=0.10,     # require close to reclaim toward VWAP
        min_vwap_edge_atr=0.35,      # require enough room to VWAP to pay fees

        # execution (maker-like)
        entry_timeout_bars=2,        # cancel entry if not filled in N bars

        # exits
        sl_atr_mult=1.0,             # tighter than swing style (scalp)
        max_hold_bars=6,             # 6*5m = 30 min

        # risk sizing
        risk_per_trade=0.02,         # 2%
        max_leverage=2.0,            # cap notional to equity*max_leverage

        printlog=False,
    )

    def log(self, txt):
        if self.p.printlog:
            dt = self.datas[0].datetime.datetime(0)
            print(f"{dt.isoformat()} {txt}")

    def __init__(self):
        # data0: 5m, data1: 1h (resampled from same feed)
        self.d5 = self.datas[0]
        self.d1h = self.datas[1]

        self.vwap = SessionVWAP(self.d5)
        self.atr = bt.indicators.ATR(self.d5, period=self.p.atr_period)
        self.ema1h = bt.indicators.EMA(self.d1h.close, period=self.p.ema_period)

        # orders
        self.entry_order = None
        self.entry_order_bar = None
        self.tp_order = None
        self.sl_order = None

        # state
        self.entry_price = None
        self.entry_bar = None
        self.entry_vwap = None

    def _trend_ok_long(self):
        if len(self.d1h) < self.p.ema_period + self.p.ema_slope_lookback + 5:
            return False
        ema_now = float(self.ema1h[0])
        ema_prev = float(self.ema1h[-self.p.ema_slope_lookback])
        return (float(self.d1h.close[0]) > ema_now) and (ema_now > ema_prev)

    def _trend_ok_short(self):
        if len(self.d1h) < self.p.ema_period + self.p.ema_slope_lookback + 5:
            return False
        ema_now = float(self.ema1h[0])
        ema_prev = float(self.ema1h[-self.p.ema_slope_lookback])
        return (float(self.d1h.close[0]) < ema_now) and (ema_now < ema_prev)

    def _atr_pct_ok(self):
        c = float(self.d5.close[0])
        a = float(self.atr[0])
        return (c > 0) and ((a / c) >= self.p.min_atr_pct)

    def _calc_size(self, stop_dist):
        equity = self.broker.getvalue()
        risk_cash = equity * self.p.risk_per_trade
        px = float(self.d5.close[0])

        if stop_dist <= 0 or px <= 0:
            return 0.0

        size = risk_cash / stop_dist  # BTC size

        # cap by max notional
        max_notional = equity * self.p.max_leverage
        size_cap = max_notional / px
        size = min(size, size_cap)

        # cap by cash (since this is a simplified single-instrument backtest)
        cash = self.broker.getcash()
        cash_cap = cash / px
        size = min(size, cash_cap)

        return max(size, 0.0)

    def _cancel_exits(self):
        for o in [self.tp_order, self.sl_order]:
            if o is not None:
                self.cancel(o)
        self.tp_order = None
        self.sl_order = None

    def _cancel_entry(self):
        if self.entry_order is not None:
            self.cancel(self.entry_order)
        self.entry_order = None
        self.entry_order_bar = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        # Entry filled -> place TP/SL
        if order.status == order.Completed and order == self.entry_order:
            self.entry_price = order.executed.price
            self.entry_bar = len(self.d5)
            # keep entry_vwap captured at signal time (set in next())
            evwap = float(self.entry_vwap) if self.entry_vwap is not None else float(self.vwap.vwap[0])
            atr = float(self.atr[0])

            self.entry_order = None
            self.entry_order_bar = None

            if self.position.size > 0:
                # TP at entry VWAP (mean reversion)
                tp = evwap
                sl = self.entry_price - self.p.sl_atr_mult * atr
                self.tp_order = self.sell(exectype=bt.Order.Limit, price=tp)
                self.sl_order = self.sell(exectype=bt.Order.Stop, price=sl)
                self.log(f"LONG filled @ {self.entry_price:.2f} TP(VWAP)={tp:.2f} SL={sl:.2f}")
            elif self.position.size < 0:
                tp = evwap
                sl = self.entry_price + self.p.sl_atr_mult * atr
                self.tp_order = self.buy(exectype=bt.Order.Limit, price=tp)
                self.sl_order = self.buy(exectype=bt.Order.Stop, price=sl)
                self.log(f"SHORT filled @ {self.entry_price:.2f} TP(VWAP)={tp:.2f} SL={sl:.2f}")

            return

        # If TP or SL filled -> cancel other; reset state
        if order.status == order.Completed and order in [self.tp_order, self.sl_order]:
            self.log("Exit filled; cancelling other exit")
            self._cancel_exits()
            self.entry_price = None
            self.entry_bar = None
            self.entry_vwap = None
            return

        # Clean up rejected/canceled
        if order.status in [order.Canceled, order.Rejected, order.Margin]:
            if order == self.entry_order:
                self.entry_order = None
                self.entry_order_bar = None
                self.entry_vwap = None
            if order in [self.tp_order, self.sl_order]:
                # avoid naked position logic; cancel both and let next() time-stop/close handle if needed
                self._cancel_exits()

    def next(self):
        # 1) Entry order timeout (maker-like: if not filled, cancel; do not chase)
        if self.entry_order is not None and self.entry_order_bar is not None:
            if (len(self.d5) - self.entry_order_bar) >= self.p.entry_timeout_bars:
                self.log("Entry timeout -> cancel (no chase)")
                self._cancel_entry()
                self.entry_vwap = None
                return

        # 2) Time stop (fast scalp): if still in position too long, flatten
        if self.position.size != 0 and self.entry_bar is not None:
            held = len(self.d5) - self.entry_bar
            if held >= self.p.max_hold_bars:
                self.log("Time stop -> flatten")
                self._cancel_exits()
                self.close()  # market close next bar
                self.entry_price = None
                self.entry_bar = None
                self.entry_vwap = None
                return

        # 3) If in position or waiting on entry, do nothing
        if self.position.size != 0 or self.entry_order is not None:
            return

        # 4) Ensure indicators ready
        if len(self.d5) < self.p.atr_period + 5:
            return
        if not self._atr_pct_ok():
            return

        close = float(self.d5.close[0])
        low = float(self.d5.low[0])
        high = float(self.d5.high[0])
        vwap = float(self.vwap.vwap[0])
        atr = float(self.atr[0])

        # Require "enough edge" to VWAP (prevents fee-noise trades)
        vwap_dist = abs(vwap - close)
        if vwap_dist < self.p.min_vwap_edge_atr * atr:
            return

        long_overshoot = vwap - self.p.entry_overshoot_atr * atr
        short_overshoot = vwap + self.p.entry_overshoot_atr * atr

        long_reclaim = vwap - self.p.reclaim_buffer_atr * atr
        short_reclaim = vwap + self.p.reclaim_buffer_atr * atr

        # Momentum confirmation (minimal): reversal candle vs prior close
        mom_up = float(self.d5.close[0]) > float(self.d5.close[-1])
        mom_dn = float(self.d5.close[0]) < float(self.d5.close[-1])

        # SL distance for sizing
        stop_dist = self.p.sl_atr_mult * atr
        size = self._calc_size(stop_dist)
        if size <= 0:
            return

        # LONG: 1H uptrend + dip below VWAP-ATR + reclaim upward
        if self._trend_ok_long():
            dipped = low <= long_overshoot
            reclaimed = close >= long_reclaim
            # also ensure we are still below VWAP (mean reversion target above entry)
            below_vwap = close < vwap

            if dipped and reclaimed and mom_up and below_vwap:
                # maker-like limit entry near close (no market chase)
                self.entry_vwap = vwap
                self.entry_order = self.buy(exectype=bt.Order.Limit, price=close, size=size)
                self.entry_order_bar = len(self.d5)
                self.log(f"Signal LONG -> LIMIT @ {close:.2f} size={size:.4f} TP@VWAP={vwap:.2f}")
                return

        # SHORT: 1H downtrend + spike above VWAP+ATR + reclaim downward
        if self._trend_ok_short():
            spiked = high >= short_overshoot
            reclaimed = close <= short_reclaim
            above_vwap = close > vwap

            if spiked and reclaimed and mom_dn and above_vwap:
                self.entry_vwap = vwap
                self.entry_order = self.sell(exectype=bt.Order.Limit, price=close, size=size)
                self.entry_order_bar = len(self.d5)
                self.log(f"Signal SHORT -> LIMIT @ {close:.2f} size={size:.4f} TP@VWAP={vwap:.2f}")
                return


# ----------------------------
# Runner / Reporting
# ----------------------------
def run_backtest(days, symbol, timeframe, cache, commission, slippage):
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
    cerebro.resampledata(data5, timeframe=bt.TimeFrame.Minutes, compression=60, name="BTC_PERP_1h")

    initial_cash = 100_000.0
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)

    if slippage and slippage > 0:
        # affects market orders; limit orders still fill at limit in bt
        cerebro.broker.set_slippage_perc(perc=slippage)

    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")

    cerebro.addstrategy(VWAPPullbackScalpPro, printlog=False)

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

    print("\n===== Backtest Report (5m VWAP Pullback Scalp: TP=VWAP, Maker-like Limit Entry) =====")
    print(f"Bars:          {len(df_bt):,} ({timeframe})")
    print(f"Initial Equity:{initial_cash:,.2f}")
    print(f"Final Equity:  {final_value:,.2f}")
    print(f"Total Return:  {total_return*100:,.2f}%")
    print(f"Max Drawdown:  {max_dd*100:,.2f}%")
    print(f"Trades:        {closed}")
    print(f"Win Rate:      {win_rate*100:,.2f}%" if not np.isnan(win_rate) else "Win Rate: N/A")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=730, help="lookback days (default: ~2 years)")
    p.add_argument("--symbol", type=str, default="BTC/USDT:USDT", help="Binance USDT-M perp symbol")
    p.add_argument("--timeframe", type=str, default="5m", help="timeframe (default: 5m)")
    p.add_argument("--no-cache", action="store_true", help="disable CSV cache")
    p.add_argument("--commission", type=float, default=0.0004, help="commission rate (fraction). ex: 0.0004=0.04%")
    p.add_argument("--slippage", type=float, default=0.00005, help="slippage (fraction) for market orders. ex: 0.00005=0.005%")
    args = p.parse_args()

    run_backtest(
        days=args.days,
        symbol=args.symbol,
        timeframe=args.timeframe,
        cache=(not args.no_cache),
        commission=args.commission,
        slippage=args.slippage,
    )


if __name__ == "__main__":
    main()
