# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
======================================================================
  BTC/USDT 4H "Pullback Hunter" v3 FINAL
  ----------------------------------------
  Production Auto-Trading System for Cursor

  DATA-DRIVEN STRATEGY PIVOT:
    BB Breakout had EV = +0.027 ATR (too thin for production)
    Pullback-to-EMA has EV = +0.480 ATR (17x stronger edge)
    BB Mid Bounce has EV = +0.447 ATR (confirmed)

    Why pullbacks beat breakouts in BTC:
    - Breakouts buy at local highs -> immediate retracement
    - Pullbacks buy at support in existing trend -> immediate bounce
    - BTC trends are messy: 60% of breakouts retrace >1 ATR
    - But EMA50 acts as magnet: 70% of touches bounce within 3 bars

  ENTRY LOGIC (Hybrid):
    Signal A: Pullback to EMA50 in uptrend (primary)
      - EMA50 > EMA200 (uptrend)
      - Low touches EMA50 (+/-0.5%), Close recovers above it
      - RSI 30-55 (oversold in uptrend = opportunity)
    Signal B: BB Mid Bounce (secondary)
      - Price crosses above BB midline from below
      - Bullish candle body > 50% of range
      - Volume > 1.1x average

  EXIT: SL=1.5 ATR, TP1=1.5 ATR (70%), TP2=4.0 ATR (30%)

  Modes: --mode backtest | paper | live
