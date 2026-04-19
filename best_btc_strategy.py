# best_btc_strategy.py
# Requirements:
#   pip install backtrader ccxt pandas numpy
#
# Notes:
# - Fetches 180 days of 1h data from Binance Spot and Binance USDT-M Perp (via ccxt.binanceusdm)
# - Fetches funding rate history (8h) and applies funding cashflows during open perp positions
# - Implements delta-neutral funding capture with spread-ATR risk sizing (2% per trade)
# - Prints Total Return, Max Drawdown, Win Rate

import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import ccxt
import backtrader as bt


# ----------------------------
# Data Fetching (ccxt)
# ----------------------------
def _fetch_ohlcv_paginated(exchange, symbol, timeframe="1h", since_ms=None, limit=1000, max_bars=None):
    """
    Fetch OHLCV with pagination. Returns list of [ts, o, h, l, c, v].
    """
    all_rows = []
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    now_ms = exchange.milliseconds()

    since = since_ms
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        if not batch:
            break

        all_rows.extend(batch)

        # advance since to next candle
        last_ts = batch[-1][0]
        since = last_ts + tf_ms

        if max_bars is not None and len(all_rows) >= max_bars:
            all_rows = all_rows[:max_bars]
            break

        # stop if we're near "now"
        if since >= now_ms - tf_ms:
            break

        # rate limit
        if getattr(exchange, "enableRateLimit", False):
            time.sleep(exchange.rateLimit / 1000.0)

        # prevent infinite loop
        if len(batch) < limit:
            break

    # de-dup by timestamp, sort
    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts")
    return df.values.tolist()


def _to_ohlcv_df(rows):
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop(columns=["ts"])
    df = df.set_index("datetime")
    # backtrader expects naive datetime index; treat as UTC naive
    df.index = df.index.tz_convert("UTC").tz_localize(None)
    df["openinterest"] = 0.0
    return df[["open", "high", "low", "close", "volume", "openinterest"]]


def _fetch_funding_rate_history_binance_usdm(futures_ex, symbol_raw="BTCUSDT", since_ms=None, limit=1000):
    """
    Fetch funding rate history for Binance USDT-M perpetual.
    Tries ccxt unified method first; falls back to raw endpoint.
    Returns list of dict: {'datetime': naive_utc_datetime_hour, 'rate': float}
    """
    records = []

    # 1) unified method (if available)
    if hasattr(futures_ex, "fetch_funding_rate_history"):
        try:
            # ccxt unified symbols vary; for unified we try with raw then with ccxt symbol
            # Many ccxt builds expect unified symbol like 'BTC/USDT:USDT'
            unified_symbol = None
            try:
                futures_ex.load_markets()
                # find a perp symbol that matches BTC/USDT
                if "BTC/USDT:USDT" in futures_ex.symbols:
                    unified_symbol = "BTC/USDT:USDT"
                elif "BTC/USDT" in futures_ex.symbols:
                    unified_symbol = "BTC/USDT"
            except Exception:
                unified_symbol = None

            if unified_symbol is None:
                unified_symbol = "BTC/USDT:USDT"

            # paginate
            since = since_ms
            while True:
                batch = futures_ex.fetch_funding_rate_history(unified_symbol, since=since, limit=limit)
                if not batch:
                    break
                for x in batch:
                    # x keys often: timestamp, datetime, fundingRate
                    ts = x.get("timestamp", None)
                    rate = x.get("fundingRate", None)
                    if ts is None or rate is None:
                        continue
                    dt = pd.to_datetime(ts, unit="ms", utc=True).floor("h")
                    dt = dt.tz_convert("UTC").tz_localize(None)
                    records.append({"datetime": dt, "rate": float(rate)})
                last_ts = batch[-1].get("timestamp", None)
                if last_ts is None:
                    break
                # funding is 8h; step a bit forward
                since = last_ts + 1
                if getattr(futures_ex, "enableRateLimit", False):
                    time.sleep(futures_ex.rateLimit / 1000.0)
                if len(batch) < limit:
                    break

            if records:
                df = pd.DataFrame(records).drop_duplicates(subset=["datetime"]).sort_values("datetime")
                return df.to_dict("records")
        except Exception:
            pass

    # 2) raw endpoint fallback: fapi/v1/fundingRate
    # ccxt method name differs across versions; use getattr
    method = None
    for cand in ["fapiPublicGetFundingRate", "fapiPublic_get_fundingrate"]:
        if hasattr(futures_ex, cand):
            method = getattr(futures_ex, cand)
            break
    if method is None:
        raise RuntimeError("Cannot find Binance futures funding rate endpoint in this ccxt version.")

    since = since_ms
    while True:
        params = {
            "symbol": symbol_raw,
            "startTime": since,
            "limit": limit,
        }
        batch = method(params)
        if not batch:
            break
        for x in batch:
            ts = int(x["fundingTime"])
            rate = float(x["fundingRate"])
            dt = pd.to_datetime(ts, unit="ms", utc=True).floor("H")
            dt = dt.tz_convert("UTC").tz_localize(None)
            records.append({"datetime": dt, "rate": rate})
        last_ts = int(batch[-1]["fundingTime"])
        since = last_ts + 1

        if getattr(futures_ex, "enableRateLimit", False):
            time.sleep(futures_ex.rateLimit / 1000.0)

        if len(batch) < limit:
            break

    df = pd.DataFrame(records).drop_duplicates(subset=["datetime"]).sort_values("datetime")
    return df.to_dict("records")


