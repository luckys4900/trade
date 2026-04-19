#!/usr/bin/env python3
"""
================================================================================
  Institutional VWAP Confluence Scalper v3.0
  ---------------------------------------------------------------------------
  Architecture: VWAP Bias + 3-EMA Trend + ADX Regime + Volume Confirmation
  Timeframe   : 5-minute BTC/USD
  Edge Source : Institutional order flow alignment (VWAP) + trend pullback

  Key differences from HBMS v1 (which lost -91%):
  1. MAX 3 TRADES PER DAY (v1 had 384 trades in 60 days = overtrading death)
  2. REGIME FILTER via ADX (no trading in chop / ADX < 20)
  3. TREND-FOLLOWING ONLY (no counter-trend = no catching falling knives)
  4. R:R minimum 1:2 enforced via ATR
  5. Session filter: London-NY overlap only (highest liquidity)
  6. Single position (no split A/B complexity that dilutes edge)
  7. Risk per trade: 1% (not 3%)
================================================================================
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from backtesting import Backtest, Strategy

try:
    # Use fractional backtesting when available for small notional accounts
    from backtesting.lib import FractionalBacktest as _FractionalBacktest

    BacktestClass = _FractionalBacktest
    FRACTIONAL = True
except ImportError:
    BacktestClass = Backtest
    FRACTIONAL = False


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# =============================================================================
# INDICATOR FUNCTIONS (backtesting.py compatible)
# =============================================================================

def ema(series, period):
    return pd.Series(series).ewm(span=period, adjust=False).mean().values


def sma(series, period):
    return pd.Series(series).rolling(window=period, min_periods=period).mean().values


def atr_calc(high, low, close, period=14):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean().values


def adx_calc(high, low, close, period=14):
    """Wilder's ADX implementation."""
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)

    plus_dm = (h - h.shift(1)).clip(lower=0)
    minus_dm = (l.shift(1) - l).clip(lower=0)
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0

    atr_smooth = tr.ewm(span=period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(span=period, min_periods=period).mean() / atr_smooth
    minus_di = 100 * minus_dm.ewm(span=period, min_periods=period).mean() / atr_smooth

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(span=period, min_periods=period).mean()
    return adx.values


def rsi_calc(series, period=14):
    s = pd.Series(series)
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).values


# =============================================================================
# DATA DOWNLOAD
# =============================================================================

def download_data(symbol="BTC-USD", period="60d"):
    logging.info("Downloading %s 5m data (period=%s)...", symbol, period)
    try:
        data = yf.download(
            symbol,
            period=period,
            interval="5m",
            progress=False,
            auto_adjust=False,
            group_by="column",
        )
        if data.empty:
            raise RuntimeError("Empty data")

        col_names = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
        data = data.iloc[:, : len(col_names)]
        data.columns = col_names[: data.shape[1]]
        data = data[~data.index.duplicated(keep="last")]
        data.sort_index(inplace=True)

        if data.index.tz is None:
            data.index = data.index.tz_localize("UTC")
        else:
            data.index = data.index.tz_convert("UTC")
        logging.info("Downloaded %d bars from yfinance", len(data))
    except Exception as e:
        logging.warning("yfinance unavailable (%s), generating synthetic BTC data", e)
        data = _generate_realistic_btc(days=60)

    # Add Daily VWAP
    day_key = data.index.date
    cum_vol = data["Volume"].groupby(day_key).cumsum()
    cum_pv = (data["Close"] * data["Volume"]).groupby(day_key).cumsum()
    data["Daily_VWAP"] = cum_pv / cum_vol.replace(0, np.nan)

    # Add hour column for session filtering
    data["Hour"] = data.index.hour

    return data[["Open", "High", "Low", "Close", "Volume", "Daily_VWAP", "Hour"]]


