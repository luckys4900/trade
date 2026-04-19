# -*- coding: utf-8 -*-
"""
Evidence-based strategy report: deduplication, IS/OOS split, bootstrap CI,
placebo (no-inflow) comparison, concentration metrics.

Strategy tiers (unchanged economics from pro backtest):
  - EV1 "Core": Tier-A exchange + 50-1000 BTC + daily<MA200 + 4h<MA50 + ATR 1-5.5%
  - EV2 "Extended": Tier-B + same trend + ATR + RSI 35-70

Hold: 7 calendar days, net of 0.10% RT + 0.07% funding (perp assumption).

Usage:
    python data/btc_inflow_evidence_strategy_report.py
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
sys.path.insert(0, DATA_DIR)

from btc_inflow_backtest import fetch_historical_prices, load_events  # noqa: E402
from btc_inflow_backtest_daily import fetch_daily_ohlcv  # noqa: E402
from btc_inflow_strategy_pro_backtest import (  # noqa: E402
    ROUND_TRIP_FEE_PCT,
    FUNDING_7D_EST_PCT,
    HOLD_DAYS,
    TIER_A_EXCHANGES,
    TIER_B_EXCHANGES,
    build_daily_features,
    build_4h_ma50,
    get_daily_row,
    get_4h_row,
    DailyRow,
    FourHRow,
)

logger = logging.getLogger("evidence")
logging.basicConfig(level=logging.INFO, format="%(message)s")

RNG = np.random.default_rng(42)


def dedupe_events(events: List[dict], window_sec: int = 72 * 3600) -> List[dict]:
    """Merge clusters within window_sec; keep event with largest inflow_btc."""
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


def net_short_7d(
    ev_ts_ms: int,
    ts_d: np.ndarray,
    close_d: np.ndarray,
    idx_d: int,
) -> Optional[float]:
    entry = float(close_d[idx_d])
    target_ts_ms = ev_ts_ms + HOLD_DAYS * 24 * 3600 * 1000
    fut_idx = int(np.searchsorted(ts_d, target_ts_ms))
    if fut_idx >= len(close_d):
        return None
    fut = float(close_d[fut_idx])
    chg = (fut - entry) / entry * 100.0
    return -chg - ROUND_TRIP_FEE_PCT - FUNDING_7D_EST_PCT


def run_aligned(
    events: List[dict],
    dfeat: pd.DataFrame,
    feat4: pd.DataFrame,
    ts_d: np.ndarray,
    close_d: np.ndarray,
    ts_4h: np.ndarray,
    pred: Callable[..., bool],
) -> List[Tuple[dict, float]]:
    rows: List[Tuple[dict, float]] = []
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
        n = net_short_7d(ev_ts_ms, ts_d, close_d, idx_d)
        if n is not None:
            rows.append((ev, n))
    return rows


def pred_ev1(ev, idx_d, idx_4h, dr, h4):
    x = float(ev.get("inflow_btc", 0))
    if not (50.0 <= x < 1000.0):
        return False
    if ev.get("exchange") not in TIER_A_EXCHANGES:
        return False
    if not (dr.close < dr.ma200 and h4.close < h4.ma50):
        return False
    if not (1.0 <= dr.atr_pct <= 5.5):
        return False
    return True


def pred_ev2(ev, idx_d, idx_4h, dr, h4):
    x = float(ev.get("inflow_btc", 0))
    if not (50.0 <= x < 1000.0):
        return False
    if ev.get("exchange") not in TIER_B_EXCHANGES:
        return False
    if not (dr.close < dr.ma200 and h4.close < h4.ma50):
        return False
    if not (1.0 <= dr.atr_pct <= 6.0):
        return False
    if not (35.0 <= dr.rsi <= 70.0):
        return False
    return True


def pred_price_ev1(dr: DailyRow, h4: FourHRow) -> bool:
    """Same technical stack as EV1 without exchange/size (for placebo)."""
    if not (dr.close < dr.ma200 and h4.close < h4.ma50):
        return False
    if not (1.0 <= dr.atr_pct <= 5.5):
        return False
    return True


def bootstrap_mean_ci(
    a: np.ndarray,
    n_boot: int = 8000,
    ci: float = 0.95,
) -> Tuple[float, float, float]:
    if len(a) < 2:
        return float(np.mean(a)), float(np.mean(a)), float(np.mean(a))
    means = []
    for _ in range(n_boot):
        s = RNG.choice(a, size=len(a), replace=True)
        means.append(float(np.mean(s)))
    means.sort()
    lo = means[int((1 - ci) / 2 * n_boot)]
    hi = means[int((1 + ci) / 2 * n_boot)]
    return float(np.mean(a)), lo, hi


def topk_abs_share(a: np.ndarray, k: int = 5) -> float:
    aa = np.abs(a)
    if aa.sum() < 1e-12:
        return 0.0
    k = min(k, len(a))
    idx = np.argsort(aa)
    return float(aa[idx[-k:]].sum() / aa.sum())


def is_oos_split(
    aligned: List[Tuple[dict, float]],
    is_frac: float = 0.4,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Time-ordered: first is_frac = in-sample (report only), rest = OOS."""
    if not aligned:
        return np.array([]), np.array([]), np.array([]), np.array([])
    aligned = sorted(aligned, key=lambda x: int(x[0]["timestamp"]))
    rets = np.array([x[1] for x in aligned])
    n = len(rets)
    cut = max(1, int(n * is_frac))
    is_rets = rets[:cut]
    oos_rets = rets[cut:]
    return is_rets, oos_rets, rets, np.array([int(x[0]["timestamp"]) for x in aligned])