def fetch_data(days=180, timeframe="1h"):
    """
    Returns:
      spot_df: pandas OHLCV for BTC/USDT spot (naive UTC index)
      perp_df: pandas OHLCV for BTC/USDT perpetual (naive UTC index)
      funding_map: dict[datetime] -> funding_rate (float), datetime is naive UTC hour
    """
    spot_ex = ccxt.binance({"enableRateLimit": True})
    futures_ex = ccxt.binanceusdm({"enableRateLimit": True})

    # Symbols
    spot_symbol = "BTC/USDT"
    perp_symbol = "BTC/USDT:USDT"  # Binance USDT-M perpetual in ccxt
    funding_symbol_raw = "BTCUSDT"

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    since_ms = int(start.timestamp() * 1000)

    # Fetch OHLCV
    spot_rows = _fetch_ohlcv_paginated(spot_ex, spot_symbol, timeframe=timeframe, since_ms=since_ms, limit=1000)
    perp_rows = _fetch_ohlcv_paginated(futures_ex, perp_symbol, timeframe=timeframe, since_ms=since_ms, limit=1000)

    spot_df = _to_ohlcv_df(spot_rows)
    perp_df = _to_ohlcv_df(perp_rows)

    # Align by intersection of timestamps
    idx = spot_df.index.intersection(perp_df.index)
    spot_df = spot_df.loc[idx].copy()
    perp_df = perp_df.loc[idx].copy()

    # Fetch funding history
    funding_records = _fetch_funding_rate_history_binance_usdm(
        futures_ex,
        symbol_raw=funding_symbol_raw,
        since_ms=since_ms,
        limit=1000,
    )
    funding_map = {r["datetime"]: float(r["rate"]) for r in funding_records}

    return spot_df, perp_df, funding_map