def _generate_realistic_btc(days=60):
    """
    Generate synthetic BTC/USD 5-minute data with realistic properties:
    - Regime switching (trending / ranging / volatile)
    - Intraday volume profile (high during London-NY overlap)
    - Fat-tailed returns
    - Trend persistence (momentum)
    - Mean reversion at extremes
    """
    from datetime import datetime, timezone

    np.random.seed(42)

    n_bars = days * 24 * 12  # 288 bars per day at 5min
    start = datetime(2025, 1, 4, tzinfo=timezone.utc)
    timestamps = pd.date_range(start, periods=n_bars, freq="5min", tz="UTC")
    hours = np.array([t.hour for t in timestamps])

    # --- Regime model ---
    # 0=ranging, 1=uptrend, 2=downtrend
    regime = np.zeros(n_bars, dtype=int)
    current_regime = 0
    regime_duration = 0
    for i in range(n_bars):
        regime_duration += 1
        # Average regime lasts ~200 bars (~17 hours)
        if regime_duration > 100 and np.random.random() < 0.01:
            current_regime = np.random.choice([0, 1, 2], p=[0.4, 0.35, 0.25])
            regime_duration = 0
        regime[i] = current_regime

    # --- Price generation with momentum ---
    base_price = 95000.0
    close = np.zeros(n_bars)
    close[0] = base_price
    momentum = 0.0

    for i in range(1, n_bars):
        r = regime[i]
        h = hours[i]

        # Time-varying volatility
        if 13 <= h < 21:  # London PM + NY
            vol = 0.0018
        elif 7 <= h < 13:  # London AM
            vol = 0.0012
        else:  # Asia
            vol = 0.0008

        # Regime-dependent drift
        if r == 1:  # uptrend
            drift = 0.00015
            vol *= 1.2
        elif r == 2:  # downtrend
            drift = -0.00012
            vol *= 1.3
        else:  # ranging
            drift = 0.0
            # Mean reversion in range
            deviation = (close[i - 1] - base_price) / base_price
            drift -= deviation * 0.001

        # Momentum (autocorrelation of returns)
        noise = np.random.standard_t(df=5) * vol  # fat tails
        momentum = 0.3 * momentum + 0.7 * noise
        ret = drift + momentum

        # Occasional spikes
        if np.random.random() < 0.003:
            ret += np.random.choice([-1, 1]) * np.random.uniform(0.005, 0.015)

        close[i] = close[i - 1] * (1 + ret)

        # Slow base price adjustment
        if i % 1000 == 0:
            base_price = close[i]

    # --- OHLCV construction ---
    opens = np.roll(close, 1)
    opens[0] = close[0]

    # Intrabar range proportional to volatility
    intra_noise = np.abs(np.random.randn(n_bars)) * 0.001
    # Higher range during active sessions
    session_mult = np.where(
        (hours >= 13) & (hours < 21),
        1.5,
        np.where((hours >= 7) & (hours < 13), 1.2, 0.8),
    )
    intra_noise *= session_mult

    highs = np.maximum(opens, close) * (1 + intra_noise)
    lows = np.minimum(opens, close) * (1 - intra_noise)

    # --- Volume with intraday profile ---
    base_vol = np.random.lognormal(mean=10, sigma=0.6, size=n_bars)
    # London-NY overlap: 2-3x volume
    ny_mask = (hours >= 13) & (hours < 21)
    london_mask = (hours >= 7) & (hours < 13)
    base_vol[ny_mask] *= np.random.uniform(2.0, 3.5, size=ny_mask.sum())
    base_vol[london_mask] *= np.random.uniform(1.3, 2.0, size=london_mask.sum())

    # Volume spikes at price moves
    abs_rets = np.abs(np.diff(close, prepend=close[0]) / close)
    spike_mask = abs_rets > 0.003
    base_vol[spike_mask] *= np.random.uniform(2.5, 5.0, size=spike_mask.sum())

    df = pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": close, "Volume": base_vol},
        index=timestamps,
    )
    df.index.name = "timestamp"

    logging.info("Generated %d synthetic BTC bars (60 days, 5min)", n_bars)
    return df


# =============================================================================
# STRATEGY
# =============================================================================


