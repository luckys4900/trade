# -*- coding: utf-8 -*-
"""
Daily-candle backtest: inflow event -> entry at first daily close >= event,
exit at first daily close >= T + N days.

Compares with 4h methodology but uses 1d OHLCV only.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
sys.path.insert(0, DATA_DIR)

from btc_inflow_backtest import load_events  # noqa: E402

logger = logging.getLogger("daily_bt")
logging.basicConfig(level=logging.INFO, format="%(message)s")

ROUND_TRIP_FEE_PCT = 0.10
HORIZON_DAYS = (1, 3, 7, 14)


def fetch_daily_ohlcv(symbol: str = "BTC/USDT", since_days: int = 1400) -> pd.DataFrame:
    cache_path = os.path.join(DATA_DIR, "btc_price_1d_cache.csv")
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400 * 3:
            logger.info(f"Loading cached 1d data from {cache_path}")
            df = pd.read_csv(cache_path)
            df["datetime"] = pd.to_datetime(df["datetime"])
            return df

    logger.info(f"Fetching {symbol} 1d from Binance...")
    import ccxt

    exchange = ccxt.binance({"enableRateLimit": True})
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000)
    all_ohlcv = []
    current_since = since_ms
    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, "1d", since=current_since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        current_since = ohlcv[-1][0] + 1
        if len(ohlcv) < 1000:
            break
        time.sleep(0.5)

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df.to_csv(cache_path, index=False)
    logger.info(f"Saved {len(df)} daily candles to {cache_path}")
    return df


def run_backtest(events: List[dict], df: pd.DataFrame) -> List[dict]:
    price_ts = df["timestamp"].values.astype(np.int64)
    price_close = df["close"].values.astype(np.float64)
    results = []

    for ev in events:
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx = int(np.searchsorted(price_ts, ev_ts_ms))
        if idx >= len(price_ts) - 1 or idx < 1:
            continue
        entry = float(price_close[idx])

        for d in HORIZON_DAYS:
            target_ts_ms = ev_ts_ms + d * 24 * 3600 * 1000
            fut_idx = int(np.searchsorted(price_ts, target_ts_ms))
            if fut_idx >= len(price_ts):
                continue
            fut = float(price_close[fut_idx])
            chg = (fut - entry) / entry * 100.0
            short_g = -chg
            results.append(
                {
                    "horizon_days": d,
                    "change_pct": chg,
                    "short_gross": short_g,
                    "short_net": short_g - ROUND_TRIP_FEE_PCT,
                    "exchange": ev.get("exchange", ""),
                    "datetime": datetime.utcfromtimestamp(ev["timestamp"]).strftime("%Y-%m-%d"),
                }
            )
    return results


def summarize(results: List[dict]) -> None:
    from scipy import stats

    print("\n" + "=" * 70)
    print("DAILY (1d) CANDLE BACKTEST - naive short at inflow (first daily close >= event)")
    print(f"Round-trip fee assumption: {ROUND_TRIP_FEE_PCT}%")
    print("=" * 70)

    for d in HORIZON_DAYS:
        sub = [r for r in results if r["horizon_days"] == d]
        if not sub:
            continue
        gross = np.array([r["short_gross"] for r in sub])
        net = np.array([r["short_net"] for r in sub])
        tm = stats.trim_mean(gross, proportiontocut=0.1) if len(gross) >= 10 else np.nan
        print(f"\n  Horizon {d} calendar days (n={len(sub)})")
        print(f"    Short gross:  mean={gross.mean():+.4f}%  median={np.median(gross):+.4f}%  "
              f"win%={(gross > 0).mean() * 100:.1f}%  std={gross.std():.2f}%")
        print(f"    Short net:    mean={net.mean():+.4f}%  median={np.median(net):+.4f}%")
        if not np.isnan(tm):
            print(f"    Trimmed mean (10%): {tm:+.4f}")


def main() -> None:
    events = load_events(min_btc=50, external_only=True)
    df = fetch_daily_ohlcv()
    logger.info(f"Events: {len(events)}  Daily candles: {len(df)}")
    results = run_backtest(events, df)
    summarize(results)

    # Per-horizon unique event count
    n_by_h = {}
    for d in HORIZON_DAYS:
        n_by_h[d] = len([r for r in results if r["horizon_days"] == d])
    print("\n  Note: 4h backtest used ~79 events; daily may differ if events fall outside range.")
    print(f"  Rows per horizon: {n_by_h}")


if __name__ == "__main__":
    main()