# ----------------------------
# Indicators
# ----------------------------
class SpreadATR(bt.Indicator):
    """
    ATR on spread = perp - spot.
    Approximates spread OHLC as:
      spread_high = perp.high - spot.high
      spread_low  = perp.low  - spot.low
      spread_close = perp.close - spot.close
    Wilder ATR smoothing.
    """
    lines = ("spread_close", "tr", "atr",)
    params = (("period", 14),)

    def __init__(self):
        self.addminperiod(self.p.period + 1)

    def next(self):
        spot = self.data0
        perp = self.data1

        spread_close = perp.close[0] - spot.close[0]
        spread_high = perp.high[0] - spot.high[0]
        spread_low = perp.low[0] - spot.low[0]

        prev_close = perp.close[-1] - spot.close[-1]

        tr = max(
            spread_high - spread_low,
            abs(spread_high - prev_close),
            abs(spread_low - prev_close),
        )

        self.lines.spread_close[0] = spread_close
        self.lines.tr[0] = tr

        if len(self) == self.p.period + 1:
            # seed ATR with simple average of TR
            tr_vals = [self.lines.tr[-i] for i in range(self.p.period)]
            self.lines.atr[0] = float(np.mean(tr_vals))
        else:
            prev_atr = self.lines.atr[-1]
            self.lines.atr[0] = (prev_atr * (self.p.period - 1) + tr) / self.p.period