class VWAPConfluenceScalper(Strategy):
    """
    Institutional VWAP Confluence Scalper

    ENTRY LOGIC (Long example - Short is symmetric):
    1. REGIME: ADX(14) >= 20 (trending market, not chop)
    2. BIAS  : Close > Daily VWAP (institutional buyers in control)
    3. TREND : EMA(9) > EMA(21) > EMA(50) (aligned momentum)
    4. PULLBACK: Low touches EMA(21) zone (mean reversion within trend)
    5. TRIGGER: Close > previous candle High (momentum resumption)
    6. VOLUME: Current volume > 1.2x SMA(20) volume
    7. RSI: 40 < RSI(14) < 70 (not overbought, has room to run)
    8. SESSION: UTC 12:00-20:00 (London PM + NY AM overlap)
    9. MAX TRADES: 3 per calendar day

    EXIT LOGIC:
    - TP: 2.0 x ATR(14) from entry
    - SL: 1.0 x ATR(14) from entry (guaranteed 1:2 R:R)
    - TRAILING: After 1R profit, move SL to breakeven
    - TIME STOP: 60 bars (5 hours) max hold
    """

    # Tunable parameters
    ema_fast: int = 9
    ema_mid: int = 21
    ema_slow: int = 50
    atr_period: int = 14
    adx_period: int = 14
    adx_threshold: float = 20.0
    rsi_period: int = 14
    vol_mult: float = 1.2
    risk_pct: float = 0.01  # 1% risk per trade
    rr_ratio: float = 2.0  # Risk:Reward = 1:2
    sl_atr_mult: float = 1.0  # SL = 1x ATR
    max_daily_trades: int = 3
    session_start: int = 12  # UTC hour
    session_end: int = 20  # UTC hour
    time_stop_bars: int = 60  # 5 hours max

    def init(self):
        c = self.data.Close
        h = self.data.High
        l = self.data.Low
        v = self.data.Volume

        self.ema9 = self.I(ema, c, self.ema_fast)
        self.ema21 = self.I(ema, c, self.ema_mid)
        self.ema50 = self.I(ema, c, self.ema_slow)
        self.atr = self.I(atr_calc, h, l, c, self.atr_period)
        self.adx = self.I(adx_calc, h, l, c, self.adx_period)
        self.rsi = self.I(rsi_calc, c, self.rsi_period)
        self.vol_sma = self.I(sma, v, 20)

        self.vwap = self.data.Daily_VWAP

        self._daily_trade_count = {}
        self._entry_bar = 0
        self._entry_price = 0.0
        self._be_moved = False
        self._diag = {
            "session": 0,
            "daily_limit": 0,
            "adx": 0,
            "vwap": 0,
            "ema": 0,
            "pullback": 0,
            "trigger": 0,
            "volume": 0,
            "rsi": 0,
            "passed": 0,
        }

    def _get_trade_date(self):
        idx = self.data.index[-1]
        return str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]

    def _today_trades(self):
        d = self._get_trade_date()
        return self._daily_trade_count.get(d, 0)

    def _increment_trades(self):
        d = self._get_trade_date()
        self._daily_trade_count[d] = self._daily_trade_count.get(d, 0) + 1

    def _manage_position(self):
        """Breakeven stop + time stop management."""
        if not self.position:
            return

        bars_held = len(self.data) - self._entry_bar
        current_price = float(self.data.Close[-1])

        # Time stop: force close after max bars
        if bars_held >= self.time_stop_bars:
            self.position.close()
            return

        # Breakeven stop: after 1R profit, move SL to entry
        if not self._be_moved:
            atr_now = float(self.atr[-1])
            if np.isnan(atr_now) or atr_now <= 0:
                return

            one_r = atr_now * self.sl_atr_mult

            if self.position.is_long:
                if current_price >= self._entry_price + one_r:
                    for trade in self.trades:
                        if trade.is_long:
                            be_price = self._entry_price + (one_r * 0.1)  # tiny buffer
                            if trade.sl is None or trade.sl < be_price:
                                trade.sl = be_price
                    self._be_moved = True

            elif self.position.is_short:
                if current_price <= self._entry_price - one_r:
                    for trade in self.trades:
                        if trade.is_short:
                            be_price = self._entry_price - (one_r * 0.1)
                            if trade.sl is None or trade.sl > be_price:
                                trade.sl = be_price
                    self._be_moved = True

    def _check_long(self):
        """Multi-factor long entry check."""
        if len(self.data.Close) < 55:
            return False

        close = float(self.data.Close[-1])
        high_prev = float(self.data.High[-2])
        low_prev = float(self.data.Low[-2])

        e9 = float(self.ema9[-1])
        e21 = float(self.ema21[-1])
        e50 = float(self.ema50[-1])
        adx_val = float(self.adx[-1])
        rsi_val = float(self.rsi[-1])
        vol_now = float(self.data.Volume[-1])
        vol_avg = float(self.vol_sma[-1])
        vwap_val = float(self.vwap[-1])
        hour_val = self.data.index[-1].hour

        if any(
            np.isnan(x)
            for x in [close, e9, e21, e50, adx_val, rsi_val, vol_avg, vwap_val]
        ):
            return False

        # 1. Session filter
        if not (self.session_start <= hour_val < self.session_end):
            self._diag["session"] += 1
            return False

        # 2. Daily trade limit
        if self._today_trades() >= self.max_daily_trades:
            self._diag["daily_limit"] += 1
            return False

        # 3. Regime: ADX must show trending
        if adx_val < self.adx_threshold:
            self._diag["adx"] += 1
            return False

        # 4. VWAP bias: price above VWAP = bullish
        if close <= vwap_val:
            self._diag["vwap"] += 1
            return False

        # 5. EMA alignment: fast > mid > slow
        if not (e9 > e21 > e50):
            self._diag["ema"] += 1
            return False

        # 6. Pullback: previous candle low near EMA21/EMA50 zone
        ema21_prev = float(self.ema21[-2])
        ema50_prev = float(self.ema50[-2])
        zone_upper = max(ema21_prev, ema50_prev) * 1.005
        zone_lower = min(ema21_prev, ema50_prev) * 0.995
        pullback_ok = low_prev <= zone_upper and low_prev >= zone_lower * 0.998
        if not pullback_ok:
            self._diag["pullback"] += 1
            return False

        # 7. Trigger: close breaks above previous high
        if close <= high_prev:
            self._diag["trigger"] += 1
            return False

        # 8. Volume confirmation
        if vol_avg <= 0 or vol_now < self.vol_mult * vol_avg:
            self._diag["volume"] += 1
            return False

        # 9. RSI filter: room to run, not overbought
        if not (35 < rsi_val < 72):
            self._diag["rsi"] += 1
            return False

        self._diag["passed"] += 1
        return True

    def _check_short(self):
        """Multi-factor short entry check (mirror of long)."""
        if len(self.data.Close) < 55:
            return False

        close = float(self.data.Close[-1])
        low_prev = float(self.data.Low[-2])
        high_prev = float(self.data.High[-2])

        e9 = float(self.ema9[-1])
        e21 = float(self.ema21[-1])
        e50 = float(self.ema50[-1])
        adx_val = float(self.adx[-1])
        rsi_val = float(self.rsi[-1])
        vol_now = float(self.data.Volume[-1])
        vol_avg = float(self.vol_sma[-1])
        vwap_val = float(self.vwap[-1])
        hour_val = self.data.index[-1].hour

        if any(
            np.isnan(x)
            for x in [close, e9, e21, e50, adx_val, rsi_val, vol_avg, vwap_val]
        ):
            return False

        if not (self.session_start <= hour_val < self.session_end):
            return False
        if self._today_trades() >= self.max_daily_trades:
            return False
        if adx_val < self.adx_threshold:
            return False
        if close >= vwap_val:
            return False
        if not (e9 < e21 < e50):
            return False

        ema21_prev = float(self.ema21[-2])
        ema50_prev = float(self.ema50[-2])
        zone_upper = max(ema21_prev, ema50_prev) * 1.005
        zone_lower = min(ema21_prev, ema50_prev) * 0.995
        pullback_ok = high_prev >= zone_lower and high_prev <= zone_upper * 1.002
        if not pullback_ok:
            return False

        if close >= low_prev:
            return False
        if vol_avg <= 0 or vol_now < self.vol_mult * vol_avg:
            return False
        if not (28 < rsi_val < 65):
            return False

        return True

    def _execute_entry(self, direction):
        """Risk-based position sizing with ATR stops."""
        atr_val = float(self.atr[-1])
        price = float(self.data.Close[-1])

        if np.isnan(atr_val) or atr_val <= 0 or np.isnan(price) or price <= 0:
            return

        sl_dist = atr_val * self.sl_atr_mult
        tp_dist = sl_dist * self.rr_ratio

        equity = float(self.equity)
        if equity <= 0:
            return

        if FRACTIONAL:
            # FractionalBacktest: size is fraction of equity (0..1)
            # Risk per 1R ≈ size * equity * (sl_dist / price)
            # Solve for size so that risk ≈ equity * risk_pct
            size = self.risk_pct * price / sl_dist
            size = float(min(max(size, 0.0), 1.0))
            if size <= 0.0:
                return
        else:
            # Classic Backtest: size is integer number of BTC units
            risk_capital = equity * self.risk_pct
            size_units = risk_capital / sl_dist
            max_affordable = (equity * 0.95) / price
            size_units = min(size_units, max_affordable)
            size_units = max(int(round(size_units)), 1)
            size = size_units

        if direction == "long":
            sl = price - sl_dist
            tp = price + tp_dist
            self.buy(size=size, sl=sl, tp=tp)
        else:
            sl = price + sl_dist
            tp = price - tp_dist
            self.sell(size=size, sl=sl, tp=tp)

        self._entry_bar = len(self.data)
        self._entry_price = price
        self._be_moved = False
        self._increment_trades()

    def next(self):
        # Manage existing position
        self._manage_position()

        # Only enter when flat
        if self.position:
            return

        if self._check_long():
            self._execute_entry("long")
        elif self._check_short():
            self._execute_entry("short")


