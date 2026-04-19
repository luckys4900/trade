# -*- coding: utf-8 -*-
"""
Pro multi-factor backtest for whale-exchange inflow short strategy.

Adds:
  - Exchange tier (empirical edge from prior project research)
  - Inflow size band (exclude mega aggregation noise)
  - Daily trend: close vs MA50 / MA200
  - Daily RSI(14) band
  - Daily ATR% regime (volatility filter)
  - 4h structure: close vs MA50 at event time
  - Hold: 7 calendar days (daily close), RT fee

Usage:
    python data/btc_inflow_strategy_pro_backtest.py
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Callable, List

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
sys.path.insert(0, DATA_DIR)

from btc_inflow_backtest import fetch_historical_prices, load_events  # noqa: E402
from btc_inflow_backtest_daily import fetch_daily_ohlcv  # noqa: E402

logger = logging.getLogger("pro_bt")
logging.basicConfig(level=logging.INFO, format="%(message)s")

ROUND_TRIP_FEE_PCT = 0.10
FUNDING_7D_EST_PCT = 0.07  # optional perp drag: ~0.01% x 7d
HOLD_DAYS = 7

# Empirical: OKEx strongest short signal; BitMEX/OKX secondary; exclude noisy venues from "tier A"
TIER_A_EXCHANGES = frozenset({"OKEx", "BitMEX", "OKX"})
TIER_B_EXCHANGES = frozenset({"OKEx", "BitMEX", "OKX", "Binance-1", "Binance-2", "Binance-3", "Crypto.com"})


def atr_pct(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean()
    return (atr / c) * 100.0


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def ma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


def build_daily_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["ma50_d"] = ma(c, 50)
    out["ma200_d"] = ma(c, 200)
    out["rsi14_d"] = rsi_series(c, 14)
    out["atr_pct_d"] = atr_pct(out, 14)
    return out


def build_4h_ma50(df4: pd.DataFrame) -> pd.DataFrame:
    out = df4.copy()
    out["ma50_4h"] = ma(out["close"], 50)
    return out


@dataclass
class FilterSpec:
    name: str
    pred: Callable[[dict, int, int, "DailyRow", "FourHRow"], bool]


@dataclass
class DailyRow:
    close: float
    ma50: float
    ma200: float
    rsi: float
    atr_pct: float
    idx: int


@dataclass
class FourHRow:
    close: float
    ma50: float
    idx: int


def get_daily_row(dfeat: pd.DataFrame, idx: int) -> Optional[DailyRow]:
    if idx < 0 or idx >= len(dfeat):
        return None
    r = dfeat.iloc[idx]
    if pd.isna(r["ma200_d"]) or pd.isna(r["rsi14_d"]):
        return None
    return DailyRow(
        close=float(r["close"]),
        ma50=float(r["ma50_d"]),
        ma200=float(r["ma200_d"]),
        rsi=float(r["rsi14_d"]),
        atr_pct=float(r["atr_pct_d"]),
        idx=idx,
    )


def get_4h_row(feat4: pd.DataFrame, idx: int) -> Optional[FourHRow]:
    if idx < 0 or idx >= len(feat4):
        return None
    r = feat4.iloc[idx]
    if pd.isna(r["ma50_4h"]):
        return None
    return FourHRow(close=float(r["close"]), ma50=float(r["ma50_4h"]), idx=idx)


def run_trades(
    events: List[dict],
    dfeat: pd.DataFrame,
    feat4: pd.DataFrame,
    ts_d: np.ndarray,
    close_d: np.ndarray,
    ts_4h: np.ndarray,
    pred: Callable[[dict, int, int, DailyRow, FourHRow], bool],
) -> List[float]:
    """Returns list of short NET returns (one per trade) for HOLD_DAYS horizon."""
    out: List[float] = []
    for ev in events:
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx_d = int(np.searchsorted(ts_d, ev_ts_ms))
        if idx_d >= len(ts_d) - 1 or idx_d < 200:
            continue
        idx_4h = int(np.searchsorted(ts_4h, ev_ts_ms))
        if idx_4h >= len(ts_4h) - 1 or idx_4h < 50:
            continue

        dr = get_daily_row(dfeat, idx_d)
        h4 = get_4h_row(feat4, idx_4h)
        if dr is None or h4 is None:
            continue
        if not pred(ev, idx_d, idx_4h, dr, h4):
            continue

        entry = dr.close
        target_ts_ms = ev_ts_ms + HOLD_DAYS * 24 * 3600 * 1000
        fut_idx = int(np.searchsorted(ts_d, target_ts_ms))
        if fut_idx >= len(close_d):
            continue
        fut = float(close_d[fut_idx])
        chg = (fut - entry) / entry * 100.0
        short_net = -chg - ROUND_TRIP_FEE_PCT - FUNDING_7D_EST_PCT
        out.append(short_net)
    return out


def stats(name: str, rets: List[float]) -> None:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    if len(rets) < 3:
        print(f"  Trades: {len(rets)} (insufficient for robust stats)")
        if rets:
            print(f"  Returns: {[round(x, 3) for x in rets]}")
        return
    a = np.array(rets)
    wins = a > 0
    print(f"  Trades: {len(a)}")
    print(f"  Win rate: {100 * wins.mean():.1f}%")
    print(f"  Mean net % / trade: {a.mean():+.4f}%  (median: {np.median(a):+.4f}%)")
    print(f"  Std %: {a.std():.4f}")
    if a.std() > 1e-9:
        # rough: ~52 independent 1-week slots per year (overlapping trades ignored)
        sharpe_like = a.mean() / a.std() * np.sqrt(26)
        print(f"  Sharpe-like (approx, sqrt(26)): {sharpe_like:.2f}")
    cum = np.prod(1.0 + a / 100.0) - 1.0
    print(f"  Cumulative simple compound (chained): {100 * cum:+.2f}%")
    peak, max_dd = 0.0, 0.0
    eq = 100.0
    for r in a:
        eq *= 1.0 + r / 100.0
        peak = max(peak, eq)
        max_dd = min(max_dd, (eq - peak) / peak * 100.0)
    print(f"  Max drawdown (simple equity from 100): {max_dd:.2f}%")


def main() -> None:
    events = load_events(min_btc=50, external_only=True)
    dfeat = build_daily_features(fetch_daily_ohlcv())
    feat4 = build_4h_ma50(fetch_historical_prices())
    ts_d = dfeat["timestamp"].values.astype(np.int64)
    close_d = dfeat["close"].values.astype(np.float64)
    ts_4h = feat4["timestamp"].values.astype(np.int64)

    def base_size(ev: dict) -> bool:
        x = float(ev.get("inflow_btc", 0))
        return 50.0 <= x < 1000.0

    # --- filter stacks ---
    def f_baseline(ev, idx_d, idx_4h, dr, h4):
        return True

    def f_size(ev, idx_d, idx_4h, dr, h4):
        return base_size(ev)

    def f_tier_a(ev, idx_d, idx_4h, dr, h4):
        return base_size(ev) and ev.get("exchange") in TIER_A_EXCHANGES

    def f_tier_b(ev, idx_d, idx_4h, dr, h4):
        return base_size(ev) and ev.get("exchange") in TIER_B_EXCHANGES

    def f_trend_d200(ev, idx_d, idx_4h, dr, h4):
        return f_tier_a(ev, idx_d, idx_4h, dr, h4) and dr.close < dr.ma200

    def f_trend_d50(ev, idx_d, idx_4h, dr, h4):
        return f_tier_a(ev, idx_d, idx_4h, dr, h4) and dr.close < dr.ma50

    def f_4h_weak(ev, idx_d, idx_4h, dr, h4):
        return f_trend_d200(ev, idx_d, idx_4h, dr, h4) and h4.close < h4.ma50

    def f_vol(ev, idx_d, idx_4h, dr, h4):
        return f_4h_weak(ev, idx_d, idx_4h, dr, h4) and 1.0 <= dr.atr_pct <= 5.5

    def f_rsi(ev, idx_d, idx_4h, dr, h4):
        return f_vol(ev, idx_d, idx_4h, dr, h4) and 38.0 <= dr.rsi <= 68.0

    def f_pro_relaxed(ev, idx_d, idx_4h, dr, h4):
        """Wider exchange tier B, trend + 4h + vol, moderate RSI."""
        if not base_size(ev) or ev.get("exchange") not in TIER_B_EXCHANGES:
            return False
        if not (dr.close < dr.ma200 and h4.close < h4.ma50):
            return False
        if not (1.0 <= dr.atr_pct <= 6.0):
            return False
        if not (35.0 <= dr.rsi <= 70.0):
            return False
        return True

    def f_pro_aggressive(ev, idx_d, idx_4h, dr, h4):
        """Tier A only, strict vol + RSI (higher precision, fewer trades)."""
        if not f_tier_a(ev, idx_d, idx_4h, dr, h4):
            return False
        if not (dr.close < dr.ma50 and h4.close < h4.ma50):
            return False
        if not (1.2 <= dr.atr_pct <= 4.5):
            return False
        if not (42.0 <= dr.rsi <= 65.0):
            return False
        return True

    suites = [
        ("S0 Baseline: all events, no factor filters (7d hold, fee+funding)", f_baseline),
        ("S1 + Inflow size 50-1000 BTC only", f_size),
        ("S2 + Tier-A exchanges (OKEx/BitMEX/OKX)", f_tier_a),
        ("S3 + Daily close < MA200 (long-term bearish)", f_trend_d200),
        ("S4 + Daily close < MA50 (stronger short bias)", f_trend_d50),
        ("S5 + 4h close < MA50 (local weak structure)", f_4h_weak),
        ("S6 + ATR% 1.0-5.5 (daily vol band)", f_vol),
        ("S7 + RSI 38-68 (avoid extremes)", f_rsi),
        ("P1 PRO (relaxed): Tier-B + MA200 + 4h MA50 + vol + RSI", f_pro_relaxed),
        ("P2 PRO (aggressive): Tier-A + dual MA50 + tight vol/RSI", f_pro_aggressive),
    ]

    print("#" * 70)
    print("# PRO MULTI-FACTOR BACKTEST - 7d hold, daily entry close")
    print("# Costs: {:.2f}% RT + {:.2f}% est. 7d funding".format(ROUND_TRIP_FEE_PCT, FUNDING_7D_EST_PCT))
    print("#" * 70)

    for label, fn in suites:
        rets = run_trades(events, dfeat, feat4, ts_d, close_d, ts_4h, fn)
        stats(label, rets)

    # Best-effort: also report gross without funding for main pro
    print("\n" + "=" * 70)
    print("Sensitivity: P1 PRO net return if funding = 0 (perp vs spot)")
    print("=" * 70)

    def run_gross_custom(pred, subtract_funding: float) -> List[float]:
        out: List[float] = []
        for ev in events:
            ev_ts_ms = int(ev["timestamp"]) * 1000
            idx_d = int(np.searchsorted(ts_d, ev_ts_ms))
            if idx_d >= len(ts_d) - 1 or idx_d < 200:
                continue
            idx_4h = int(np.searchsorted(ts_4h, ev_ts_ms))
            if idx_4h >= len(ts_4h) - 1 or idx_4h < 50:
                continue
            dr = get_daily_row(dfeat, idx_d)
            h4 = get_4h_row(feat4, idx_4h)
            if dr is None or h4 is None:
                continue
            if not f_pro_relaxed(ev, idx_d, idx_4h, dr, h4):
                continue
            entry = dr.close
            target_ts_ms = ev_ts_ms + HOLD_DAYS * 24 * 3600 * 1000
            fut_idx = int(np.searchsorted(ts_d, target_ts_ms))
            if fut_idx >= len(close_d):
                continue
            fut = float(close_d[fut_idx])
            chg = (fut - entry) / entry * 100.0
            out.append(-chg - ROUND_TRIP_FEE_PCT - subtract_funding)
        return out

    for fund in (0.0, FUNDING_7D_EST_PCT):
        r = run_gross_custom(f_pro_relaxed, fund)
        if len(r) >= 3:
            a = np.array(r)
            print(f"  Funding adj {fund:.2f}%: mean={a.mean():+.4f}%  n={len(a)}")


if __name__ == "__main__":
    main()
