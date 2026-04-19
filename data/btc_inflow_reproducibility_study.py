# -*- coding: utf-8 -*-
"""
Trade counts, year split, and regime-based reproducibility for inflow short strategies.

- Reports n per strategy and per calendar year
- Defines "overheated then inflow" as proxy for user question (2026 rally + large inflow)
- Compares 7d short net in cold vs overheated regimes

Usage:
    python data/btc_inflow_reproducibility_study.py
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import Callable, Dict, List, Optional

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
)

logger = logging.getLogger("repro")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def one_trade_net(
    ev: dict,
    ts_d: np.ndarray,
    close_d: np.ndarray,
    pred,
    dfeat: pd.DataFrame,
    feat4: pd.DataFrame,
    ts_4h: np.ndarray,
) -> Optional[float]:
    ev_ts_ms = int(ev["timestamp"]) * 1000
    idx_d = int(np.searchsorted(ts_d, ev_ts_ms))
    if idx_d >= len(ts_d) - 1 or idx_d < 200:
        return None
    idx_4h = int(np.searchsorted(ts_4h, ev_ts_ms))
    if idx_4h >= len(ts_4h) - 1 or idx_4h < 50:
        return None
    dr = get_daily_row(dfeat, idx_d)
    h4 = get_4h_row(feat4, idx_4h)
    if dr is None or h4 is None:
        return None
    if not pred(ev, idx_d, idx_4h, dr, h4):
        return None
    entry = dr.close
    target_ts_ms = ev_ts_ms + HOLD_DAYS * 24 * 3600 * 1000
    fut_idx = int(np.searchsorted(ts_d, target_ts_ms))
    if fut_idx >= len(close_d):
        return None
    fut = float(close_d[fut_idx])
    chg = (fut - entry) / entry * 100.0
    return -chg - ROUND_TRIP_FEE_PCT - FUNDING_7D_EST_PCT


def naive_7d_net(ev: dict, ts_d: np.ndarray, close_d: np.ndarray, dfeat: pd.DataFrame) -> Optional[float]:
    ev_ts_ms = int(ev["timestamp"]) * 1000
    idx_d = int(np.searchsorted(ts_d, ev_ts_ms))
    if idx_d >= len(ts_d) - 1 or idx_d < 200:
        return None
    entry = float(close_d[idx_d])
    target_ts_ms = ev_ts_ms + HOLD_DAYS * 24 * 3600 * 1000
    fut_idx = int(np.searchsorted(ts_d, target_ts_ms))
    if fut_idx >= len(close_d):
        return None
    fut = float(close_d[fut_idx])
    chg = (fut - entry) / entry * 100.0
    return -chg - ROUND_TRIP_FEE_PCT - FUNDING_7D_EST_PCT


def ret_n_days(close: np.ndarray, idx: int, n: int) -> Optional[float]:
    if idx < n:
        return None
    a, b = float(close[idx - n]), float(close[idx])
    return (b - a) / a * 100.0


def classify_overheated(
    close_d: np.ndarray,
    dfeat: pd.DataFrame,
    idx_d: int,
    mode: str,
) -> bool:
    """Proxy for 'rally / overheated market' at inflow bar."""
    c = float(close_d[idx_d])
    r = dfeat.iloc[idx_d]
    ma200 = float(r["ma200_d"])
    ma50 = float(r["ma50_d"])
    rsi = float(r["rsi14_d"])
    r30 = ret_n_days(close_d, idx_d, 30)
    r90 = ret_n_days(close_d, idx_d, 90)

    if mode == "strict":
        return (
            c > ma200
            and rsi >= 62.0
            and (r30 is not None and r30 >= 10.0)
        )
    if mode == "medium":
        return (c > ma200) or (rsi >= 65.0) or (r30 is not None and r30 >= 15.0)
    if mode == "bull_price":
        return c > ma200 and c > ma50
    raise ValueError(mode)


def summarize_returns(name: str, rets: List[float]) -> None:
    print(f"\n  --- {name} ---")
    if len(rets) == 0:
        print("    n=0")
        return
    a = np.array(rets)
    print(f"    n={len(a)}  mean={a.mean():+.4f}%  median={np.median(a):+.4f}%  "
          f"win%={(a > 0).mean() * 100:.1f}%  std={a.std():.2f}%")


def main() -> None:
    events = load_events(min_btc=50, external_only=True)
    dfeat = build_daily_features(fetch_daily_ohlcv())
    feat4 = build_4h_ma50(fetch_historical_prices())
    ts_d = dfeat["timestamp"].values.astype(np.int64)
    close_d = dfeat["close"].values.astype(np.float64)
    ts_4h = feat4["timestamp"].values.astype(np.int64)

    # Year histogram (raw events)
    print("=" * 70)
    print("1) EVENT COUNTS BY CALENDAR YEAR (filtered 50+ BTC, external)")
    print("=" * 70)
    by_year: Dict[int, int] = {}
    for ev in events:
        y = datetime.utcfromtimestamp(ev["timestamp"]).year
        by_year[y] = by_year.get(y, 0) + 1
    for y in sorted(by_year.keys()):
        print(f"  {y}: {by_year[y]} events")
    print(f"  TOTAL: {len(events)}")
    print("\n  NOTE: If one year dominates, cross-year reproducibility is NOT demonstrated.")

    def base_size(ev: dict) -> bool:
        x = float(ev.get("inflow_btc", 0))
        return 50.0 <= x < 1000.0

    def f_s6_style(ev, idx_d, idx_4h, dr, h4):
        if not base_size(ev) or ev.get("exchange") not in TIER_A_EXCHANGES:
            return False
        if not (dr.close < dr.ma200 and h4.close < h4.ma50):
            return False
        if not (1.0 <= dr.atr_pct <= 5.5):
            return False
        return True

    def f_p1_style(ev, idx_d, idx_4h, dr, h4):
        if not base_size(ev) or ev.get("exchange") not in TIER_B_EXCHANGES:
            return False
        if not (dr.close < dr.ma200 and h4.close < h4.ma50):
            return False
        if not (1.0 <= dr.atr_pct <= 6.0):
            return False
        if not (35.0 <= dr.rsi <= 70.0):
            return False
        return True

    print("\n" + "=" * 70)
    print("2) TRADE COUNTS BY STRATEGY (after idx>=200 + valid 7d forward)")
    print("=" * 70)

    strategy_runners = [
        ("naive_7d (daily entry, no signal filter)", lambda ev: naive_7d_net(ev, ts_d, close_d, dfeat)),
        ("S6_style (Tier-A + MA200/4hMA50 + ATR)", lambda ev: one_trade_net(ev, ts_d, close_d, f_s6_style, dfeat, feat4, ts_4h)),
        ("P1_style (Tier-B + full pro relaxed)", lambda ev: one_trade_net(ev, ts_d, close_d, f_p1_style, dfeat, feat4, ts_4h)),
    ]

    for pname, runner in strategy_runners:
        per_year: Dict[int, int] = {}
        trades_total = 0
        for ev in events:
            net = runner(ev)
            if net is None:
                continue
            trades_total += 1
            y = datetime.utcfromtimestamp(ev["timestamp"]).year
            per_year[y] = per_year.get(y, 0) + 1

        print(f"\n  {pname}")
        print(f"    total trades: {trades_total}")
        for y in sorted(per_year.keys()):
            print(f"      {y}: {per_year[y]}")

    # Regime split: overheated vs cold (naive 7d)
    print("\n" + "=" * 70)
    print("3) REGIME PROXY: 'Overheated then large inflow' vs cold market")
    print("    (Used to address: 2026 rally + later large inflow, similar flow?)")
    print("=" * 70)

    for mode, label in [
        ("medium", "Medium: MA200 break OR RSI>=65 OR 30d return>=15%"),
        ("strict", "Strict: MA200 above AND RSI>=62 AND 30d return>=10%"),
        ("bull_price", "Bull price: close>MA200 and close>MA50"),
    ]:
        hot, cold = [], []
        hot_s6, cold_s6 = [], []
        for ev in events:
            ev_ts_ms = int(ev["timestamp"]) * 1000
            idx_d = int(np.searchsorted(ts_d, ev_ts_ms))
            if idx_d >= len(ts_d) - 1 or idx_d < 200:
                continue
            oh = classify_overheated(close_d, dfeat, idx_d, mode)
            n = naive_7d_net(ev, ts_d, close_d, dfeat)
            if n is None:
                continue
            (hot if oh else cold).append(n)
            # S6 requires cold-trend filters - on overheated days S6 often fails by design
            net6 = one_trade_net(ev, ts_d, close_d, f_s6_style, dfeat, feat4, ts_4h)
            if net6 is not None:
                (hot_s6 if oh else cold_s6).append(net6)

        print(f"\n  Mode: {label}")
        summarize_returns("Naive 7d short | OVERHEATED regime", hot)
        summarize_returns("Naive 7d short | COLD / non-overheated regime", cold)
        summarize_returns("S6_style | OVERHEATED (trades that still pass filter)", hot_s6)
        summarize_returns("S6_style | COLD", cold_s6)

    print("\n" + "=" * 70)
    print("4) REPRODUCIBILITY ASSESSMENT (honest)")
    print("=" * 70)
    print("""
  - Statistical: Need many IID trades across regimes and years. Here most events
    sit in ONE calendar year -> out-of-sample years are almost empty.
  - Economic: Pro strategy (S6/P1) EXCLUDES overheated bull charts by construction
    (short below MA200 etc.). If 2026 is a strong bull with price above MA200,
    the rule set may produce FEW OR ZERO trades - that is intentional risk control,
    not 'same flow as backtest'.
  - Forward scenario: If price rallies and THEN large inflows arrive, behaviour
    depends on whether filters still fire. Naive short may lose in bull overheated
    episodes; trend filters are meant to skip them - verify n in section 3.
""")


if __name__ == "__main__":
    main()
