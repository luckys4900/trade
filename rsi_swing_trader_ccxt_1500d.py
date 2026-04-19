#!/usr/bin/env python3
# Required installs:
#   pip install ccxt pandas numpy backtesting

import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import ccxt
from backtesting import Backtest, Strategy

try:
    # Prefer fractional backtesting when available
    from backtesting.lib import FractionalBacktest as _FractionalBacktest

    BacktestClass = _FractionalBacktest
    USING_FRACTIONAL = True
except ImportError:
    BacktestClass = Backtest
    USING_FRACTIONAL = False


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# =============================================================================
# INDICATORS
# =============================================================================

def ema_ind(series: pd.Series, period: int) -> np.ndarray:
    s = pd.Series(series)
    return s.ewm(span=period, adjust=False).mean().values


def rsi_ind(series: pd.Series, period: int = 14) -> np.ndarray:
    """Wilder-style RSI."""
    s = pd.Series(series)
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).values


def atr_ind(high: pd.Series, low: pd.Series, close: pd.Series,
            period: int = 14) -> np.ndarray:
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    prev_c = c.shift(1)
    tr = pd.concat(
        [
            h - l,
            (h - prev_c).abs(),
            (l - prev_c).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    return atr.values


# =============================================================================
# DATA FETCHING (Binance via ccxt, with CSV cache)
# =============================================================================

def fetch_binance_ohlcv_ccxt(
    symbol: str = "BTC/USDT",
    timeframe: str = "4h",
    days: int = 1500,
    csv_path: Path = Path("btc_usdt_4h_1500d.csv"),
    limit_per_call: int = 1000,
) -> pd.DataFrame:
    """
    Fetch OHLCV from Binance via ccxt with pagination and local CSV cache.

    - If `csv_path` exists, load from CSV (no API calls).
    - Otherwise:
        * Use ccxt.binance() public API
        * Page through history using `since` + `limit`
        * Stop when reaching desired period or latest candle
        * Save to CSV for future runs
    """
    if csv_path.exists():
        logging.info("Loading cached OHLCV from %s", csv_path)
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df

    logging.info(
        "No cache found. Fetching %s %s data for last %d days from Binance...",
        symbol,
        timeframe,
        days,
    )

    exchange = ccxt.binance({"enableRateLimit": True})

    # Start time (UTC now - days)
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(since_dt.timestamp() * 1000)

    all_ohlcv = []
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    next_since = since_ms

    while True:
        logging.info(
            "Requesting OHLCV: symbol=%s timeframe=%s since=%s",
            symbol,
            timeframe,
            datetime.fromtimestamp(next_since / 1000, tz=timezone.utc).isoformat(),
        )
        ohlcv = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=next_since,
            limit=limit_per_call,
        )
        if not ohlcv:
            logging.info("No more data returned from exchange. Stopping pagination.")
            break

        all_ohlcv.extend(ohlcv)
        last_ts = ohlcv[-1][0]
        next_since = last_ts + timeframe_ms

        # Stop when we are close to the latest candles
        if datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc) >= datetime.now(
            timezone.utc
        ) - timedelta(hours=4):
            logging.info("Reached latest candles. Stopping.")
            break

        # Be gentle with the API
        exchange.sleep(200)

    if not all_ohlcv:
        raise RuntimeError("No OHLCV data fetched from Binance.")

    df = pd.DataFrame(
        all_ohlcv,
        columns=["timestamp", "Open", "High", "Low", "Close", "Volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)

    logging.info("Fetched %d %s candles from Binance", len(df), timeframe)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path)
    logging.info("Cached OHLCV to %s", csv_path)

    return df


# =============================================================================
# STRATEGY (RSI Swing v6 相当)
# =============================================================================

class RSIMomentumSwingBinance(Strategy):
    """
    RSI Momentum Swing strategy on 4H BTC/USDT from Binance.

    Long:
      - RSI(10) falls below 30, then crosses back above 30
      - Close > EMA(50)

    Short:
      - RSI(10) rises above 70, then crosses back below 70
      - Close < EMA(50)

    Risk:
      - Risk per trade: 3% of current equity
      - SL = entry - 2.5 * ATR(14)  (long), entry + 2.5 * ATR(14) (short)
      - TP = entry + 4.0 * ATR(14)  (long), entry - 4.0 * ATR(14) (short)
      - Time stop: max_bars (4H bars)
    """

    rsi_period: int = 10
    rsi_os: float = 30.0
    rsi_ob: float = 70.0
    ema_period: int = 50
    atr_period: int = 14
    sl_atr_mult: float = 2.5
    tp_atr_mult: float = 4.0
    risk_per_trade: float = 0.03
    max_bars: int = 20  # 20 * 4H = 80 hours

    def init(self) -> None:
        close = self.data.Close
        high = self.data.High
        low = self.data.Low

        self.rsi = self.I(rsi_ind, close, self.rsi_period)
        self.ema = self.I(ema_ind, close, self.ema_period)
        self.atr = self.I(atr_ind, high, low, close, self.atr_period)

        self._entry_bar: Optional[int] = None

    def next(self) -> None:
        # Time-based exit
        if self.position:
            if self._entry_bar is not None:
                bars_held = len(self.data.Close) - self._entry_bar
                if bars_held >= self.max_bars:
                    self.position.close()
                    self._entry_bar = None
                    return
            return

        if len(self.data.Close) < max(self.rsi_period, self.ema_period, self.atr_period) + 3:
            return

        rsi_now = float(self.rsi[-1])
        rsi_prev = float(self.rsi[-2])
        price = float(self.data.Close[-1])
        ema_now = float(self.ema[-1])
        atr_now = float(self.atr[-1])

        if any(np.isnan(x) for x in [rsi_now, rsi_prev, price, ema_now, atr_now]):
            return
        if atr_now <= 0 or price <= 0:
            return

        # Long signal
        long_rsi = (rsi_prev <= self.rsi_os) and (rsi_now > self.rsi_os)
        long_trend = price > ema_now

        # Short signal
        short_rsi = (rsi_prev >= self.rsi_ob) and (rsi_now < self.rsi_ob)
        short_trend = price < ema_now

        if long_rsi and long_trend:
            self._enter_trade("long", price, atr_now)
        elif short_rsi and short_trend:
            self._enter_trade("short", price, atr_now)

    def _enter_trade(self, direction: str, price: float, atr_now: float) -> None:
        equity = float(self.equity)
        if equity <= 0 or atr_now <= 0:
            return

        sl_dist = atr_now * self.sl_atr_mult
        tp_dist = atr_now * self.tp_atr_mult

        if USING_FRACTIONAL:
            # size is fraction of equity (0..1)
            size = self.risk_per_trade * price / sl_dist
            size = float(min(max(size, 0.0), 1.0))
            if size <= 0.0:
                return
        else:
            # size is number of BTC units
            risk_capital = equity * self.risk_per_trade
            units = risk_capital / sl_dist
            max_units = (equity * 0.95) / price
            units = float(min(units, max_units))
            if units <= 0.0:
                return
            size = units

        if direction == "long":
            sl = price - sl_dist
            tp = price + tp_dist
            self.buy(size=size, sl=sl, tp=tp)
        else:
            sl = price + sl_dist
            tp = price - tp_dist
            self.sell(size=size, sl=sl, tp=tp)

        self._entry_bar = len(self.data.Close)


# =============================================================================
# BACKTEST RUNNER
# =============================================================================

def run_backtest() -> None:
    csv_path = Path("btc_usdt_4h_1500d.csv")
    data = fetch_binance_ohlcv_ccxt(
        symbol="BTC/USDT",
        timeframe="4h",
        days=1500,
        csv_path=csv_path,
    )

    logging.info(
        "Backtest data: %d bars | %s → %s",
        len(data),
        data.index[0],
        data.index[-1],
    )

    bt = BacktestClass(
        data,
        RSIMomentumSwingBinance,
        cash=10_000.0,
        commission=0.00035,  # 0.035% taker fee
        margin=0.05,         # up to 20x leverage
        trade_on_close=False,
        exclusive_orders=False,
    )

    stats = bt.run()
    print("\n" + "=" * 75)
    print("  RSI Momentum Swing Trader v6.0 - 1500d Backtest (Binance BTC/USDT 4h)")
    print("=" * 75)
    for key in [
        "Start",
        "End",
        "Duration",
        "Exposure Time [%]",
        "Equity Final [$]",
        "Equity Peak [$]",
        "Return [%]",
        "Buy & Hold Return [%]",
        "Sharpe Ratio",
        "Sortino Ratio",
        "Calmar Ratio",
        "Max. Drawdown [%]",
        "Avg. Drawdown [%]",
        "# Trades",
        "Win Rate [%]",
        "Best Trade [%]",
        "Worst Trade [%]",
        "Avg. Trade [%]",
        "Profit Factor",
        "Expectancy [%]",
        "SQN",
    ]:
        if key in stats.index:
            print(f"  {key:<30s}: {stats[key]}")

    print("=" * 75)

    # Open interactive chart in a browser
    bt.plot(open_browser=True)


def main() -> None:
    try:
        run_backtest()
    except Exception as exc:
        logging.exception("Backtest failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