# =============================================================================
# BACKTEST RUNNER
# =============================================================================


def run():
    data = download_data("BTC-USD", "60d")
    logging.info(
        "Data shape: %s, range: %s to %s", data.shape, data.index[0], data.index[-1]
    )

    initial_cash = 100.0 if FRACTIONAL else 1_000_000.0

    bt = BacktestClass(
        data,
        VWAPConfluenceScalper,
        cash=initial_cash,
        commission=0.00035,  # 0.035% taker
        margin=0.05,  # 20x max leverage
        trade_on_close=False,
        exclusive_orders=False,
    )

    stats = bt.run()

    # Print filter diagnostics (long side)
    strat = bt._results._strategy if hasattr(bt, "_results") else None
    if strat and hasattr(strat, "_diag"):
        print("\n  FILTER DIAGNOSTICS (long entry rejections):")
        for k, v in strat._diag.items():
            print(f"    {k:>15s}: {v}")
    else:
        print("\n  (diagnostics unavailable - check strategy access)")

    # ---- Results ----
    print("\n" + "=" * 70)
    print("  VWAP CONFLUENCE SCALPER v3.0 - BACKTEST RESULTS")
    print("=" * 70)

    key_metrics = [
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
    ]

    for m in key_metrics:
        if m in stats.index:
            val = stats[m]
            print(f"  {m:<30s}: {val}")

    print("=" * 70)

    # ---- Diagnostic vs HBMS v1 ----
    n_trades = stats.get("# Trades", 0)
    win_rate = stats.get("Win Rate [%]", 0)
    ret = stats.get("Return [%]", 0)
    max_dd = stats.get("Max. Drawdown [%]", 0)

    print("\n  DIAGNOSTIC vs HBMS v1 (-91.5% return):")
    print(f"  Trades     : {n_trades:>6}  (v1 had 384 = massive overtrading)")
    print(f"  Win Rate   : {win_rate:>6.1f}% (v1 had 29.7% = no edge)")
    print(f"  Return     : {ret:>+6.2f}%")
    print(f"  Max DD     : {max_dd:>6.2f}%")

    if n_trades > 0:
        avg_trade = stats.get("Avg. Trade [%]", 0)
        pf = stats.get("Profit Factor", 0)
        print(f"  Avg Trade  : {avg_trade:>+6.3f}%")
        print(f"  Profit Fct : {pf:>6.2f}")

        if avg_trade > 0:
            print("\n  [OK] Positive expectancy per trade")
        else:
            print("\n  [!!] Negative expectancy - strategy needs more filtering")

        if pf and pf > 1.0:
            print(f"  [OK] Profit Factor {pf:.2f} > 1.0")
        elif pf:
            print(f"  [!!] Profit Factor {pf:.2f} < 1.0 - adjust parameters")
    else:
        print("\n  [!!] No trades generated - filters may be too strict")
        print("       Try: lower adx_threshold, wider session window,")
        print("            or relax pullback zone tolerance")

    print("=" * 70)

    # ---- Parameter sensitivity (quick grid) ----
    if n_trades >= 1:
        print("\n  PARAMETER SENSITIVITY ANALYSIS:")
        print(
            f"  {'ADX':>5} {'VolM':>5} {'RR':>5} | {'N':>4} {'WR%':>7} "
            f"{'Ret%':>8} {'DD%':>8} {'PF':>6}"
        )
        print(f"  {'-'*55}")

        for adx_t in [15, 20, 25]:
            for vol_m in [1.0, 1.2, 1.5]:
                for rr in [1.5, 2.0, 2.5]:
                    try:
                        s = bt.run(
                            adx_threshold=adx_t,
                            vol_mult=vol_m,
                            rr_ratio=rr,
                        )
                            # noqa: E123
                        nt = s.get("# Trades", 0)
                        if nt > 0:
                            wr = s.get("Win Rate [%]", 0)
                            r = s.get("Return [%]", 0)
                            dd = s.get("Max. Drawdown [%]", 0)
                            p = s.get("Profit Factor", 0)
                            if p is None or np.isnan(p):
                                p = 0
                            print(
                                f"  {adx_t:>5} {vol_m:>5.1f} {rr:>5.1f} | "
                                f"{nt:>4} {wr:>6.1f}% {r:>+7.2f}% {dd:>7.2f}% {p:>5.2f}"
                            )
                    except Exception:
                        pass

        print()

    # Save HTML report (cross-platform)
    try:
        out_file = Path.cwd() / "vwap_scalper_report.html"
        bt.plot(open_browser=True, filename=str(out_file))
        logging.info("Chart saved to %s", out_file)
    except Exception as e:
        logging.warning("Could not generate plot: %s", e)

    return stats


if __name__ == "__main__":
    try:
        stats = run()
    except Exception as e:
        logging.exception("Failed: %s", e)
        sys.exit(1)