# ----------------------------
# Strategy
# ----------------------------
class FundingRateArbStrategy(bt.Strategy):
    """
    Delta-neutral funding capture:
      - If funding rate >= enter_fr: Long Spot + Short Perp (receive funding)
      - If funding rate <= -enter_fr: Short Spot + Long Perp (receive funding) [optional symmetric]
    Risk control:
      - Position sizing based on spread ATR so that stop distance == stop_atr_mult * spread_ATR
      - Risk per trade = 2% of equity
    Exits:
      - Funding drops back toward 0 (<= exit_fr or >= -exit_fr)
      - Spread stop hit
      - Optional basis z-score filter
    """

    params = dict(
        risk_per_trade=0.02,
        enter_fr=0.00010,      # 0.01% per funding interval (8h) as a typical "meaningful" threshold
        exit_fr=0.00003,
        stop_atr_mult=3.0,
        atr_period=14,
        z_period=72,           # 72h rolling window for basis sanity filter
        z_entry_max=2.5,
        z_exit_max=3.5,
        max_leverage=2.0,      # cap notional vs equity (prevents unrealistic sizes)
        allow_negative_funding=True,  # capture both sides (may not be implementable IRL on spot short)
        funding_map=None,      # dict[datetime]->rate
        printlog=False,
    )

    def log(self, txt):
        if self.p.printlog:
            dt = self.data0.datetime.datetime(0)
            print(f"{dt.isoformat()} {txt}")

    def __init__(self):
        if self.p.funding_map is None:
            self.p.funding_map = {}

        self.spread_atr = SpreadATR(self.datas[0], self.datas[1], period=self.p.atr_period)
        self.spread = self.datas[1].close - self.datas[0].close
        self.spread_sma = bt.indicators.SMA(self.spread, period=self.p.z_period)
        self.spread_std = bt.indicators.StandardDeviation(self.spread, period=self.p.z_period)

        self.last_funding_dt = None

        # Trade tracking (pair-trade level)
        self.pair_open = False
        self.entry_value = None
        self.trade_count = 0
        self.win_count = 0

        # For stop management
        self.entry_spread = None
        self.side = 0  # +1 = long spot/short perp, -1 = short spot/long perp

    def _add_cash(self, amount):
        # backtrader broker method name differs across versions
        if hasattr(self.broker, "add_cash"):
            self.broker.add_cash(amount)
        elif hasattr(self.broker, "addcash"):
            self.broker.addcash(amount)
        else:
            # fallback: do nothing
            pass

    def _current_funding_rate(self):
        dt = self.data0.datetime.datetime(0)
        dt_key = dt.replace(minute=0, second=0, microsecond=0)
        return self.p.funding_map.get(dt_key, None), dt_key

    def _zscore(self):
        if self.spread_std[0] == 0 or np.isnan(self.spread_std[0]):
            return 0.0
        return float((self.spread[0] - self.spread_sma[0]) / self.spread_std[0])

    def _calc_size(self):
        equity = self.broker.getvalue()
        risk_cash = equity * self.p.risk_per_trade

        atr = float(self.spread_atr.atr[0])
        stop_dist = max(atr * self.p.stop_atr_mult, 1e-8)  # USD per BTC (spread move)

        size = risk_cash / stop_dist  # BTC size since PnL ≈ -Δspread * size (for side +1)

        # cap by notional leverage
        spot_px = float(self.datas[0].close[0])
        max_notional = equity * self.p.max_leverage
        size_cap = max_notional / max(spot_px, 1e-8)

        # cap by available cash for spot long (to keep it realistic)
        # Note: shorting spot would increase cash; we still cap conservatively.
        cash = self.broker.getcash()
        cash_cap = cash / max(spot_px, 1e-8)

        size = min(size, size_cap, cash_cap)
        return max(size, 0.0)

    def _open_pair(self, side):
        # side: +1 (long spot / short perp), -1 (short spot / long perp)
        size = self._calc_size()
        if size <= 0:
            return

        self.side = side
        self.entry_spread = float(self.spread[0])
        self.entry_value = self.broker.getvalue()
        self.pair_open = True

        if side == +1:
            self.buy(data=self.datas[0], size=size)   # long spot
            self.sell(data=self.datas[1], size=size)  # short perp
            self.log(f"OPEN +1 size={size:.4f} spread={self.entry_spread:.2f}")
        else:
            self.sell(data=self.datas[0], size=size)  # short spot
            self.buy(data=self.datas[1], size=size)   # long perp
            self.log(f"OPEN -1 size={size:.4f} spread={self.entry_spread:.2f}")

    def _close_pair(self, reason=""):
        if not self.pair_open:
            return

        self.close(data=self.datas[0])
        self.close(data=self.datas[1])

        # update trade stats on close signal (approx; executed next bar)
        # We will finalize in notify_order when both legs are closed.
        self.log(f"CLOSE signal reason={reason}")

    def notify_order(self, order):
        # We track completed closure by checking when both positions are flat after orders complete.
        if order.status in [order.Completed, order.Canceled, order.Rejected]:
            pos0 = self.getposition(self.datas[0]).size
            pos1 = self.getposition(self.datas[1]).size
            if self.pair_open and pos0 == 0 and pos1 == 0:
                # Pair fully closed
                exit_value = self.broker.getvalue()
                pnl = exit_value - (self.entry_value if self.entry_value is not None else exit_value)

                self.trade_count += 1
                if pnl > 0:
                    self.win_count += 1

                self.log(f"PAIR CLOSED pnl={pnl:.2f} trades={self.trade_count} wins={self.win_count}")

                self.pair_open = False
                self.entry_value = None
                self.entry_spread = None
                self.side = 0

    def next(self):
        # 1) Apply funding cashflow if there is a funding event at this hour
        fr, fr_dt = self._current_funding_rate()
        if fr is not None and fr_dt != self.last_funding_dt:
            self.last_funding_dt = fr_dt
            perp_pos = self.getposition(self.datas[1]).size
            if perp_pos != 0:
                perp_px = float(self.datas[1].close[0])
                # funding payment: longs pay when fr > 0, shorts receive when fr > 0
                # approximate: funding_pnl = -position * price * rate
                funding_pnl = -float(perp_pos) * perp_px * float(fr)
                self._add_cash(funding_pnl)
                self.log(f"FUNDING dt={fr_dt} rate={fr:.6f} perp_pos={perp_pos:.4f} pnl={funding_pnl:.2f}")

        # Need enough history for indicators
        if len(self) < max(self.p.z_period, self.p.atr_period) + 2:
            return

        z = self._zscore()

        # 2) If no open pair, look for entry
        if not self.pair_open:
            # basis sanity filter: avoid extremely dislocated spread
            if abs(z) > self.p.z_entry_max:
                return

            if fr is None:
                return

            # Enter +1: receive positive funding by shorting perp
            if fr >= self.p.enter_fr:
                self._open_pair(side=+1)
                return

            # Enter -1: receive negative funding by longing perp (optional)
            if self.p.allow_negative_funding and fr <= -self.p.enter_fr:
                self._open_pair(side=-1)
                return

            return

        # 3) Manage open pair: stop / exit conditions
        atr = float(self.spread_atr.atr[0])
        stop_dist = atr * self.p.stop_atr_mult
        curr_spread = float(self.spread[0])

        # stop based on adverse spread move
        if self.side == +1:
            # PnL ≈ -Δspread * size, so we lose when spread increases
            if curr_spread >= self.entry_spread + stop_dist:
                self._close_pair(reason="STOP_SPREAD_WIDEN")
                return
        elif self.side == -1:
            # lose when spread decreases
            if curr_spread <= self.entry_spread - stop_dist:
                self._close_pair(reason="STOP_SPREAD_NARROW")
                return

        # basis blowout safety exit
        if abs(z) > self.p.z_exit_max:
            self._close_pair(reason="BASIS_Z_BLOWOUT")
            return

        # funding exit: edge decays
        if fr is not None:
            if self.side == +1 and fr <= self.p.exit_fr:
                self._close_pair(reason="FUNDING_DECAY")
                return
            if self.side == -1 and fr >= -self.p.exit_fr:
                self._close_pair(reason="FUNDING_DECAY")
                return

    def stop(self):
        # expose win rate for reporting
        self.final_trade_count = self.trade_count
        self.final_win_count = self.win_count


