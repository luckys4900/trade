# -*- coding: utf-8 -*-
"""
EV1 inflow-short filter evaluation (shared by signal builder and tests).

Rules (from research):
  - 50 <= inflow_btc < 1000
  - exchange in Tier-A (OKEx, BitMEX, OKX)
  - external inflow only (sender_count > 0) — caller filters
  - daily: close < MA200, ATR% in [1.0, 5.5]
  - 4h: close < MA50 at event time
"""

from __future__ import annotations

import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_DATA = os.path.dirname(os.path.abspath(__file__))
if _DATA not in sys.path:
    sys.path.insert(0, _DATA)

from btc_inflow_strategy_pro_backtest import (  # noqa: E402
    get_4h_row,
    get_daily_row,
)

# Must match btc_inflow_backtest / pro backtest
TIER_A = frozenset({"OKEx", "BitMEX", "OKX"})
EXCLUDE = frozenset({"Tether", "Bitbank", "Coincheck"})


def dedupe_events(events: List[dict], window_sec: int = 72 * 3600) -> List[dict]:
    ev_sorted = sorted(events, key=lambda e: int(e["timestamp"]))
    out: List[dict] = []
    i = 0
    while i < len(ev_sorted):
        cluster = [ev_sorted[i]]
        j = i + 1
        t0 = int(ev_sorted[i]["timestamp"])
        while j < len(ev_sorted) and int(ev_sorted[j]["timestamp"]) - t0 <= window_sec:
            cluster.append(ev_sorted[j])
            j += 1
        best = max(cluster, key=lambda e: float(e.get("inflow_btc", 0)))
        out.append(best)
        i = j
    return out


def ev1_pred(ev: dict, idx_d: int, idx_4h: int, dr, h4) -> bool:
    x = float(ev.get("inflow_btc", 0))
    if not (50.0 <= x < 1000.0):
        return False
    if ev.get("exchange") not in TIER_A:
        return False
    if int(ev.get("sender_count", 0)) == 0:
        return False
    if not (dr.close < dr.ma200 and h4.close < h4.ma50):
        return False
    if not (1.0 <= dr.atr_pct <= 5.5):
        return False
    return True


def strength_from_age(event_ts: int, horizon_sec: int = 7 * 24 * 3600) -> float:
    """1.0 at t=0, linear decay to 0 at horizon."""
    now = int(time.time())
    age = max(0, now - int(event_ts))
    if age >= horizon_sec:
        return 0.0
    return 1.0 - age / float(horizon_sec)


def evaluate_latest_signal(
    events: List[dict],
    dfeat: pd.DataFrame,
    feat4: pd.DataFrame,
    ts_d: np.ndarray,
    ts_4h: np.ndarray,
    max_event_age_sec: int = 7 * 24 * 3600,
) -> Tuple[dict, Optional[dict]]:
    """
    Returns (output_dict, best_event_or_none).
    Picks newest deduped event within max_event_age that passes EV1.
    """
    now = int(time.time())
    raw = [
        e
        for e in events
        if e.get("exchange") not in EXCLUDE
        and float(e.get("inflow_btc", 0)) >= 50
        and int(e.get("sender_count", 0)) > 0
    ]
    ded = dedupe_events(raw)
    # newest first among recent
    candidates = [e for e in ded if now - int(e["timestamp"]) <= max_event_age_sec]
    candidates.sort(key=lambda e: int(e["timestamp"]), reverse=True)

    best: Optional[dict] = None
    for ev in candidates:
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
        if ev1_pred(ev, idx_d, idx_4h, dr, h4):
            best = ev
            break

    out: Dict = {
        "strategy": "EV1_INFLOW_SHORT",
        "valid": False,
        "signal": "NONE",
        "strength": 0.0,
        "reason": "",
        "last_event_ts": 0,
        "last_event_exchange": None,
        "last_event_inflow_btc": None,
        "evaluated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
    }

    if best is None:
        out["reason"] = "no_qualifying_inflow in window or EV1 filters failed"
        return out, None

    st = strength_from_age(int(best["timestamp"]), horizon_sec=max_event_age_sec)
    out["valid"] = st > 0
    out["signal"] = "SHORT_BIAS" if st > 0 else "NONE"
    out["strength"] = round(st, 4)
    out["last_event_ts"] = int(best["timestamp"])
    out["last_event_exchange"] = best.get("exchange")
    out["last_event_inflow_btc"] = float(best.get("inflow_btc", 0))
    out["reason"] = (
        f"EV1 pass: {out['last_event_exchange']} "
        f"{out['last_event_inflow_btc']:.2f} BTC, age-weighted strength={st:.2f}"
    )
    return out, best
