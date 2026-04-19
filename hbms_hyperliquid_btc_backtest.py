import datetime as dt
import logging
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import yfinance as yf
from backtesting import Backtest, Strategy

try:
    # Prefer fractional backtesting for small accounts trading high-priced assets
    from backtesting.lib import FractionalBacktest as _FractionalBacktest
    BacktestClass = _FractionalBacktest
    USING_FRACTIONAL_BACKTEST = True
except ImportError:  # Fallback if FractionalBacktest is unavailable
    BacktestClass = Backtest
    USING_FRACTIONAL_BACKTEST = False


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def ema_indicator(series: pd.Series, period: int) -> np.ndarray:
    """
    Exponential Moving Average (EMA) implementation.
    """
    s = pd.Series(series)
    ema = s.ewm(span=period, adjust=False).mean()
    return ema.values


def sma_indicator(series: pd.Series, period: int) -> np.ndarray:
    """
    Simple Moving Average (SMA) implementation.
    """
    s = pd.Series(series)
    sma = s.rolling(window=period, min_periods=period).mean()
    return sma.values


def atr_indicator(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> np.ndarray:
    """
    Average True Range (ATR) implementation compatible with backtesting.I().
    """
    high = pd.Series(high)
    low = pd.Series(low)
    close = pd.Series(close)

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr.values


def download_btc_5m_history(symbol: str = "BTC-USD", period: str = "60d") -> pd.DataFrame:
    """
    Download 5-minute BTC history.

    NOTE: Yahoo Finance limits 5m data to approximately the last 60 days.
    To keep the script robust, we fetch the maximum allowed window (60d)
    rather than failing when requesting 6 months.
    """
    logging.info("Downloading %s 5m data for period=%s", symbol, period)
    data = yf.download(
        symbol,
        period=period,
        interval="5m",
        progress=False,
        auto_adjust=False,
        group_by="column",
    )

    if data.empty:
        raise RuntimeError("No data downloaded from yfinance.")

    # Normalize columns by position (Yahoo usually returns OHLCV in first 6 columns)
    # This avoids complications with MultiIndex structures.
    if data.shape[1] < 5:
        raise RuntimeError("Downloaded data does not contain enough OHLCV columns.")

    col_names = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    data = data.iloc[:, : len(col_names)]
    data.columns = col_names[: data.shape[1]]

    logging.info("Downloaded columns (normalized): %s", list(data.columns))

    data = data[~data.index.duplicated(keep="last")]
    data.sort_index(inplace=True)

    # Ensure timezone is UTC
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    else:
        data.index = data.index.tz_convert("UTC")

    # Keep only OHLCV for backtesting.py
    return data[["Open", "High", "Low", "Close", "Volume"]]


def add_daily_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Daily VWAP (reset at 00:00 UTC) column to 5m OHLCV data.
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty.")

    df = df.copy()

    # Group by UTC calendar day
    day_key = df.index.date
    vol = df["Volume"]
    pv = df["Close"] * df["Volume"]

    cum_vol = vol.groupby(day_key).cumsum()
    cum_pv = pv.groupby(day_key).cumsum()

    df["Daily_VWAP"] = cum_pv / cum_vol.replace(0, np.nan)

    return df


class HBMSHyperliquidBTCStrategy(Strategy):
    """
    Hyperliquid BTC Micro-Scalp (HBMS) Strategy for 5m BTC/USD.
    Implements:
    - Daily VWAP filter
    - EMA(9), EMA(21), ATR(14), Volume SMA(20)
    - Risk-based position sizing (3% of equity per trade)
    - Split entries into 2 partial positions (A and B)
    - Partial take profits and break-even stop adjustment
    """

    lot_step: float = 0.001
    risk_per_trade: float = 0.03
    slippage_frac: float = 0.0001  # 0.01% assumed slippage

    def init(self) -> None:
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume

        self.ema9 = self.I(ema_indicator, close, 9)
        self.ema21 = self.I(ema_indicator, close, 21)
        self.atr = self.I(atr_indicator, high, low, close, 14)
        self.vol_sma20 = self.I(sma_indicator, volume, 20)

        # Daily VWAP is pre-computed and provided as an extra column
        self.daily_vwap = self.data.Daily_VWAP

        # Track which TP1 trades have already triggered BE move
        self._processed_tp1_ids: set[int] = set()

    def _round_to_lot(self, size: float) -> float:
        if size <= 0:
            return 0.0
        return np.floor(size / self.lot_step) * self.lot_step

    def _handle_trailing_and_forced_exit(self) -> None:
        """
        - Move B-leg stop to break-even (+/- 0.05%) after A-leg TP hit.
        - Force close B-leg when price closes beyond EMA(21) against position.
        """
        # Break-even move when TP1 (A-leg) closes with profit
        for trade in self.closed_trades:
            trade_id = id(trade)
            if trade_id in self._processed_tp1_ids:
                continue

            if trade.tag == "L_A" and trade.pl > 0:
                self._processed_tp1_ids.add(trade_id)
                for open_trade in self.trades:
                    if open_trade.tag == "L_B" and open_trade.is_long:
                        be_sl = open_trade.entry_price * (1.0 + 0.0005)
                        if open_trade.sl is None or open_trade.sl < be_sl:
                            open_trade.sl = be_sl

            elif trade.tag == "S_A" and trade.pl > 0:
                self._processed_tp1_ids.add(trade_id)
                for open_trade in self.trades:
                    if open_trade.tag == "S_B" and open_trade.is_short:
                        be_sl = open_trade.entry_price * (1.0 - 0.0005)
                        if open_trade.sl is None or open_trade.sl > be_sl:
                            open_trade.sl = be_sl

        # Forced exit for B-leg when EMA(21) is broken against position
        ema21_now = float(self.ema21[-1])
        close_now = float(self.data.Close[-1])

        for trade in list(self.trades):
            if trade.tag == "L_B" and trade.is_long:
                if close_now < ema21_now:
                    trade.close()
            elif trade.tag == "S_B" and trade.is_short:
                if close_now > ema21_now:
                    trade.close()

    def _long_entry_conditions(self) -> bool:
        """
        Long setup:
        1. Close > Daily VWAP
        2. EMA9 > EMA21
        3. Volume spike: Volume > 1.5 * Volume SMA(20)
        4. Pullback: previous candle low within value area between EMA9 and EMA21
        5. Trigger: current close breaks above previous candle high
        """
        # Need at least 3 candles history for previous-high logic
        if len(self.data.Close) < 25:
            return False

        close_now = float(self.data.Close[-1])
        high_prev = float(self.data.High[-2])
        low_prev = float(self.data.Low[-2])

        ema9_now = float(self.ema9[-1])
        ema21_now = float(self.ema21[-1])
        ema9_prev = float(self.ema9[-2])
        ema21_prev = float(self.ema21[-2])

        vol_now = float(self.data.Volume[-1])
        vol_sma20_now = float(self.vol_sma20[-1])
        vwap_now = float(self.daily_vwap[-1])

        if any(
            np.isnan(x)
            for x in [
                close_now,
                high_prev,
                low_prev,
                ema9_now,
                ema21_now,
                ema9_prev,
                ema21_prev,
                vol_now,
                vol_sma20_now,
                vwap_now,
            ]
        ):
            return False

        env_ok = close_now > vwap_now
        mom_ok = ema9_now > ema21_now
        vol_ok = vol_now > 1.5 * vol_sma20_now

        ema_min_prev = min(ema9_prev, ema21_prev)
        ema_max_prev = max(ema9_prev, ema21_prev)
        pullback_ok = ema_min_prev <= low_prev <= ema_max_prev

        trigger_ok = close_now > high_prev

        return env_ok and mom_ok and vol_ok and pullback_ok and trigger_ok

    def _short_entry_conditions(self) -> bool:
        """
        Short setup (symmetric to long):
        1. Close < Daily VWAP
        2. EMA9 < EMA21
        3. Volume spike: Volume > 1.5 * Volume SMA(20)
        4. Pullback: previous candle high within value area between EMA9 and EMA21
        5. Trigger: current close breaks below previous candle low
        """
        if len(self.data.Close) < 25:
            return False

        close_now = float(self.data.Close[-1])
        low_prev = float(self.data.Low[-2])
        high_prev = float(self.data.High[-2])

        ema9_now = float(self.ema9[-1])
        ema21_now = float(self.ema21[-1])
        ema9_prev = float(self.ema9[-2])
        ema21_prev = float(self.ema21[-2])

        vol_now = float(self.data.Volume[-1])
        vol_sma20_now = float(self.vol_sma20[-1])
        vwap_now = float(self.daily_vwap[-1])

        if any(
            np.isnan(x)
            for x in [
                close_now,
                low_prev,
                high_prev,
                ema9_now,
                ema21_now,
                ema9_prev,
                ema21_prev,
                vol_now,
                vol_sma20_now,
                vwap_now,
            ]
        ):
            return False

        env_ok = close_now < vwap_now
        mom_ok = ema9_now < ema21_now
        vol_ok = vol_now > 1.5 * vol_sma20_now

        ema_min_prev = min(ema9_prev, ema21_prev)
        ema_max_prev = max(ema9_prev, ema21_prev)
        pullback_ok = ema_min_prev <= high_prev <= ema_max_prev

        trigger_ok = close_now < low_prev

        return env_ok and mom_ok and vol_ok and pullback_ok and trigger_ok

    def _enter_with_risk_positioning(self, direction: str) -> None:
        """
        Enter trade with risk-based position sizing.
        direction: "long" or "short"
        """
        atr_now = float(self.atr[-1])
        price_now = float(self.data.Close[-1])
        if np.isnan(atr_now) or np.isnan(price_now):
            return

        if atr_now <= 0:
            return

        # Initial SL distance based on ATR(14) * 1.5
        sl_distance = atr_now * 1.5

        # Effective risk per unit includes price slippage component
        effective_risk_per_unit = sl_distance + price_now * self.slippage_frac

        equity = float(self.equity)
        risk_capital = equity * self.risk_per_trade
        if risk_capital <= 0:
            return

        if USING_FRACTIONAL_BACKTEST:
            # FractionalBacktest: size is fraction of equity (0 < size < 1)
            size_fraction = 0.03 * price_now / effective_risk_per_unit
            size_fraction = float(min(max(size_fraction, 0.0), 1.0))

            if size_fraction <= 0.0:
                return

            half_size = size_fraction / 2.0
            if half_size <= 0.0:
                return
        else:
            # Classic Backtest: size is number of units (BTC)
            total_size = risk_capital / effective_risk_per_unit
            total_size = self._round_to_lot(total_size)

            # Need at least 2 * lot_step to split into A/B
            if total_size < 2 * self.lot_step:
                return

            half_size = total_size / 2.0

        if direction == "long":
            entry_price = price_now
            sl_price = entry_price - sl_distance
            r = entry_price - sl_price
            tp1 = entry_price + 1.0 * r
            tp2 = entry_price + 3.0 * r

            self.buy(size=half_size, sl=sl_price, tp=tp1, tag="L_A")
            self.buy(size=half_size, sl=sl_price, tp=tp2, tag="L_B")

        elif direction == "short":
            entry_price = price_now
            sl_price = entry_price + sl_distance
            r = sl_price - entry_price
            tp1 = entry_price - 1.0 * r
            tp2 = entry_price - 3.0 * r

            self.sell(size=half_size, sl=sl_price, tp=tp1, tag="S_A")
            self.sell(size=half_size, sl=sl_price, tp=tp2, tag="S_B")

    def next(self) -> None:
        # First, manage open trades (move to BE, forced EMA21 exit)
        self._handle_trailing_and_forced_exit()

        # Only open new positions when flat (simplifies risk accounting)
        if self.position:
            return

        # Long setup
        if self._long_entry_conditions():
            self._enter_with_risk_positioning(direction="long")
            return

        # Short setup (symmetric)
        if self._short_entry_conditions():
            self._enter_with_risk_positioning(direction="short")


def run_backtest() -> pd.Series:
    data = download_btc_5m_history(symbol="BTC-USD", period="60d")
    data = add_daily_vwap(data)

    bt = BacktestClass(
        data,
        HBMSHyperliquidBTCStrategy,
        cash=100.0,
        commission=0.00035,  # 0.035% taker fee
        margin=0.05,  # up to 20x leverage
        trade_on_close=False,
        exclusive_orders=False,
    )

    stats = bt.run()
    logging.info("Backtest completed.")
    print(stats)

    # Open HTML report in browser
    bt.plot(open_browser=True)

    return stats


def main() -> None:
    try:
        stats = run_backtest()
    except Exception as exc:
        logging.exception("Backtest execution failed: %s", exc)
        sys.exit(1)

    # Extract key metrics for easier inspection
    metrics = ["Return [%]", "Max. Drawdown [%]", "Sharpe Ratio"]
    available_metrics = [m for m in metrics if m in stats.index]

    if available_metrics:
        logging.info("Key metrics:")
        for m in available_metrics:
            logging.info("%s: %s", m, stats[m])


if __name__ == "__main__":
    main()

