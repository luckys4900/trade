# -*- coding: utf-8 -*-
"""
L2 + trades replay backtest — v2.1 FULL (extends hl_replay_backtest_v21.py).

Adds vs base v21:
  - Dynamic ATR: TP/SL distances recomputed from rolling mid each book update
  - Trailing: after unrealized gain >= --trail-activate-pct, trail off peak/trough
  - Regime (entry only): skip if relative spread too wide or |CDS| above cap
  - Same causality: trades with ex_ts < book ex_ts; entry on next book after signal

Requires logs from hl_l2_logger.py (kind, ex_ts, bids_json, asks_json, ...).

Usage:
  python hl_replay_backtest_v21_full.py --log-dir data/raw/hl_btc_l2_chunks
  python hl_replay_backtest_v21_full.py ... --export-csv path/to/ofi_export.csv

Optional --export-csv: third-party order-flow CSV (see kronos_export_cds.py). Repo "Kronos"
in SYSTEM/kronos_predictor.py is a forecaster, not this export.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from tqdm import tqdm

from hl_replay_backtest_v21 import (
    compute_cds,
    load_log_frames,
    mid,
    parse_book_row,
    best_bid_ask,
    rolling_atr_from_mids,
    micro_price_dev,
)
from kronos_export_cds import (
    OrderflowExportLookup,
    build_lookup,
    compute_cds_from_export_row,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class OpenTradeFull:
    direction: int
    entry: float
    entry_ex_ts: int
    tp_mult: float
    sl_mult: float
    trail_activate_pct: float
    trail_pct: float
    trail_atr_mult: float
    best_extreme: float  # long: max favorable mid; short: min favorable mid
    trail_active: bool = False


def _tp_sl_prices(direction: int, entry: float, atr: float, tp_mult: float, sl_mult: float) -> Tuple[float, float]:
    tp_dist = tp_mult * atr
    sl_dist = sl_mult * atr
    if direction == 1:
        return entry + tp_dist, entry - sl_dist
    return entry - tp_dist, entry + sl_dist


def _log_span_days(df: pd.DataFrame) -> float:
    t0 = int(df["ex_ts"].min())
    t1 = int(df["ex_ts"].max())
    dt = t1 - t0
    # HL websocket "time" is typically ms (13 digits); fallback if ever seconds
    if t0 > 1_000_000_000_000:
        span_sec = max(dt / 1000.0, 1.0)
    else:
        span_sec = max(float(dt), 1.0)
    return span_sec / 86400.0


def run_replay_full(
    df: pd.DataFrame,
    cds_threshold: float,
    trade_lookback_ms: int,
    tp_mult: float,
    sl_mult: float,
    max_hold_ms: int,
    notional: float,
    maker_roundtrip: float,
    max_spread_rel: float,
    cds_abs_skip: float,
    trail_activate_pct: float,
    trail_pct: float,
    trail_atr_mult: float,
    atr_window: int,
    of_export_lookup: Optional[OrderflowExportLookup] = None,
) -> Dict[str, float]:
    trade_buf: List[Dict[str, Any]] = []
    mids_hist: List[float] = []
    pending_signal: Optional[Tuple[int, int, float]] = None
    open_pos: Optional[OpenTradeFull] = None
    trade_pnls: List[float] = []
    capital = 10_000.0
    equity_curve: List[float] = [capital]

    trade_count_window = 60_000
    trade_times: List[int] = []

    def close_trade(ot: OpenTradeFull, exit_px: float, ex_ts: int) -> None:
        nonlocal capital, open_pos
        pnl_pct = ot.direction * (exit_px - ot.entry) / (ot.entry + 1e-12)
        pnl_cash = notional * pnl_pct - notional * maker_roundtrip
        capital += pnl_cash
        trade_pnls.append(pnl_cash / notional)
        equity_curve.append(capital)
        open_pos = None

    for idx in tqdm(range(len(df)), desc="replay_full"):
        row = df.iloc[idx]
        ex_ts = int(row["ex_ts"])
        kind = row["kind"]

        if kind == "trade":
            trade_buf.append(
                {
                    "ex_ts": ex_ts,
                    "px": float(row["px"]),
                    "sz": float(row["sz"]),
                    "side": row["side"],
                }
            )
            trade_times.append(ex_ts)
            cutoff_t = ex_ts - trade_lookback_ms
            trade_buf = [t for t in trade_buf if t["ex_ts"] >= cutoff_t]
            trade_times = [t for t in trade_times if t >= ex_ts - trade_count_window]
            continue

        if kind != "l2Book":
            continue

        bids, asks = parse_book_row(row)
        if not bids or not asks:
            continue
        bb, ba = best_bid_ask(bids, asks)
        if not np.isfinite(bb) or not np.isfinite(ba):
            continue
        m = mid(bb, ba)
        spread_rel = (ba - bb) / (m + 1e-12)

        mids_hist.append(m)
        if len(mids_hist) > 500:
            mids_hist = mids_hist[-500:]

        recent = [t for t in trade_buf if t["ex_ts"] < ex_ts]
        n_recent = len([t for t in trade_times if ex_ts - trade_count_window <= t < ex_ts])
        vol_spike = n_recent / 30.0 if n_recent else 0.0
        atr = rolling_atr_from_mids(mids_hist[:-1], atr_window)
        if atr <= 0:
            atr = abs(ba - bb) * 5.0 + 1e-8

        if open_pos is not None:
            ot = open_pos
            if ex_ts - ot.entry_ex_ts > max_hold_ms:
                close_trade(ot, m, ex_ts)
                continue

            tp, sl = _tp_sl_prices(ot.direction, ot.entry, atr, ot.tp_mult, ot.sl_mult)

            dist_trail = max(trail_pct * ot.entry, trail_atr_mult * atr)

            if ot.direction == 1:
                unrealized = (m - ot.entry) / (ot.entry + 1e-12)
                if m > ot.best_extreme:
                    ot.best_extreme = m
                if unrealized >= trail_activate_pct:
                    ot.trail_active = True
                trail_stop_px = ot.best_extreme - dist_trail if ot.trail_active else float("-inf")

                hit_sl = bb <= sl
                hit_tp = ba >= tp
                hit_trail = ot.trail_active and bb <= trail_stop_px

                if hit_sl:
                    close_trade(ot, sl, ex_ts)
                elif hit_trail:
                    close_trade(ot, max(trail_stop_px, bb), ex_ts)
                elif hit_tp:
                    close_trade(ot, tp, ex_ts)
            else:
                unrealized = (ot.entry - m) / (ot.entry + 1e-12)
                if m < ot.best_extreme:
                    ot.best_extreme = m
                if unrealized >= trail_activate_pct:
                    ot.trail_active = True
                trail_stop_px = ot.best_extreme + dist_trail if ot.trail_active else float("inf")

                hit_sl = ba >= sl
                hit_tp = bb <= tp
                hit_trail = ot.trail_active and ba >= trail_stop_px

                if hit_sl:
                    close_trade(ot, sl, ex_ts)
                elif hit_trail:
                    close_trade(ot, min(trail_stop_px, ba), ex_ts)
                elif hit_tp:
                    close_trade(ot, tp, ex_ts)

            continue

        book_for_cds = {"bids": bids, "asks": asks}
        cds = compute_cds(book_for_cds, recent, vol_spike)
        if of_export_lookup is not None:
            kr = of_export_lookup.row_at_or_before(ex_ts)
            if kr is not None:
                cds_x = compute_cds_from_export_row(kr, vol_spike)
                if cds_x is not None:
                    cds = float(cds_x)

        if pending_signal is not None:
            direction, sig_ts, _ = pending_signal
            if ex_ts > sig_ts:
                entry = m
                if direction == 1:
                    extreme = entry
                else:
                    extreme = entry
                open_pos = OpenTradeFull(
                    direction=direction,
                    entry=entry,
                    entry_ex_ts=ex_ts,
                    tp_mult=tp_mult,
                    sl_mult=sl_mult,
                    trail_activate_pct=trail_activate_pct,
                    trail_pct=trail_pct,
                    trail_atr_mult=trail_atr_mult,
                    best_extreme=extreme,
                )
                pending_signal = None
            continue

        if spread_rel > max_spread_rel:
            continue
        if abs(cds) > cds_abs_skip:
            continue

        vol_sum = sum(t["sz"] for t in recent)
        vwap = sum(t["px"] * t["sz"] for t in recent) / vol_sum if vol_sum > 0 else m
        mu_dev = micro_price_dev(bids, asks, 5)
        long_ok = cds > cds_threshold and m < vwap and mu_dev > 0
        short_ok = cds < -cds_threshold and m > vwap and mu_dev < 0

        if long_ok:
            pending_signal = (1, ex_ts, cds)
        elif short_ok:
            pending_signal = (-1, ex_ts, cds)

    span_days = _log_span_days(df)
    eq = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    max_dd_pct = float(np.min((eq / peak - 1.0) * 100.0)) if len(eq) > 1 else 0.0

    if not trade_pnls:
        return {
            "log_span_days": float(span_days),
            "trades": 0.0,
            "trades_per_day": 0.0,
            "win_rate_pct": 0.0,
            "expectancy_pct": 0.0,
            "total_pnl_usd": 0.0,
            "final_capital": float(capital),
            "max_dd_pct": 0.0,
        }

    arr = np.array(trade_pnls, dtype=float)
    return {
        "log_span_days": float(span_days),
        "trades": float(len(arr)),
        "trades_per_day": float(len(arr) / max(span_days, 1e-9)),
        "win_rate_pct": float((arr > 0).mean() * 100.0),
        "expectancy_pct": float(arr.mean() * 100.0),
        "total_pnl_usd": float(capital - 10_000.0),
        "final_capital": float(capital),
        "max_dd_pct": max_dd_pct,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="HL L2 replay v2.1 FULL")
    ap.add_argument("--log-dir", type=Path, default=Path("data/raw/hl_btc_l2_chunks"))
    ap.add_argument("--parquet", type=Path, default=None)
    ap.add_argument("--cds-threshold", type=float, default=0.58)
    ap.add_argument("--lookback-ms", type=int, default=60_000)
    ap.add_argument("--tp-mult", type=float, default=3.4)
    ap.add_argument("--sl-mult", type=float, default=2.3)
    ap.add_argument("--max-hold-ms", type=int, default=900_000)
    ap.add_argument("--notional", type=float, default=20_000.0)
    ap.add_argument("--maker-roundtrip", type=float, default=0.0003)
    ap.add_argument("--max-spread-rel", type=float, default=0.0005, help="Skip entries if (ask-bid)/mid above this")
    ap.add_argument("--cds-abs-skip", type=float, default=2.5, help="Skip entries if abs(CDS) above this")
    ap.add_argument("--trail-activate-pct", type=float, default=0.002, help="Unrealized return to activate trail")
    ap.add_argument("--trail-pct", type=float, default=0.0015, help="Min trail distance as fraction of entry price")
    ap.add_argument("--trail-atr-mult", type=float, default=1.5)
    ap.add_argument("--atr-window", type=int, default=30)
    ap.add_argument(
        "--export-csv",
        type=Path,
        default=None,
        help="Optional dir or CSV of external OFI features (see kronos_export_cds.py). "
        "NOT the same as SYSTEM/kronos_predictor.py. Overrides CDS when row has twobi+af.",
    )
    args = ap.parse_args()

    df = load_log_frames(args.log_dir, args.parquet)
    if len(df) < 30:
        logger.error("Too few rows; collect more logs with hl_l2_logger.py")
        return

    of_lu: Optional[OrderflowExportLookup] = None
    if args.export_csv is not None:
        of_lu = build_lookup(args.export_csv)
        logger.info("Using external OFI export for CDS when twobi+af present: %s", args.export_csv)

    r = run_replay_full(
        df,
        cds_threshold=args.cds_threshold,
        trade_lookback_ms=args.lookback_ms,
        tp_mult=args.tp_mult,
        sl_mult=args.sl_mult,
        max_hold_ms=args.max_hold_ms,
        notional=args.notional,
        maker_roundtrip=args.maker_roundtrip,
        max_spread_rel=args.max_spread_rel,
        cds_abs_skip=args.cds_abs_skip,
        trail_activate_pct=args.trail_activate_pct,
        trail_pct=args.trail_pct,
        trail_atr_mult=args.trail_atr_mult,
        atr_window=args.atr_window,
        of_export_lookup=of_lu,
    )
    logger.info("=== Replay FULL result ===")
    for k, v in r.items():
        logger.info("%s: %s", k, v)
    pd.DataFrame([r]).to_csv("hl_replay_v21_full_result.csv", index=False)


if __name__ == "__main__":
    main()