def placebo_no_inflow(
    dfeat: pd.DataFrame,
    feat4: pd.DataFrame,
    ts_d: np.ndarray,
    close_d: np.ndarray,
    ts_4h: np.ndarray,
    inflow_days: set,
    year: int = 2026,
    n_sample: int = 400,
) -> List[float]:
    """
    Random calendar days in `year` where technical EV1 passes but day NOT in inflow_days.
    """
    dt = pd.to_datetime(dfeat["datetime"], utc=True)
    candidates: List[int] = []
    for i in range(len(dfeat)):
        if dt.dt.year.iloc[i] != year:
            continue
        if i < 200:
            continue
        day = dt.dt.date.iloc[i]
        if day in inflow_days:
            continue
        dr = get_daily_row(dfeat, i)
        ev_ts_ms = int(ts_d[i])
        idx_4h = int(np.searchsorted(ts_4h, ev_ts_ms))
        if idx_4h >= len(ts_4h) - 1 or idx_4h < 50:
            continue
        h4 = get_4h_row(feat4, idx_4h)
        if dr is None or h4 is None:
            continue
        if not pred_price_ev1(dr, h4):
            continue
        candidates.append(i)

    if not candidates:
        return []
    pick = RNG.choice(len(candidates), size=min(n_sample, len(candidates)), replace=False)
    out = []
    for p in pick:
        i = candidates[p]
        ev_ts_ms = int(ts_d[i])
        n = net_short_7d(ev_ts_ms, ts_d, close_d, i)
        if n is not None:
            out.append(n)
    return out


def print_block(title: str, rets: np.ndarray) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    if len(rets) < 3:
        print(f"  n={len(rets)} (too few for inference)")
        return
    m, lo, hi = bootstrap_mean_ci(rets)
    wr = (rets > 0).mean() * 100
    print(f"  n={len(rets)}  win%={wr:.1f}%")
    print(f"  mean net %: {m:+.4f}%   bootstrap 95% CI: [{lo:+.4f}%, {hi:+.4f}%]")
    print(f"  median: {np.median(rets):+.4f}%  std: {rets.std():.4f}%")
    try:
        from scipy import stats

        tstat, pval = stats.ttest_1samp(rets, 0, alternative="greater")
        print(f"  one-sided t-test mean>0: p={pval:.4f}")
    except Exception:
        pass
    conc = topk_abs_share(rets, k=min(5, len(rets)))
    print(f"  concentration: share of |return| in largest 5 trades: {100*conc:.1f}%")


