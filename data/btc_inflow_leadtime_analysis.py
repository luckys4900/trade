# -*- coding: utf-8 -*-
"""
Lead time from exchange inflow (event time) to first meaningful BTC price drop.
Evaluates whether shorting on inflow confirmation is plausible on 4h data.

Usage:
    python data/btc_inflow_leadtime_analysis.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# Reuse backtest filters
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
sys.path.insert(0, DATA_DIR)

from btc_inflow_backtest import EXCLUDE_EXCHANGES, fetch_historical_prices, load_events  # noqa: E402

logger = logging.getLogger("leadtime")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def first_hit_hours(
    price_ts: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    ev_ts_ms: int,
    start_idx: int,
    drop_pct: float,
    max_bars: int,
    use_low: bool,
) -> Optional[float]:
    """
    Hours from event-aligned bar to first bar where price drops >= drop_pct from entry close.
    entry = closes[start_idx]. Scan from start_idx+1 .. start_idx+max_bars (next bars only).
    """
    entry = float(closes[start_idx])
    thr = entry * (1.0 - drop_pct / 100.0)
    end = min(start_idx + max_bars + 1, len(closes))
    for j in range(start_idx + 1, end):
        px = float(lows[j]) if use_low else float(closes[j])
        if px <= thr:
            dt_ms = int(price_ts[j]) - ev_ts_ms
            return max(0.0, dt_ms / 3600000.0)
    return None


def analyze(
    events: List[dict],
    df: pd.DataFrame,
    thresholds: List[float],
    max_hours: int,
    use_low: bool,
) -> None:
    price_ts = df["timestamp"].values.astype(np.int64)
    lows = df["low"].values.astype(np.float64)
    closes = df["close"].values.astype(np.float64)

    bar_ms = 4 * 3600 * 1000
    max_bars = int(np.ceil(max_hours / 4))

    rows = []
    for ev in events:
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx = int(np.searchsorted(price_ts, ev_ts_ms))
        if idx >= len(price_ts) - 1 or idx < 1:
            continue
        entry = float(closes[idx])
        for d in thresholds:
            h = first_hit_hours(price_ts, lows, closes, ev_ts_ms, idx, d, max_bars, use_low)
            rows.append(
                {
                    "exchange": ev["exchange"],
                    "inflow_btc": ev["inflow_btc"],
                    "tx": ev.get("tx_hash", "")[:16],
                    "threshold_pct": d,
                    "hit_hours": h,
                    "hit": h is not None,
                }
            )

    rdf = pd.DataFrame(rows)
    mode = "low (intrabar)" if use_low else "close"
    print(f"\n=== Entry: first 4h candle close at/after on-chain event time (same as backtest) ===")
    print(f"=== Drop detection: {mode}, max_horizon={max_hours}h ===\n")

    for d in thresholds:
        sub = rdf[rdf["threshold_pct"] == d]
        hits = sub[sub["hit"]]
        n = len(sub) // len(thresholds)  # unique events
        # sub has one row per event per threshold
        sub_d = sub[sub["threshold_pct"] == d]
        hit_rate = len(sub_d[sub_d["hit"]]) / len(sub_d) * 100 if len(sub_d) else 0
        times = sub_d.loc[sub_d["hit"], "hit_hours"].dropna()
        print(f"--- First >= {d}% drop from entry close ---")
        print(f"    events: {len(sub_d)} | hit within {max_hours}h: {hit_rate:.1f}% ({len(times)})")
        if len(times) > 0:
            print(f"    lead time (hours): mean={times.mean():.2f}  median={times.median():.2f}  "
                  f"p25={times.quantile(0.25):.2f}  p75={times.quantile(0.75):.2f}")
        print()

    # OKEx subset
    ex_ok = "OKEx"
    for d in thresholds:
        ev_ok = [e for e in events if e["exchange"] == ex_ok]
        if not ev_ok:
            continue
        # rebuild rows for OKEx only
        ok_rows = []
        for ev in ev_ok:
            ev_ts_ms = int(ev["timestamp"]) * 1000
            idx = int(np.searchsorted(price_ts, ev_ts_ms))
            if idx >= len(price_ts) - 1 or idx < 1:
                continue
            h = first_hit_hours(price_ts, lows, closes, ev_ts_ms, idx, d, max_bars, use_low)
            ok_rows.append({"hit": h is not None, "hit_hours": h})
        okdf = pd.DataFrame(ok_rows)
        if okdf.empty:
            continue
        hit_rate = okdf["hit"].mean() * 100
        times = okdf.loc[okdf["hit"], "hit_hours"].dropna()
        print(f"--- OKEx only: first >= {d}% drop ---")
        print(f"    events: {len(okdf)} | hit: {hit_rate:.1f}% ({len(times)})")
        if len(times) > 0:
            print(f"    lead time (h): mean={times.mean():.2f}  median={times.median():.2f}")
        print()


def main() -> None:
    events = load_events(min_btc=50, external_only=True)
    logger.info(f"Loaded {len(events)} inflow events (50+ BTC, external, exclusions applied)")
    df = fetch_historical_prices()
    logger.info(f"Price rows: {len(df)}")

    thresholds = [0.5, 1.0, 2.0]
    max_hours = 168  # 7d

    analyze(events, df, thresholds, max_hours=max_hours, use_low=True)
    print("\n--- Alternative: close-only (must close below threshold) ---\n")
    analyze(events, df, thresholds, max_hours=max_hours, use_low=False)

    # Symmetry: time to first +1% UP (short would lose) — same horizon
    print("\n=== Time to first +1% MOVE AGAINST short (rally from entry) [intrabar high] ===\n")
    price_ts = df["timestamp"].values.astype(np.int64)
    highs = df["high"].values.astype(np.float64)
    closes = df["close"].values.astype(np.float64)
    max_bars = int(np.ceil(168 / 4))

    rally_times = []
    drop_times = []
    for ev in events:
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx = int(np.searchsorted(price_ts, ev_ts_ms))
        if idx >= len(price_ts) - 1 or idx < 1:
            continue
        entry = float(closes[idx])
        thr_up = entry * 1.01
        thr_dn = entry * 0.99
        rh = None
        dh = None
        end = min(idx + max_bars + 1, len(closes))
        for j in range(idx + 1, end):
            if rh is None and float(highs[j]) >= thr_up:
                rh = max(0.0, (int(price_ts[j]) - ev_ts_ms) / 3600000.0)
            if dh is None and float(df["low"].values[j]) <= thr_dn:
                dh = max(0.0, (int(price_ts[j]) - ev_ts_ms) / 3600000.0)
            if rh is not None and dh is not None:
                break
        rally_times.append(rh)
        drop_times.append(dh)

    both = []
    for r, d in zip(rally_times, drop_times):
        if r is not None and d is not None:
            both.append((r, d, r < d))
        elif r is None and d is not None:
            both.append((float("inf"), d, False))
        elif r is not None and d is None:
            both.append((r, float("inf"), True))
        else:
            both.append(None)

    valid = [b for b in both if b is not None]
    first_rally_faster = sum(1 for b in valid if b[2] is False and b[0] != float("inf"))
    first_drop_faster = sum(1 for b in valid if b[2] is True)
    comparable = [b for b in valid if b[0] != float("inf") and b[1] != float("inf")]
    n_comp = len(comparable)
    if n_comp:
        r_wins = sum(1 for b in comparable if b[0] < b[1])
        d_wins = sum(1 for b in comparable if b[1] < b[0])
        ties = sum(1 for b in comparable if b[0] == b[1])
        print(f"Events with both 1% up and 1% down within 168h: {n_comp}")
        print(f"  Rally to +1% faster than dip to -1%: {r_wins} ({100*r_wins/n_comp:.1f}%)")
        print(f"  Dip to -1% faster: {d_wins} ({100*d_wins/n_comp:.1f}%)")
        print(f"  Same bar: {ties}")

    print("\n=== Interpretation (for report) ===")
    print("- Lead time uses 4h bars; sub-4h resolution is not available.")
    print("- 'Rational short' needs edge after fees/funding; prior backtest showed weak 24h edge.")
    print("- If median time to -1% is large but +1% rally comes first often, naive short is risky.")


if __name__ == "__main__":
    main()
