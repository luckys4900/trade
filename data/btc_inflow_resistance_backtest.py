# -*- coding: utf-8 -*-
"""
Backtest: short only when price touches pre-inflow resistance after a whale inflow.

Resistance = max(high) over [idx-lookback, idx) (4h bars), no lookahead.
Entry: first bar j > idx where high[j] >= resistance, fill at close[j] (market on touch bar).
Only consider events where close[idx] < resistance (room to rally into level).

Compares:
  (A) Resistance delayed short
  (B) Naive short at inflow close (same events)
  (C) Naive short at inflow (all matched events)

Usage:
    python data/btc_inflow_resistance_backtest.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
sys.path.insert(0, DATA_DIR)

from btc_inflow_backtest import fetch_historical_prices, load_events  # noqa: E402

logger = logging.getLogger("res_bt")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Round-trip cost assumption (taker-ish perp), in %
ROUND_TRIP_FEE_PCT = 0.10
HORIZONS_H = (24, 48, 72)


@dataclass
class TradeRow:
    tx: str
    exchange: str
    inflow_btc: float
    resistance: float
    inflow_close: float
    touch_bar: int
    hours_to_touch: float
    short_entry: float
    horizon_h: int
    spot_change_pct: float
    short_gross_pct: float
    short_net_pct: float


def find_resistance_touch(
    highs: np.ndarray,
    closes: np.ndarray,
    timestamps: np.ndarray,
    idx: int,
    lookback: int,
    max_wait_bars: int,
) -> Tuple[Optional[int], float]:
    """Return (touch_bar_index, resistance_level) or (None, 0)."""
    lo = max(0, idx - lookback)
    if lo >= idx:
        return None, 0.0
    res = float(np.max(highs[lo:idx]))
    if closes[idx] >= res:
        return None, res
    end = min(idx + 1 + max_wait_bars, len(highs))
    for j in range(idx + 1, end):
        if highs[j] >= res:
            return j, res
    return None, res


def forward_close(
    timestamps: np.ndarray,
    closes: np.ndarray,
    from_idx: int,
    horizon_h: int,
) -> Optional[float]:
    target_ts = int(timestamps[from_idx]) + horizon_h * 3600 * 1000
    fi = int(np.searchsorted(timestamps, target_ts))
    if fi >= len(closes):
        return None
    return float(closes[fi])


def run_backtest(
    events: List[dict],
    df: pd.DataFrame,
    lookback_bars: int,
    max_wait_bars: int,
) -> Tuple[List[TradeRow], Dict[str, object]]:
    highs = df["high"].values.astype(np.float64)
    closes = df["close"].values.astype(np.float64)
    ts = df["timestamp"].values.astype(np.int64)

    rows: List[TradeRow] = []

    matched_inflow = 0
    skipped_no_touch = 0
    skipped_already_at_res = 0

    for ev in events:
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx = int(np.searchsorted(ts, ev_ts_ms))
        if idx >= len(ts) - 2 or idx < 1:
            continue
        if idx < lookback_bars:
            continue

        matched_inflow += 1
        res = float(np.max(highs[idx - lookback_bars : idx]))
        ic = float(closes[idx])

        if ic >= res:
            skipped_already_at_res += 1
            continue

        touch_j, _ = find_resistance_touch(highs, closes, ts, idx, lookback_bars, max_wait_bars)
        if touch_j is None:
            skipped_no_touch += 1
            continue

        entry = float(closes[touch_j])
        hours_touch = (int(ts[touch_j]) - ev_ts_ms) / 3600000.0

        for h in HORIZONS_H:
            fut = forward_close(ts, closes, touch_j, h)
            if fut is None:
                continue
            chg = (fut - entry) / entry * 100.0
            short_g = -chg
            short_n = short_g - ROUND_TRIP_FEE_PCT
            rows.append(
                TradeRow(
                    tx=ev.get("tx_hash", "")[:16],
                    exchange=ev.get("exchange", ""),
                    inflow_btc=float(ev.get("inflow_btc", 0)),
                    resistance=res,
                    inflow_close=ic,
                    touch_bar=touch_j,
                    hours_to_touch=hours_touch,
                    short_entry=entry,
                    horizon_h=h,
                    spot_change_pct=chg,
                    short_gross_pct=short_g,
                    short_net_pct=short_n,
                )
            )

    meta = {
        "lookback_bars": lookback_bars,
        "max_wait_bars": max_wait_bars,
        "matched_inflow": matched_inflow,
        "skipped_already_at_res": skipped_already_at_res,
        "skipped_no_touch_within_window": skipped_no_touch,
        "resistance_trades_events": len(rows) // len(HORIZONS_H),
    }
    return rows, meta


def summarize_trades(rows: List[TradeRow], label: str) -> None:
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    if not rows:
        print("  (no trades)")
        return
    for h in HORIZONS_H:
        sub = [r for r in rows if r.horizon_h == h]
        if not sub:
            continue
        gross = np.array([r.short_gross_pct for r in sub])
        net = np.array([r.short_net_pct for r in sub])
        wins = gross > 0
        print(f"\n  Horizon {h}h  (n={len(sub)})")
        print(f"    Short gross:  mean={gross.mean():+.4f}%  median={np.median(gross):+.4f}%  "
              f"win%={100 * wins.mean():.1f}%")
        print(f"    Short net ({ROUND_TRIP_FEE_PCT}% RT fee):  mean={net.mean():+.4f}%  median={np.median(net):+.4f}%")
        print(f"    Worst / Best (gross): {gross.min():+.2f}% / {gross.max():+.2f}%")


def summarize_naive(naive: List[Dict], label: str) -> None:
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    if not naive:
        print("  (empty)")
        return
    for h in HORIZONS_H:
        sub = [x for x in naive if x["h"] == h]
        if not sub:
            continue
        gross = np.array([x["short_gross"] for x in sub])
        net = np.array([x["short_net"] for x in sub])
        print(f"\n  Horizon {h}h  (n={len(sub)})")
        print(f"    Short gross:  mean={gross.mean():+.4f}%  median={np.median(gross):+.4f}%  "
              f"win%={100 * (gross > 0).mean():.1f}%")
        print(f"    Short net:      mean={net.mean():+.4f}%  median={np.median(net):+.4f}%")


def touch_latency_stats(rows: List[TradeRow]) -> None:
    """Hours from inflow to resistance touch (once per event)."""
    seen = set()
    lat = []
    for r in rows:
        if r.horizon_h != 24:
            continue
        if r.tx in seen:
            continue
        seen.add(r.tx)
        lat.append(r.hours_to_touch)
    if not lat:
        return
    a = np.array(lat)
    print(f"\n  Time from inflow to resistance touch (first touch, h):")
    print(f"    mean={a.mean():.2f}  median={np.median(a):.2f}  p75={np.percentile(a, 75):.2f}")


def run_naive_all(events: List[dict], df: pd.DataFrame) -> List[Dict]:
    ts = df["timestamp"].values.astype(np.int64)
    closes = df["close"].values.astype(np.float64)
    out = []
    for ev in events:
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx = int(np.searchsorted(ts, ev_ts_ms))
        if idx >= len(ts) - 2 or idx < 1:
            continue
        ic = float(closes[idx])
        for h in HORIZONS_H:
            fut0 = forward_close(ts, closes, idx, h)
            if fut0 is None:
                continue
            chg0 = (fut0 - ic) / ic * 100.0
            out.append({"h": h, "short_gross": -chg0, "short_net": -chg0 - ROUND_TRIP_FEE_PCT})
    return out


def main() -> None:
    events = load_events(min_btc=50, external_only=True)
    df = fetch_historical_prices()
    logger.info(f"Events: {len(events)}  OHLCV rows: {len(df)}")

    # 42 bars * 4h = 168h lookback for resistance; 42 bars max wait = 168h
    lookback = 42
    max_wait = 42

    rows, meta = run_backtest(events, df, lookback_bars=lookback, max_wait_bars=max_wait)

    print("\n" + "#" * 70)
    print("# BTC Inflow / Touch Recent Resistance / Short (BACKTEST REPORT)")
    print("#" * 70)
    print(f"""
