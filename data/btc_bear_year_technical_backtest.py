# -*- coding: utf-8 -*-
"""
Bear-year sanity check when historical INFLOW labels are missing.

Facts from btc_inflow_events.json (50+ BTC, external, exclusions):
  - 2018: 0 events -> cannot replicate "inflow short" for that year with this file
  - 2022: 1 event  -> at most one trade (no distribution)
  - 2026: dominates

This script:
  1) Reports inflow event counts by year (honest limit)
  2) Fetches extended daily BTC/USDT and applies S6-like PRICE-ONLY proxy
     (daily MA200 + daily MA50 + ATR% band, same costs as pro backtest)
     on EVERY calendar day in 2018 and 2022 where indicators are valid.
  3) Compares to 2026 days that (a) have an inflow event and (b) pass the same proxy.

This tests whether TECHNICAL filters behave similarly in known bear years vs 2026 inflow days.
It does NOT replace a true multi-year inflow panel (needs on-chain event history).

Usage:
    python data/btc_bear_year_technical_backtest.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
sys.path.insert(0, DATA_DIR)

from btc_inflow_backtest import load_events  # noqa: E402
from btc_inflow_strategy_pro_backtest import (  # noqa: E402
    ROUND_TRIP_FEE_PCT,
    FUNDING_7D_EST_PCT,
    HOLD_DAYS,
    atr_pct,
)

logger = logging.getLogger("bear_bt")
logging.basicConfig(level=logging.INFO, format="%(message)s")

EXT_CACHE = os.path.join(DATA_DIR, "btc_price_1d_extended.csv")


def fetch_extended_daily(since_days: int = 4200) -> pd.DataFrame:
    if os.path.exists(EXT_CACHE):
        age = time.time() - os.path.getmtime(EXT_CACHE)
        if age < 86400 * 7:
            logger.info(f"Loading {EXT_CACHE}")
            df = pd.read_csv(EXT_CACHE)
            df["datetime"] = pd.to_datetime(df["datetime"])
            return df

    logger.info("Fetching extended 1d OHLCV from Binance (may take ~30s)...")
    import ccxt

    exchange = ccxt.binance({"enableRateLimit": True})
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000)
    all_rows = []
    cur = since_ms
    while True:
        batch = exchange.fetch_ohlcv("BTC/USDT", "1d", since=cur, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        cur = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.35)

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df.to_csv(EXT_CACHE, index=False)
    logger.info(f"Saved {len(df)} rows to {EXT_CACHE}")
    return df


def ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    al = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["ma50_d"] = ma(c, 50)
    out["ma200_d"] = ma(c, 200)
    out["rsi14_d"] = rsi_series(c, 14)
    out["atr_pct_d"] = atr_pct(out, 14)
    return out


def short_7d_net(
    close: np.ndarray,
    ts: np.ndarray,
    idx: int,
) -> Optional[float]:
    if idx >= len(close) - 1 or idx < 200:
        return None
    entry = float(close[idx])
    ev_ts_ms = int(ts[idx])
    target_ts_ms = ev_ts_ms + HOLD_DAYS * 24 * 3600 * 1000
    fut_idx = int(np.searchsorted(ts, target_ts_ms))
    if fut_idx >= len(close):
        return None
    fut = float(close[fut_idx])
    chg = (fut - entry) / entry * 100.0
    return -chg - ROUND_TRIP_FEE_PCT - FUNDING_7D_EST_PCT


def s6_price_only_daily(row: pd.Series) -> bool:
    """Mirror S6 trend/vol without exchange or 4h (daily proxy)."""
    if pd.isna(row["ma200_d"]) or pd.isna(row["ma50_d"]):
        return False
    c = float(row["close"])
    if not (c < float(row["ma200_d"]) and c < float(row["ma50_d"])):
        return False
    ap = float(row["atr_pct_d"])
    if not (1.0 <= ap <= 5.5):
        return False
    return True


def year_mask(dt: pd.Series, y: int) -> np.ndarray:
    return (dt.dt.year == y).values


def summarize(name: str, rets: List[float]) -> None:
    print(f"\n  {name}")
    if len(rets) == 0:
        print("    n=0")
        return
    a = np.array(rets)
    print(
        f"    n={len(a)}  mean={a.mean():+.4f}%  median={np.median(a):+.4f}%  "
        f"win%={(a > 0).mean() * 100:.1f}%  std={a.std():.2f}%"
    )


def main() -> None:
    events = load_events(min_btc=50, external_only=True)
    print("=" * 70)
    print("A) Inflow events in this repo (same filter as backtests)")
    print("=" * 70)
    by_y: Dict[int, int] = {}
    for ev in events:
        y = datetime.utcfromtimestamp(ev["timestamp"]).year
        by_y[y] = by_y.get(y, 0) + 1
    for y in sorted(by_y.keys()):
        print(f"  {y}: {by_y[y]} events")
    print(f"  2018: {by_y.get(2018, 0)} events  <- need labels to run identical inflow BT")
    print(f"  2022: {by_y.get(2022, 0)} events")

    df = enrich(fetch_extended_daily())
    ts = df["timestamp"].values.astype(np.int64)
    close = df["close"].values.astype(np.float64)
    dt = df["datetime"]

    print("\n" + "=" * 70)
    print("B) Price-only S6 DAILY PROXY (close<MA200 & close<MA50 & ATR% in [1,5.5])")
    print("    Hold 7d, same fee+funding as pro backtest.")
    print("    Applied to EVERY valid day in selected years (not only inflows).")
    print("=" * 70)

    for year in (2018, 2022, 2021, 2024):
        rets = []
        for i in range(len(df)):
            if dt.iloc[i].year != year:
                continue
            if i < 200:
                continue
            if not s6_price_only_daily(df.iloc[i]):
                continue
            r = short_7d_net(close, ts, i)
            if r is not None:
                rets.append(r)
        summarize(f"Year {year} (all days passing proxy)", rets)

    # 2026: only on inflow event dates (by matching day)
    ev_days_2026 = set()
    for ev in events:
        if datetime.utcfromtimestamp(ev["timestamp"]).year != 2026:
            continue
        d = datetime.utcfromtimestamp(ev["timestamp"]).date()
        ev_days_2026.add(d)

    rets_2026_inf = []
    for i in range(len(df)):
        if dt.iloc[i].year != 2026:
            continue
        if i < 200:
            continue
        d = pd.Timestamp(dt.iloc[i]).date()
        if d not in ev_days_2026:
            continue
        if not s6_price_only_daily(df.iloc[i]):
            continue
        r = short_7d_net(close, ts, i)
        if r is not None:
            rets_2026_inf.append(r)
    summarize("2026 only on CALENDAR DAYS with >=1 inflow event + proxy pass", rets_2026_inf)

    # Single 2022 inflow event if any
    ev22 = [e for e in events if datetime.utcfromtimestamp(e["timestamp"]).year == 2022]
    if ev22:
        ev = ev22[0]
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx = int(np.searchsorted(ts, ev_ts_ms))
        r = short_7d_net(close, ts, idx) if idx >= 200 else None
        print("\n" + "=" * 70)
        print("C) The ONE 2022 inflow event in JSON (full sample naive 7d short net)")
        print("=" * 70)
        print(f"  net 7d short (if valid idx): {r}")

    print("\n" + "=" * 70)
    print("D) Interpretation")
    print("=" * 70)
    print("""
  - Identical ON-CHAIN inflow backtest for 2018 is impossible with current JSON
    (zero labeled events). Same for statistical power in 2022 (one event).
  - Section B compares TECHNICAL side of the rule in bear calendar years (2018,
    2022) vs a bull year (2021) and recent (2024). This checks regime behaviour
    of the filters, not the inflow trigger.
  - If 2018/2022 pass-groups show positive mean 7d short similar to 2026 inflow
    subset, technical stack is more credible across bear regimes; if not, 2026
    inflow results may be episode-specific.
  - To claim full reproducibility, build a multi-year inflow event panel from
    blockchain indexers (same exchange addresses and thresholds).
""")


if __name__ == "__main__":
    main()
