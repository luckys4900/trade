import logging
import sys
from typing import Tuple

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


def sma_indicator(series: pd.Series, period: int) -> np.ndarray:
    s = pd.Series(series)
    return s.rolling(window=period, min_periods=period).mean().values


def bollinger_bands(
    series: pd.Series, period: int = 20, std_mult: float = 2.5
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    s = pd.Series(series)
    mid = s.rolling(window=period, min_periods=period).mean()
    std = s.rolling(window=period, min_periods=period).std(ddof=0)
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return mid.values, upper.values, lower.values


def rsi_indicator(series: pd.Series, period: int = 3) -> np.ndarray:
    s = pd.Series(series)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.values


def download_btc_5m_history(symbol: str = "BTC-USD", period: str = "60d") -> pd.DataFrame:
    """
    Download 5-minute BTC history.

    Yahoo Finance limits 5m data to roughly the last 60 days.
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

    return data[["Open", "High", "Low", "Close", "Volume"]]


class CLSMRLiqSweepStrategy(Strategy):
    """
    CLS-MR: Liquidation Sweep & Mean Reversion strategy for BTC 5m.

    - Panic detection via Bollinger Band (20, 2.5σ) and RSI(3)
    - Trend filter via SMA(200)
    - Risk-based sizing (3% of equity per trade), split into A/B legs
    - FractionalBacktest support for small accounts
    """

    risk_per_trade: float = 0.03
    slippage_frac: float = 0.0001  # 0.01% slippage assumption
    fee_frac: float = 0.00035  # 0.035% taker fee
    be_offset_frac: float = 0.0005  # Break-even offset to cover costs

    def init(self) -> None:
        close = self.data.Close

        # Indicators
        self.sma200 = self.I(sma_indicator, close, 200)
        self.bb_mid, self.bb_upper, self.bb_lower = self.I(
            bollinger_bands, close, 20, 2.5
        )
        self.rsi3 = self.I(rsi_indicator, close, 3)

        # Long setup state
        self.long_setup_active: bool = False
        self.long_setup_index: int = -1
        self.long_setup_high: float = np.nan
        self.long_setup_low: float = np.nan

        # Short setup state (symmetric; may be disabled by user if only long wanted)
        self.short_setup_active: bool = False
        self.short_setup_index: int = -1
        self.short_setup_high: float = np.nan
        self.short_setup_low: float = np.nan

        # Track processed TP1 legs to move B-leg stops
        self._processed_tp1_ids: set[int] = set()

    # ========= Utility =========

    def _long_trend_ok(self) -> bool:
        sma = float(self.sma200[-1])
        close = float(self.data.Close[-1])
        if np.isnan(sma) or np.isnan(close):
            return False
        return close > sma

    def _short_trend_ok(self) -> bool:
        sma = float(self.sma200[-1])
        close = float(self.data.Close[-1])
        if np.isnan(sma) or np.isnan(close):
            return False
        return close < sma

    # ========= Setup Detection =========

    def _detect_long_panic_setup(self) -> None:
        """Detect long-side panic setup candle."""
        if not self._long_trend_ok():
            return

        close = float(self.data.Close[-1])
        lower = float(self.bb_lower[-1])
        rsi = float(self.rsi3[-1])

        if any(np.isnan(x) for x in [close, lower, rsi]):
            return

        if close < lower and rsi <= 15:
            # Record panic candle
            self.long_setup_active = True
            self.long_setup_index = len(self.data.Close) - 1
            self.long_setup_high = float(self.data.High[-1])
            self.long_setup_low = float(self.data.Low[-1])

    def _detect_short_panic_setup(self) -> None:
        """Detect short-side panic setup candle (symmetric)."""
        if not self._short_trend_ok():
            return

        close = float(self.data.Close[-1])
        upper = float(self.bb_upper[-1])
        rsi = float(self.rsi3[-1])

        if any(np.isnan(x) for x in [close, upper, rsi]):
            return

        if close > upper and rsi >= 85:
            self.short_setup_active = True
            self.short_setup_index = len(self.data.Close) - 1
            self.short_setup_high = float(self.data.High[-1])
            self.short_setup_low = float(self.data.Low[-1])

    # ========= Entry Execution =========

    def _enter_long_from_setup(self) -> None:
        if not self.long_setup_active:
            return

        # Time window: within 5 bars after setup
        age = (len(self.data.Close) - 1) - self.long_setup_index
        if age <= 0 or age > 5:
            return

        close = float(self.data.Close[-1])
        setup_high = float(self.long_setup_high)
        setup_low = float(self.long_setup_low)

        if any(np.isnan(x) for x in [close, setup_high, setup_low]):
            return

        # Trigger: current close breaks above setup high
        if close <= setup_high:
            return

        # Approximate entry at next bar open by sending order now
        entry_price = close
        sl_price = setup_low - entry_price * 0.0005
        sl_distance = entry_price - sl_price
        if sl_distance <= 0:
            return

        # 1R
        r = sl_distance
        tp1_price = entry_price + 1.5 * r

        equity = float(self.equity)
        if equity <= 0:
            return

        # Include slippage in effective risk per unit
        denom = sl_distance + entry_price * self.slippage_frac
        if denom <= 0:
            return

        if USING_FRACTIONAL_BACKTEST:
            # size is fraction of equity (0..1)
            size_fraction = self.risk_per_trade * entry_price / denom
            size_fraction = float(min(max(size_fraction, 0.0), 1.0))
            if size_fraction <= 0.0:
                return
            half_size = size_fraction / 2.0
        else:
            # size is number of BTC units
            risk_capital = equity * self.risk_per_trade
            total_units = risk_capital / denom
            if total_units <= 0:
                return
            half_size = total_units / 2.0

        if half_size <= 0:
            return

        # Leg A: TP1, Leg B: no static TP (managed by mean-reversion exit)
        self.buy(size=half_size, sl=sl_price, tp=tp1_price, tag="L_A")
        self.buy(size=half_size, sl=sl_price, tag="L_B")

        # Reset setup after entry
        self.long_setup_active = False

    def _enter_short_from_setup(self) -> None:
        if not self.short_setup_active:
            return

        age = (len(self.data.Close) - 1) - self.short_setup_index
        if age <= 0 or age > 5:
            return

        close = float(self.data.Close[-1])
        setup_low = float(self.short_setup_low)
        setup_high = float(self.short_setup_high)

        if any(np.isnan(x) for x in [close, setup_low, setup_high]):
            return

        # Trigger: current close breaks below setup low
        if close >= setup_low:
            return

        entry_price = close
        sl_price = setup_high + entry_price * 0.0005
        sl_distance = sl_price - entry_price
        if sl_distance <= 0:
            return

        r = sl_distance
        tp1_price = entry_price - 1.5 * r

        equity = float(self.equity)
        if equity <= 0:
            return

        denom = sl_distance + entry_price * self.slippage_frac
        if denom <= 0:
            return

        if USING_FRACTIONAL_BACKTEST:
            size_fraction = self.risk_per_trade * entry_price / denom
            size_fraction = float(min(max(size_fraction, 0.0), 1.0))
            if size_fraction <= 0.0:
                return
            half_size = size_fraction / 2.0
        else:
            risk_capital = equity * self.risk_per_trade
            total_units = risk_capital / denom
            if total_units <= 0:
                return
            half_size = total_units / 2.0

        if half_size <= 0:
            return

        self.sell(size=half_size, sl=sl_price, tp=tp1_price, tag="S_A")
        self.sell(size=half_size, sl=sl_price, tag="S_B")

        self.short_setup_active = False

    # ========= Trade Management =========

    def _manage_be_and_tp2(self) -> None:
        """
        - When A-leg hits TP1 with profit, move B-leg SL to BE+cost.
        - TP2: when price mean-reverts to BB mid (cross with candle body).
        """
        # Move SL of B-leg to BE when A-leg closes in profit
        for trade in self.closed_trades:
            trade_id = id(trade)
            if trade_id in self._processed_tp1_ids:
                continue

            if trade.tag == "L_A" and trade.pl > 0:
                self._processed_tp1_ids.add(trade_id)
                for open_trade in self.trades:
                    if open_trade.tag == "L_B" and open_trade.is_long:
                        be_sl = open_trade.entry_price * (1.0 + self.be_offset_frac)
                        if open_trade.sl is None or open_trade.sl < be_sl:
                            open_trade.sl = be_sl

            elif trade.tag == "S_A" and trade.pl > 0:
                self._processed_tp1_ids.add(trade_id)
                for open_trade in self.trades:
                    if open_trade.tag == "S_B" and open_trade.is_short:
                        be_sl = open_trade.entry_price * (1.0 - self.be_offset_frac)
                        if open_trade.sl is None or open_trade.sl > be_sl:
                            open_trade.sl = be_sl

        # TP2: mean reversion to BB mid
        if len(self.data.Close) < 2:
            return

        close_now = float(self.data.Close[-1])
        close_prev = float(self.data.Close[-2])
        mid_now = float(self.bb_mid[-1])
        mid_prev = float(self.bb_mid[-2])

        if any(np.isnan(x) for x in [close_now, close_prev, mid_now, mid_prev]):
            return

        for trade in list(self.trades):
            if trade.tag == "L_B" and trade.is_long:
                # Body crosses above mid-band
                if close_prev <= mid_prev and close_now > mid_now:
                    trade.close()
            elif trade.tag == "S_B" and trade.is_short:
                # Body crosses below mid-band
                if close_prev >= mid_prev and close_now < mid_now:
                    trade.close()

    # ========= Main Step =========

    def next(self) -> None:
        # Manage open trades first (BE move and TP2 logic)
        self._manage_be_and_tp2()

        # Age-out setups older than 5 bars
        current_index = len(self.data.Close) - 1
        if self.long_setup_active and current_index - self.long_setup_index > 5:
            self.long_setup_active = False
        if self.short_setup_active and current_index - self.short_setup_index > 5:
            self.short_setup_active = False

        # Only open new setups/entries when flat (one position at a time)
        if not self.position:
            # Detect panic setups
            self._detect_long_panic_setup()
            self._detect_short_panic_setup()

            # Attempt entries from active setups
            self._enter_long_from_setup()
            self._enter_short_from_setup()


def run_backtest() -> pd.Series:
    data = download_btc_5m_history(symbol="BTC-USD", period="60d")

    bt = BacktestClass(
        data,
        CLSMRLiqSweepStrategy,
        cash=100.0,
        commission=0.00035,  # 0.035% taker fee
        margin=0.05,  # up to 20x leverage
        trade_on_close=False,
        exclusive_orders=False,
    )

    stats = bt.run()
    logging.info("Backtest completed.")
    print(stats)

    # Plot to HTML and open in browser
    bt.plot(open_browser=True)

    return stats


def main() -> None:
    try:
        stats = run_backtest()
    except Exception as exc:
        logging.exception("Backtest execution failed: %s", exc)
        sys.exit(1)

    metrics = ["Return [%]", "Max. Drawdown [%]", "Sharpe Ratio"]
    available = [m for m in metrics if m in stats.index]
    if available:
        logging.info("Key metrics:")
        for m in available:
            logging.info("%s: %s", m, stats[m])


if __name__ == "__main__":
    main()