def main() -> None:
    raw = load_events(min_btc=50, external_only=True)
    ded = dedupe_events(raw, window_sec=72 * 3600)

    dfeat = build_daily_features(fetch_daily_ohlcv())
    feat4 = build_4h_ma50(fetch_historical_prices())
    ts_d = dfeat["timestamp"].values.astype(np.int64)
    close_d = dfeat["close"].values.astype(np.float64)
    ts_4h = feat4["timestamp"].values.astype(np.int64)

    inflow_days_2026 = set()
    for e in ded:
        if datetime.utcfromtimestamp(int(e["timestamp"])).year == 2026:
            inflow_days_2026.add(datetime.utcfromtimestamp(int(e["timestamp"])).date())

    print("#" * 70)
    print("# EVIDENCE STRATEGY REPORT (dedup + bootstrap + IS/OOS + placebo)")
    print("#" * 70)
    print(f"\n  Raw events: {len(raw)}  |  After 72h cluster dedup (max inflow kept): {len(ded)}")

    for name, pred in [
        ("EV1 Core (Tier-A + technicals)", pred_ev1),
        ("EV2 Extended (Tier-B + RSI band)", pred_ev2),
    ]:
        aligned = run_aligned(ded, dfeat, feat4, ts_d, close_d, ts_4h, pred)
        rets = np.array([x[1] for x in aligned])
        print_block(f"{name} - ALL (deduped events)", rets)

        is_r, oos_r, _, _ = is_oos_split(aligned, is_frac=0.4)
        print_block(f"{name} - IN-SAMPLE (first 40% by time)", is_r)
        print_block(f"{name} - OUT-OF-SAMPLE (last 60% by time)", oos_r)

    # Sensitivity: no dedup (overlapping events; inflates n, optimistic)
    aligned_raw = run_aligned(raw, dfeat, feat4, ts_d, close_d, ts_4h, pred_ev1)
    rets_raw = np.array([x[1] for x in aligned_raw])
    print_block("SENSITIVITY: EV1 on RAW events (no cluster dedup, overlapping risk)", rets_raw)
    is_r2, oos_r2, _, _ = is_oos_split(aligned_raw, is_frac=0.4)
    print_block("SENSITIVITY: EV1 OOS (raw events)", oos_r2)

    # Placebo
    pl = placebo_no_inflow(
        dfeat, feat4, ts_d, close_d, ts_4h, inflow_days_2026, year=2026, n_sample=300
    )
    if pl:
        pa = np.array(pl)
        print_block("PLACEBO: 2026 random NO-INFLOW days, same technical EV1 stack", pa)

    # Compare EV1 mean vs placebo mean
    aligned1 = run_aligned(ded, dfeat, feat4, ts_d, close_d, ts_4h, pred_ev1)
    r1 = np.array([x[1] for x in aligned1])
    pa = np.array(pl) if pl else np.array([])
    if len(r1) >= 3 and len(pa) >= 3:
        print("\n" + "=" * 70)
        print("SUMMARY (EV1 vs placebo)")
        print("=" * 70)
        print(f"  EV1 mean: {r1.mean():+.4f}%  (n={len(r1)})")
        print(f"  Placebo mean: {pa.mean():+.4f}%  (n={len(pa)})")
        print("  If EV1 mean >> placebo, inflow signal adds incremental edge (same tech filter).")

    print("\n" + "=" * 70)
    print("REPRODUCIBILITY GRADING (heuristic)")
    print("=" * 70)
    print("""
  A) Dedup reduces double-counting from same liquidation week.
  B) OOS positive mean with wide CI still allows failure in live trading.
  C) Placebo separates 'technical short in bear structure' vs 'inflow timing'.
  D) Multi-year inflow labels still required for full external validity.
""")


if __name__ == "__main__":
    main()