# ----------------------------
# Run Backtest
# ----------------------------
def run():
    spot_df, perp_df, funding_map = fetch_data(days=180, timeframe="1h")

    cerebro = bt.Cerebro(stdstats=False)

    data_spot = bt.feeds.PandasData(dataname=spot_df)
    data_perp = bt.feeds.PandasData(dataname=perp_df)

    cerebro.adddata(data_spot, name="BTC_SPOT")
    cerebro.adddata(data_perp, name="BTC_PERP")

    # Broker
    initial_cash = 100_000.0
    cerebro.broker.setcash(initial_cash)

    # Commission (set conservative defaults; adjust to your tier)
    # Note: This is per-trade commission on notional. For maker/taker realism, extend with custom comminfo.
    fee_rate = 0.0004  # 0.04% typical taker-level placeholder
    cerebro.broker.setcommission(commission=fee_rate)

    # Analyzers
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    # Strategy
    cerebro.addstrategy(
        FundingRateArbStrategy,
        funding_map=funding_map,
        risk_per_trade=0.02,
        enter_fr=0.00010,
        exit_fr=0.00003,
        stop_atr_mult=3.0,
        atr_period=14,
        z_period=72,
        z_entry_max=2.5,
        z_exit_max=3.5,
        max_leverage=2.0,
        allow_negative_funding=True,
        printlog=False,
    )

    results = cerebro.run()
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    total_return = final_value / initial_cash - 1.0

    dd = strat.analyzers.dd.get_analysis()
    max_dd = dd["max"]["drawdown"] / 100.0  # fraction

    trades = getattr(strat, "final_trade_count", 0)
    wins = getattr(strat, "final_win_count", 0)
    win_rate = (wins / trades) if trades > 0 else float("nan")

    print("===== Backtest Report (Funding Rate Arb, BTC Spot + Perp) =====")
    print(f"Period Bars: {len(spot_df):,} (1h)")
    print(f"Initial Equity: {initial_cash:,.2f}")
    print(f"Final Equity:   {final_value:,.2f}")
    print(f"Total Return:   {total_return*100:,.2f}%")
    print(f"Max Drawdown:   {max_dd*100:,.2f}%")
    print(f"Trades:         {trades}")
    print(f"Win Rate:       {win_rate*100:,.2f}%" if not np.isnan(win_rate) else "Win Rate: N/A")


if __name__ == "__main__":
    run()
