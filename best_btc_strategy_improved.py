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


# ---------- Data Fetch (ccxt) ----------
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
    df.index = df.index.tz_convert("UTC").tz_localize(None)  # backtrader naive UTC
    df["openinterest"] = 0.0

    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.reset_index().to_csv(cache_path, index=False)

    return df


# ---------- Indicators ----------
class SessionVWAP(bt.Indicator):
    """Daily (UTC) reset VWAP using typical price."""
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


# ---------- Strategy ----------
class VWAPBandReversionScalp(bt.Strategy):
    """
    5m scalp:
      - HTF (1H) EMA filter
      - Overshoot outside VWAP band (ATR multiple) then re-enter band => mean reversion entry
      - Entry: market (next bar open) for research stability
      - TP: entry VWAP
      - SL: ATR multiple (enforced by bar-close check)
      - Time stop: short
      - Cooldown after stop
      - Daily loss limit
    """

    params = dict(
        # HTF filter (1H)
        ema_period_1h=50,

        # 5m
        atr_period=14,
        band_atr=0.9,              # VWAP ± band_atr*ATR
        sl_atr=1.2,                # stop distance
        time_stop_bars=3,          # 3 bars = 15min
        min_edge_bps=8.0,          # require VWAP distance >= X bps to avoid fee-noise

        # risk
        risk_per_trade=0.005,      # 0.5% (2%はスキャだとDDが跳ねやすい)
        max_leverage=2.0,          # notional cap

        # safety
        cooldown_bars=6,           # after stop, wait 30min
        daily_loss_limit=0.02,     # -2% from day start => stop trading that day

        printlog=False,
    )

    def log(self, txt):
        if self.p.printlog:
            dt = self.datas[0].datetime.datetime(0)
            print(f"{dt.isoformat()} {txt}")

    def __init__(self):
        self.d5 = self.datas[0]
        self.d1h = self.datas[1]

        self.vwap = SessionVWAP(self.d5)
        self.atr = bt.indicators.ATR(self.d5, period=self.p.atr_period)
        self.ema1h = bt.indicators.EMA(self.d1h.close, period=self.p.ema_period_1h)

        # state
        self.entry_bar = None
        self.entry_vwap = None
        self.stop_price = None
        self.tp_price = None
        self.cooldown = 0

        # daily lock
        self.cur_day = None
        self.day_start_value = None
        self.day_locked = False

        # stats/debug
        self.sig_long = 0
        self.sig_short = 0
        self.entries = 0
        self.stops = 0
        self.tps = 0
        self.timeouts = 0
        self.daily_lock_count = 0

    def _trend_long(self):
        if len(self.d1h) < self.p.ema_period_1h + 5:
            return False
        return float(self.d1h.close[0]) > float(self.ema1h[0])

    def _trend_short(self):
        if len(self.d1h) < self.p.ema_period_1h + 5:
            return False
        return float(self.d1h.close[0]) < float(self.ema1h[0])

    def _edge_ok(self, price, vwap):
        # require distance to vwap >= min_edge_bps
        if price <= 0:
            return False
        dist_bps = abs(vwap - price) / price * 10000.0
        return dist_bps >= self.p.min_edge_bps

    def _calc_size(self, stop_dist):
        equity = self.broker.getvalue()
        risk_cash = equity * self.p.risk_per_trade
        px = float(self.d5.close[0])
        if stop_dist <= 0 or px <= 0:
            return 0.0

        size = risk_cash / stop_dist  # BTC

        # cap by notional leverage
        max_notional = equity * self.p.max_leverage
        size = min(size, max_notional / px)

        # cap by cash (backtrader margin not modeled like futures)
        cash = self.broker.getcash()
        size = min(size, cash / px)

        return max(size, 0.0)

    def _update_daily_lock(self):
        dt = self.d5.datetime.datetime(0)
        d = dt.date()
        if self.cur_day is None or d != self.cur_day:
            self.cur_day = d
            self.day_start_value = self.broker.getvalue()
            self.day_locked = False

        if not self.day_locked and self.day_start_value is not None:
            if self.broker.getvalue() <= self.day_start_value * (1.0 - self.p.daily_loss_limit):
                self.day_locked = True
                self.daily_lock_count += 1
                # flatten if any
                if self.position.size != 0:
                    self.close()

    def next(self):
        self._update_daily_lock()

        # cooldown countdown
        if self.cooldown > 0:
            self.cooldown -= 1

        # manage open position via bar-close checks (robust in bar-based backtests)
        if self.position.size != 0 and self.entry_bar is not None:
            held = len(self.d5) - self.entry_bar
            close = float(self.d5.close[0])

            if self.position.size > 0:
                # TP / SL
                if self.tp_price is not None and close >= self.tp_price:
                    self.tps += 1
                    self.close()
                    self._reset_trade_state()
                    return
                if self.stop_price is not None and close <= self.stop_price:
                    self.stops += 1
                    self.close()
                    self._reset_trade_state(stopout=True)
                    return
            else:
                if self.tp_price is not None and close <= self.tp_price:
                    self.tps += 1
                    self.close()
                    self._reset_trade_state()
                    return
                if self.stop_price is not None and close >= self.stop_price:
                    self.stops += 1
                    self.close()
                    self._reset_trade_state(stopout=True)
                    return

            # time stop
            if held >= self.p.time_stop_bars:
                self.timeouts += 1
                self.close()
                self._reset_trade_state()
                return

        # no new entries if day locked or cooldown or already in position
        if self.day_locked or self.cooldown > 0 or self.position.size != 0:
            return

        if len(self.d5) < self.p.atr_period + 5:
            return

        vwap = float(self.vwap.vwap[0])
        atr = float(self.atr[0])
        if atr <= 0:
            return

        close = float(self.d5.close[0])
        prev_close = float(self.d5.close[-1])
        low = float(self.d5.low[0])
        high = float(self.d5.high[0])

        lower = vwap - self.p.band_atr * atr
        upper = vwap + self.p.band_atr * atr

        # core idea: went outside band, now re-enter band (reversion trigger)
        # LONG signal: touched below lower band, then closes back above lower band, still below VWAP
        if self._trend_long():
            if (low <= lower) and (close > lower) and (close < vwap) and (close > prev_close) and self._edge_ok(close, vwap):
                self.sig_long += 1
                stop_dist = self.p.sl_atr * atr
                size = self._calc_size(stop_dist)
                if size > 0:
                    self.buy(size=size)  # market next bar open
                    self.entries += 1
                    # store intended exit levels based on signal-time values
                    self.entry_bar = len(self.d5)
                    self.entry_vwap = vwap
                    self.tp_price = vwap
                    self.stop_price = close - stop_dist  # approx (bar-close model)
                return

        # SHORT signal
        if self._trend_short():
            if (high >= upper) and (close < upper) and (close > vwap) and (close < prev_close) and self._edge_ok(close, vwap):
                self.sig_short += 1
                stop_dist = self.p.sl_atr * atr
                size = self._calc_size(stop_dist)
                if size > 0:
                    self.sell(size=size)
                    self.entries += 1
                    self.entry_bar = len(self.d5)
                    self.entry_vwap = vwap
                    self.tp_price = vwap
                    self.stop_price = close + stop_dist
                return

    def _reset_trade_state(self, stopout=False):
        self.entry_bar = None
        self.entry_vwap = None
        self.stop_price = None
        self.tp_price = None
        if stopout:
            self.cooldown = self.p.cooldown_bars

    def stop(self):
        print("\n===== Debug Summary =====")
        print(f"Signals Long:  {self.sig_long}")
        print(f"Signals Short: {self.sig_short}")
        print(f"Entries Sent:  {self.entries}")
        print(f"TP hits:       {self.tps}")
        print(f"Stop hits:     {self.stops}")
        print(f"Time stops:    {self.timeouts}")
        print(f"Daily locks:   {self.daily_lock_count}")


# ---------- Run ----------
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
    cerebro.broker.setcommission(commission=commission)
    if slippage and slippage > 0:
        cerebro.broker.set_slippage_perc(perc=slippage)

    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")

    cerebro.addstrategy(VWAPBandReversionScalp, printlog=False)

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

    print("\n===== Backtest Report (5m VWAP Band Reversion Scalp) =====")
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
    p.add_argument("--commission", type=float, default=0.0004, help="0.0004 = 0.04%")
    p.add_argument("--slippage", type=float, default=0.0001, help="0.0001 = 0.01%")
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