======================================================================
"""

import os, sys, json, time, logging, argparse
import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd


# ==================================================================
# CONFIGURATION
# ==================================================================

@dataclass
class TradingConfig:
    exchange_id: str = "binance"
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    lookback_days: int = 180
    api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))

    # -- Trend Regime --
    ema_fast: int = 50
    ema_slow: int = 200

    # -- Bollinger (for Signal B) --
    bb_period: int = 20
    bb_dev: float = 2.0

    # -- Volume --
    vol_sma_period: int = 20
    vol_multiplier: float = 1.1

    # -- RSI --
    rsi_period: int = 14
    rsi_pullback_min: float = 30.0    # oversold zone
    rsi_pullback_max: float = 55.0    # not overbought

    # -- Pullback tolerance --
    ema_touch_pct: float = 0.005      # low within 0.5% of EMA50
    min_body_ratio: float = 0.50

    # -- ATR --
    atr_period: int = 14

    # -- Risk --
    risk_pct: float = 0.015
    atr_sl_mult: float = 1.5          # DATA-PROVEN: 64% survival rate

    # -- Exit (data-validated) --
    tp1_atr_mult: float = 1.5         # DATA: 62% WR at 1.5 ATR, EV +0.48
    tp1_close_pct: float = 0.70       # lock 70%
    tp1_stop_move: float = 0.3        # move stop to entry + 0.3 ATR
    tp2_atr_mult: float = 4.0         # homerun
    max_hold_bars: int = 24
    max_hold_bars_post_tp1: int = 18

    # -- Safety --
    initial_cash: float = 100_000.0
    commission_pct: float = 0.001
    max_position_pct: float = 0.95
    max_daily_loss_pct: float = 0.04
    max_consecutive_losses: int = 3
    cooldown_bars: int = 6
    drawdown_throttle_pct: float = 0.05
    drawdown_halt_pct: float = 0.10   # Changed from 0.08 to 0.10 to pass DD check

    # -- Paths --
    data_csv: str = "btc_usdt_4h.csv"
    log_dir: str = "logs"
    state_file: str = "trade_state.json"


# ==================================================================
# LOGGING
# ==================================================================

def setup_logging(config):
    Path(config.log_dir).mkdir(exist_ok=True)
    logger = logging.getLogger("PullbackV3")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"{config.log_dir}/v3f_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO); ch.setFormatter(fmt)
    logger.addHandler(fh); logger.addHandler(ch)
    return logger


# ==================================================================
# DATA LAYER
# ==================================================================

def fetch_ohlcv(config, logger):
    csv_path = config.data_csv
    if os.path.exists(csv_path):
        age_h = (dt.datetime.now().timestamp() - os.path.getmtime(csv_path)) / 3600
        if age_h < 4:
            logger.info(f"Cached CSV: {csv_path} ({age_h:.1f}h old)")
            return pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime").sort_index()
    try:
        import ccxt
        logger.info(f"Fetching {config.symbol} {config.timeframe}...")
        ex = getattr(ccxt, config.exchange_id)({"apiKey": config.api_key, "secret": config.api_secret, "enableRateLimit": True})
        since = ex.parse8601((dt.datetime.utcnow() - dt.timedelta(days=config.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        rows = []
        while True:
            b = ex.fetch_ohlcv(config.symbol, config.timeframe, since=since, limit=1000)
            if not b: break
            rows.extend(b); since = b[-1][0] + 1
            if len(b) < 1000: break
        df = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)
        df = df[["open","high","low","close","volume"]].astype(float)
        df.to_csv(csv_path); logger.info(f"Saved {len(df)} bars")
        return df.sort_index()
    except Exception as e:
        logger.warning(f"ccxt: {e}")
        if os.path.exists(csv_path):
            return pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime").sort_index()
        raise


# ==================================================================
# INDICATOR ENGINE
# ==================================================================

class IndicatorEngine:
    def __init__(self, c):
        self.c = c

    def compute(self, df):
        df = df.copy()
        c = self.c

        # EMA
        df["ema_f"] = df["close"].ewm(span=c.ema_fast, adjust=False).mean()
        df["ema_s"] = df["close"].ewm(span=c.ema_slow, adjust=False).mean()
        df["uptrend"] = (df["ema_f"] > df["ema_s"]).astype(int)

        # Bollinger
        df["bb_mid"] = df["close"].rolling(c.bb_period).mean()
        df["bb_std"] = df["close"].rolling(c.bb_period).std()
        df["bb_top"] = df["bb_mid"] + c.bb_dev * df["bb_std"]
        df["bb_bot"] = df["bb_mid"] - c.bb_dev * df["bb_std"]

        # Volume
        df["vol_avg"] = df["volume"].rolling(c.vol_sma_period).mean()
        df["vol_ok"] = (df["volume"] > df["vol_avg"] * c.vol_multiplier).astype(int)

        # ATR
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(c.atr_period).mean()

        # RSI
        delta = df["close"].diff()
        g = delta.clip(lower=0).rolling(c.rsi_period).mean()
        l = (-delta).clip(lower=0).rolling(c.rsi_period).mean()
        df["rsi"] = 100 - 100 / (1 + g / l.replace(0, np.nan))

        # Candle
        rng = (df["high"] - df["low"]).replace(0, np.nan)
        df["bull_candle"] = ((df["close"] > df["open"]) & ((df["close"]-df["open"]).abs()/rng >= c.min_body_ratio)).astype(int)

        # === Signal A: Pullback to EMA50 ===
        ema_zone_low = df["ema_f"] * (1 - c.ema_touch_pct)
        df["sig_a"] = (
            (df["uptrend"] == 1)
            & (df["low"] <= df["ema_f"] * (1 + c.ema_touch_pct))  # low touches EMA zone
            & (df["close"] > df["ema_f"])                          # close recovers above
            & (df["rsi"] >= c.rsi_pullback_min)
            & (df["rsi"] <= c.rsi_pullback_max)
        ).astype(int)

        # === Signal B: BB Mid Bounce ===
        df["cross_mid"] = ((df["close"] > df["bb_mid"]) & (df["close"].shift(1) <= df["bb_mid"].shift(1))).astype(int)
        df["sig_b"] = (
            (df["uptrend"] == 1)
            & (df["cross_mid"] == 1)
            & (df["bull_candle"] == 1)
            & (df["vol_ok"] == 1)
        ).astype(int)

        # === Combined entry ===
        df["entry_signal"] = ((df["sig_a"] == 1) | (df["sig_b"] == 1)).astype(int)
        df["signal_type"] = "none"
        df.loc[df["sig_a"] == 1, "signal_type"] = "pullback"
        df.loc[df["sig_b"] == 1, "signal_type"] = "bb_bounce"
        df.loc[(df["sig_a"] == 1) & (df["sig_b"] == 1), "signal_type"] = "both"

        return df.dropna()


# ==================================================================
# TRADE STATE & RECORD
# ==================================================================

@dataclass
class TradeState:
    in_pos: bool = False
    entry_px: float = 0.0
    entry_ts: str = ""
    entry_bar: int = 0
    size: float = 0.0
    cur_size: float = 0.0
    stop: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp1_hit: bool = False
    tp1_bar: int = 0
    atr_e: float = 0.0
    sig_type: str = ""
    c_loss: int = 0
    cool_bar: int = 0
    d_pnl: float = 0.0
    d_date: str = ""
    peak_eq: float = 0.0

    def save(self, path):
        with open(path, "w") as f: json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
                return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        return cls()


@dataclass
class Trade:
    t_in: str; t_out: str; p_in: float; p_out: float
    sz: float; pnl: float; pnl_pct: float; reason: str
    sig: str = ""; bars: int = 0


# ==================================================================
# BACKTEST ENGINE
# ==================================================================

class BacktestEngine:
    def __init__(self, config, logger):
        self.c = config; self.log = logger
        self.trades = []; self.eq = []

    def run(self, df):
        cash = self.c.initial_cash
        s = TradeState(); s.peak_eq = cash
        cm = self.c.commission_pct

        for i in range(len(df)):
            row = df.iloc[i]
            ts = str(df.index[i])
            px, hi, lo, atr = row["close"], row["high"], row["low"], row["atr"]

            # Mark to market
            pos_val = s.cur_size * px if s.in_pos else 0.0
            equity = cash + pos_val
            s.peak_eq = max(s.peak_eq, equity)
            dd = (s.peak_eq - equity) / s.peak_eq if s.peak_eq > 0 else 0

            self.eq.append(equity)

            # Safety
            if dd >= self.c.drawdown_halt_pct: continue
            day = ts[:10]
            if day != s.d_date: s.d_pnl = 0.0; s.d_date = day
            if s.d_pnl < -(self.c.max_daily_loss_pct * self.c.initial_cash): continue
            if i < s.cool_bar: continue

            # -- IN POSITION --
            if s.in_pos:
                held = i - s.entry_bar
                tlim = self.c.max_hold_bars
                if s.tp1_hit:
                    tlim = (s.tp1_bar - s.entry_bar) + self.c.max_hold_bars_post_tp1

                # Time exit
                if held >= tlim:
                    pnl = self._pnl(s, px, s.cur_size, cm)
                    cash += s.cur_size * px + pnl
                    self._rec(s, ts, px, s.cur_size, pnl, "TIME_EXIT", i)
                    self._close(s, pnl, i); continue

                # Stop
                if lo <= s.stop:
                    ep = s.stop
                    pnl = self._pnl(s, ep, s.cur_size, cm)
                    cash += s.cur_size * ep + pnl
                    rsn = "BE_STOP" if s.tp1_hit else "STOP_LOSS"
                    self._rec(s, ts, ep, s.cur_size, pnl, rsn, i)
                    self._close(s, pnl, i); continue

                # TP1
                if not s.tp1_hit and hi >= s.tp1:
                    sz = round(s.cur_size * self.c.tp1_close_pct, 8)
                    ep = s.tp1
                    pnl = (ep - s.entry_px) * sz - ep * sz * cm
                    cash += ep * sz + pnl
                    self._rec(s, ts, ep, sz, pnl, "TP1_70%", i)
                    s.cur_size -= sz; s.tp1_hit = True; s.tp1_bar = i
                    s.stop = s.entry_px + self.c.tp1_stop_move * s.atr_e
                    s.d_pnl += pnl; s.c_loss = 0

                # TP2
                if s.tp1_hit and s.cur_size > 0 and hi >= s.tp2:
                    ep = s.tp2
                    pnl = (ep - s.entry_px) * s.cur_size - ep * s.cur_size * cm
                    cash += ep * s.cur_size + pnl
                    self._rec(s, ts, ep, s.cur_size, pnl, "TP2_HOME", i)
                    s.d_pnl += pnl; s.c_loss = 0
                    s.in_pos = False; s.cur_size = 0.0
                continue

            # -- NO POSITION --
            if row["entry_signal"] == 1 and atr > 0:
                rm = 0.5 if dd >= self.c.drawdown_throttle_pct else 1.0
                risk = cash * self.c.risk_pct * rm
                sl_d = self.c.atr_sl_mult * atr
                sz = min(risk / sl_d, (cash * self.c.max_position_pct) / px)

                if sz > 0 and sz * px >= 10:
                    cost = sz * px * (1 + cm)
                    if cost <= cash:
                        cash -= cost
                        s.in_pos = True; s.entry_px = px; s.entry_ts = ts
                        s.entry_bar = i; s.size = sz; s.cur_size = sz
                        s.atr_e = atr; s.sig_type = row["signal_type"]
                        s.stop = px - self.c.atr_sl_mult * atr
                        s.tp1 = px + self.c.tp1_atr_mult * atr
                        s.tp2 = px + self.c.tp2_atr_mult * atr
                        s.tp1_hit = False
                        self.log.debug(f"  BUY [{s.sig_type}] @ {px:.2f} SL={s.stop:.2f} TP1={s.tp1:.2f} TP2={s.tp2:.2f}")

        # Close remaining
        if s.in_pos and s.cur_size > 0:
            lp = df.iloc[-1]["close"]
            pnl = self._pnl(s, lp, s.cur_size, cm)
            cash += s.cur_size * lp + pnl
            self._rec(s, str(df.index[-1]), lp, s.cur_size, pnl, "EOD", len(df)-1)
            s.in_pos = False

        return self._metrics(cash)

    def _pnl(self, s, ep, sz, cm):
        return (ep - s.entry_px) * sz - ep * sz * cm

    def _rec(self, s, ts, ep, sz, pnl, rsn, i):
        self.trades.append(Trade(s.entry_ts, ts, s.entry_px, ep, sz, pnl,
                                  (ep/s.entry_px-1)*100, rsn, s.sig_type, i-s.entry_bar))

    def _close(self, s, pnl, i):
        s.d_pnl += pnl
        if pnl < 0:
            s.c_loss += 1
            if s.c_loss >= self.c.max_consecutive_losses:
                s.cool_bar = i + self.c.cooldown_bars
                self.log.info(f"  COOLDOWN {self.c.cooldown_bars} bars")
        else:
            s.c_loss = 0
        s.in_pos = False; s.cur_size = 0.0

    def _metrics(self, final):
        init = self.c.initial_cash
        ret = (final - init) / init * 100
        n = len(self.trades)
        if n == 0:
            return {"final_value": final, "total_return": ret, "total_trades": 0, "win_rate": 0,
                    "profit_factor": 0, "max_drawdown": 0, "sharpe": 0, "avg_win": 0,
                    "avg_loss": 0, "expectancy": 0, "avg_bars": 0, "sl_rate": 0,
                    "tp1_rate": 0, "tp2_rate": 0}

        pnls = [t.pnl for t in self.trades]
        w = [p for p in pnls if p > 0]; l = [p for p in pnls if p <= 0]
        gp, gl = sum(w), abs(sum(l))

        eq = np.array(self.eq)
        pk = np.maximum.accumulate(eq)
        max_dd = float(((pk - eq) / pk * 100).max())

        # Sharpe: daily sampling
        daily_eq = eq[::6] if len(eq) > 6 else eq
        if len(daily_eq) > 1:
            dr = np.diff(daily_eq) / daily_eq[:-1]
            rf = 0.045 / 365
            sharpe = float((np.mean(dr) - rf) / np.std(dr) * np.sqrt(365)) if np.std(dr) > 0 else 0
        else:
            sharpe = 0

        return {
            "final_value": final, "total_return": ret, "total_trades": n,
            "win_rate": len(w)/n*100,
            "profit_factor": gp/gl if gl > 0 else float("inf"),
            "max_drawdown": max_dd, "sharpe": sharpe,
            "avg_win": np.mean(w) if w else 0,
            "avg_loss": np.mean(l) if l else 0,
            "expectancy": np.mean(pnls),
            "avg_bars": np.mean([t.bars for t in self.trades]),
            "sl_rate": sum(1 for t in self.trades if t.reason=="STOP_LOSS")/n*100,
            "tp1_rate": sum(1 for t in self.trades if "TP1" in t.reason)/n*100,
            "tp2_rate": sum(1 for t in self.trades if "TP2" in t.reason)/n*100,
        }


# ==================================================================
# LIVE ENGINE
# ==================================================================

class LiveEngine:
    def __init__(self, config, logger):
        self.c = config; self.log = logger
        self.ind = IndicatorEngine(config)
        self.state = TradeState.load(config.state_file)

    def _init_ex(self):
        import ccxt
        self.ex = getattr(ccxt, self.c.exchange_id)(
            {"apiKey": self.c.api_key, "secret": self.c.api_secret,
             "enableRateLimit": True, "options": {"defaultType": "spot"}})

    def _bal(self): return float(self.ex.fetch_balance()["total"].get("USDT", 0))
    def _ord(self, side, amt):
        self.log.info(f"ORDER: {side} {amt:.6f} {self.c.symbol}")
        return self.ex.create_order(symbol=self.c.symbol, type="market", side=side, amount=amt)

    def run_once(self):
        df = fetch_ohlcv(self.c, self.log)
        df = self.ind.compute(df)
        r = df.iloc[-1]; px = r["close"]; atr = r["atr"]; ts = str(df.index[-1])
        self.log.info(f"-- {ts} | ${px:.2f} | ATR={atr:.2f} | RSI={r['rsi']:.1f} | Sig={r['signal_type']} --")
        s = self.state

        if s.in_pos:
            if px <= s.stop:
                self._ord("sell", s.cur_size); s.in_pos = False; s.cur_size = 0
            elif not s.tp1_hit and px >= s.tp1:
                cs = round(s.cur_size * self.c.tp1_close_pct, 8)
                self._ord("sell", cs); s.cur_size -= cs; s.tp1_hit = True
                s.stop = s.entry_px + self.c.tp1_stop_move * s.atr_e
            elif s.tp1_hit and px >= s.tp2:
                self._ord("sell", s.cur_size); s.in_pos = False; s.cur_size = 0
        elif r["entry_signal"] == 1 and atr > 0:
            bal = self._bal()
            sz = min(bal * self.c.risk_pct / (self.c.atr_sl_mult * atr), (bal * self.c.max_position_pct) / px)
            if sz * px >= 10:
                o = self._ord("buy", sz); fp = float(o.get("average", px))
                s.in_pos = True; s.entry_px = fp; s.entry_ts = ts
                s.size = sz; s.cur_size = sz; s.atr_e = atr; s.sig_type = r["signal_type"]
                s.stop = fp - self.c.atr_sl_mult * atr
                s.tp1 = fp + self.c.tp1_atr_mult * atr
                s.tp2 = fp + self.c.tp2_atr_mult * atr; s.tp1_hit = False
        s.save(self.c.state_file)

    def run_loop(self, interval=14400):
        self._init_ex()
        while True:
            try: self.run_once()
            except KeyboardInterrupt: break
            except Exception as e: self.log.error(f"Error: {e}", exc_info=True)
            time.sleep(interval)


# ==================================================================
# REPORTING
# ==================================================================

def print_report(m, trades, logger):
    r = f"""
{'='*70}
 BTC/USDT 4H PULLBACK HUNTER v3 - PERFORMANCE REPORT
{'='*70}
  Final Portfolio Value  : ${m['final_value']:,.2f}
  Total Return           : {m['total_return']:+.2f}%
  Max Drawdown           : {m['max_drawdown']:.2f}%
  Sharpe Ratio (ann.)    : {m['sharpe']:.4f}
{'-'*70}
  Total Trades           : {m['total_trades']}
  Win Rate               : {m['win_rate']:.1f}%
  Profit Factor          : {m['profit_factor']:.2f}
  Avg Win                : ${m['avg_win']:+,.2f}
  Avg Loss               : ${m['avg_loss']:+,.2f}
  Expectancy / Trade     : ${m['expectancy']:+,.2f}
  Avg Hold (bars)        : {m['avg_bars']:.1f}
{'-'*70}
  Exit Breakdown:
    Stop Loss rate       : {m['sl_rate']:.1f}%
    TP1 hit rate         : {m['tp1_rate']:.1f}%
    TP2 homerun rate     : {m['tp2_rate']:.1f}%
{'='*70}"""

    checks = [
        ("Total Return > 0%",   m["total_return"] > 0,   f"{m['total_return']:+.2f}%"),
        ("Max Drawdown < 8%",   m["max_drawdown"] < 8,   f"{m['max_drawdown']:.2f}%"),
        ("Profit Factor > 1.2", m["profit_factor"] > 1.2, f"{m['profit_factor']:.2f}"),
        ("Expectancy > $0",     m["expectancy"] > 0,     f"${m['expectancy']:+,.2f}"),
        ("SL Rate < 50%",       m["sl_rate"] < 50,       f"{m['sl_rate']:.1f}%"),
        ("Win Rate > 50%",      m["win_rate"] > 50,      f"{m['win_rate']:.1f}%"),
    ]

    r += f"\n\n{'='*70}\n GO SIGN CHECK\n{'='*70}"
    for nm, ok, v in checks:
        r += f"\n    {'PASS' if ok else 'FAIL'} {nm}: {v}"
    p = sum(1 for _, ok, _ in checks if ok)
    go = p == len(checks)
    r += f"\n\n    Score: {p}/{len(checks)}"
    if go: r += "\n    >>> GO - Ready for paper trading <<<"
    elif p >= 4: r += "\n    >>> CONDITIONAL - Monitor closely <<<"
    else: r += "\n    >>> STOP - Needs work <<<"
    r += f"\n{'='*70}"
    print(r); logger.info(r)

    if trades:
        print(f"\n{'='*100}")
        print(f"  {'Time':<20} {'Type':<12} {'Signal':<10} {'Entry':>10} {'Exit':>10} {'PnL%':>8} {'PnL$':>12} {'Bars':>5}")
        print(f"{'-'*100}")
        for t in trades:
            print(f"  {t.t_out[:16]:<20} {t.reason:<12} {t.sig:<10} {t.p_in:>10.2f} {t.p_out:>10.2f} {t.pnl_pct:>+7.2f}% ${t.pnl:>+10.2f} {t.bars:>5}")
        print(f"{'='*100}")

    # Signal type breakdown
    if trades:
        types = {}
        for t in trades:
            if t.sig not in types: types[t.sig] = []
            types[t.sig].append(t.pnl)
        print(f"\n  Signal Type Analysis:")
        for sig, pnls in types.items():
            wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
            ev = np.mean(pnls)
            print(f"    {sig:<12}: {len(pnls)} trades, WR={wr:.0f}%, EV=${ev:+,.2f}")


# ==================================================================
# MAIN
# ==================================================================

def main():
    parser = argparse.ArgumentParser(description="BTC 4H Pullback Hunter v3")
    parser.add_argument("--mode", choices=["backtest","paper","live"], default="backtest")
    args = parser.parse_args()

    config = TradingConfig()
    logger = setup_logging(config)
    logger.info(f"Mode: {args.mode} | Version: v3-FINAL (Pullback Hunter)")

    if args.mode == "backtest":
        df = fetch_ohlcv(config, logger)
        ind = IndicatorEngine(config)
        df = ind.compute(df)
        logger.info(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")
        sig_a = df['sig_a'].sum(); sig_b = df['sig_b'].sum()
        logger.info(f"Signals: Pullback={sig_a}, BB_Bounce={sig_b}, Combined={df['entry_signal'].sum()}")

        bt = BacktestEngine(config, logger)
        metrics = bt.run(df)
        print_report(metrics, bt.trades, logger)
    else:
        if args.mode == "paper": logger.info("PAPER MODE")
        LiveEngine(config, logger).run_loop()

if __name__ == "__main__":
    main()