Definitions:
  - Resistance: max(high) over {lookback} x 4h bars BEFORE inflow candle (= ~7d lookback).
  - Inflow candle close must be STRICTLY below resistance (rally room).
  - First touch: first bar within {max_wait} x 4h (=168h) after inflow where high >= resistance.
  - Short entry: close of touch bar. Exit: first close at or after T+{HORIZONS_H}h (same method as inflow backtest).
  - Short PnL (gross): -(exit - entry) / entry * 100. Net: gross - {ROUND_TRIP_FEE_PCT}% round-trip fee.
""")

    print("--- Sample construction ---")
    for k, v in meta.items():
        print(f"  {k}: {v}")

    summarize_trades(rows, "(A) Resistance-touch short (only if touch within 168h)")
    touch_latency_stats(rows)

    # Rebuild naive for SAME events that had a touch (pairwise)
    # Extract unique tx from rows
    txs = {r.tx for r in rows}
    ev_touch = [e for e in events if e.get("tx_hash", "")[:16] in txs]
    naive_paired = []
    ts_arr = df["timestamp"].values.astype(np.int64)
    closes = df["close"].values.astype(np.float64)
    for ev in ev_touch:
        ev_ts_ms = int(ev["timestamp"]) * 1000
        idx = int(np.searchsorted(ts_arr, ev_ts_ms))
        if idx >= len(closes) - 2:
            continue
        ic = float(closes[idx])
        for h in HORIZONS_H:
            fut0 = forward_close(ts_arr, closes, idx, h)
            if fut0 is None:
                continue
            chg0 = (fut0 - ic) / ic * 100.0
            naive_paired.append({"h": h, "short_gross": -chg0, "short_net": -chg0 - ROUND_TRIP_FEE_PCT})

    summarize_naive(naive_paired, "(B) Naive short at INFLOW (same events as A, apple-to-apple)")

    naive_all = run_naive_all(events, df)
    summarize_naive(naive_all, "(C) Naive short at inflow (ALL events with valid price match)")

    # OKEx-only resistance strategy
    rows_ok = [r for r in rows if r.exchange == "OKEx"]
    summarize_trades(rows_ok, "(D) Resistance-touch short, OKEx inflows only")

    print("\n" + "=" * 70)
    print("CONCLUSION (read with caution)")
    print("=" * 70)
    print("""
- If (A) net mean > (B) net mean at same horizon, delayed entry at resistance adds EV vs shorting
  immediately on the same events.
- Resistance is a crude proxy (equal highs); real trading uses finer structure + stops.
- Survivorship: events that never reach resistance in 168h are excluded from (A).
- No guarantee of causality; overlapping macro regimes may dominate.
""")


if __name__ == "__main__":
    main()
