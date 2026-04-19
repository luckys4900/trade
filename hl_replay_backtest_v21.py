# -*- coding: utf-8 -*-
"""
Replay backtest on HL L2 + trades logs from hl_l2_logger.py.

Reads all part_*.parquet in a directory (or a single parquet), merges rows,
sorts by exchange time ex_ts, then simulates conservative execution:
  - CDS computed only from trades with ex_ts < current book ex_ts (no same-tick leak)
  - Signal on book update at T; entry mid at next book update strictly after T
  - TP/SL vs best bid/ask on subsequent books; if both hit in one update, SL first
  - Fixed notion add PnL (no absurd compounding); ATR proxy from rolling mid returns

Install:
  pip install pandas pyarrow numpy tqdm

Usage:
  python hl_replay_backtest_v21.py --log-dir data/raw/hl_btc_l2_chunks
"""
from __future__ import annotations

import argparse
import ast
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_log_frames(log_dir: Path, single: Optional[Path]) -> pd.DataFrame:
    paths: List[Path]
    if single is not None:
        paths = [single]
    else:
        paths = sorted(log_dir.glob("part_*.parquet"))
    if not paths:
        raise FileNotFoundError(f"No parquet files in {log_dir} (use --parquet path)")

    dfs = [pd.read_parquet(p) for p in tqdm(paths, desc="read_parquet")]
    df = pd.concat(dfs, ignore_index=True)
    df = df.sort_values("ex_ts").reset_index(drop=True)
    logger.info("loaded %s rows from %s files", len(df), len(paths))
    return df


def parse_book_row(row: pd.Series) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    bids = json.loads(row["bids_json"]) if isinstance(row["bids_json"], str) else row["bids_json"]
    asks = json.loads(row["asks_json"]) if isinstance(row["asks_json"], str) else row["asks_json"]
    if isinstance(bids, str):
        bids = ast.literal_eval(bids)
    if isinstance(asks, str):
        asks = ast.literal_eval(asks)
    return list(bids), list(asks)


def best_bid_ask(bids: List[Dict[str, Any]], asks: List[Dict[str, Any]]) -> Tuple[float, float]:
    if not bids or not asks:
        return float("nan"), float("nan")
    bb = float(bids[0]["px"])
    ba = float(asks[0]["px"])
    return bb, ba


def mid(bb: float, ba: float) -> float:
    return (bb + ba) * 0.5


def twobi_l5(bids: List[Dict[str, Any]], asks: List[Dict[str, Any]], n: int = 5) -> float:
    bid_vol = sum(float(x["sz"]) for x in bids[:n])
    ask_vol = sum(float(x["sz"]) for x in asks[:n])
    s = bid_vol + ask_vol
    if s <= 0:
        return 0.0
    return (bid_vol - ask_vol) / s


def micro_price_dev(bids: List[Dict[str, Any]], asks: List[Dict[str, Any]], n: int = 5) -> float:
    bid_vol = sum(float(x["sz"]) for x in bids[:n])
    ask_vol = sum(float(x["sz"]) for x in asks[:n])
    s = bid_vol + ask_vol
    if s <= 0 or not bids or not asks:
        return 0.0
    bb = float(bids[0]["px"])
    ba = float(asks[0]["px"])
    m = mid(bb, ba)
    mu = (ba * bid_vol + bb * ask_vol) / s
    return (mu - m) / (m + 1e-12)


def agg_flow(trades: List[Dict[str, Any]]) -> float:
    buy = sum(t["sz"] for t in trades if t["side"] == "B")
    sell = sum(t["sz"] for t in trades if t["side"] == "A")
    s = buy + sell
    if s <= 0:
        return 0.0
    return (buy - sell) / s


def cvd_signed_volume(trades: List[Dict[str, Any]]) -> float:
    return sum(t["sz"] if t["side"] == "B" else -t["sz"] for t in trades)


def compute_cds(book: Dict[str, Any], recent_trades: List[Dict[str, Any]], vol_spike: float) -> float:
    bids = book["bids"]
    asks = book["asks"]
    tw = twobi_l5(bids, asks, 5)
    af = agg_flow(recent_trades)
    mu_dev = micro_price_dev(bids, asks, 5)
    cvd = cvd_signed_volume(recent_trades)
    cvd_norm = cvd / (abs(cvd) + 1e-9)
    vs = min(vol_spike, 3.0)
    return (
        0.25 * tw
        + 0.30 * np.sign(af)
        + 0.20 * mu_dev
        + 0.15 * cvd_norm
        + 0.10 * np.sign(af) * vs
    )


@dataclass
class OpenTrade:
    direction: int
    entry: float
    entry_ex_ts: int
    tp: float
    sl: float
    tp_mult: float
    sl_mult: float
    atr: float


def rolling_atr_from_mids(mids: List[float], window: int = 30) -> float:
    if len(mids) < 2:
        return 0.0
    arr = np.array(mids[-window:], dtype=float)
    rets = np.diff(arr) / (arr[:-1] + 1e-12)
    return float(np.std(rets) * np.mean(arr)) if len(rets) else 0.0


def run_replay(
    df: pd.DataFrame,
    cds_threshold: float,
    trade_lookback_ms: int,
    tp_mult: float,
    sl_mult: float,
    max_hold_ms: int,
    notional: float,
    maker_roundtrip: float,
) -> Dict[str, float]:
    trade_buf: List[Dict[str, Any]] = []
    mids_hist: List[float] = []
    pending_signal: Optional[Tuple[int, int, float]] = None  # (dir, signal_ex_ts, cds_at_signal)
    open_pos: Optional[OpenTrade] = None
    trade_pnls: List[float] = []
    capital = 10_000.0

    trade_count_window = 60000
    trade_times: List[int] = []

    for idx in tqdm(range(len(df)), desc="replay"):
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
        mids_hist.append(m)
        if len(mids_hist) > 500:
            mids_hist = mids_hist[-500:]

        recent = [t for t in trade_buf if t["ex_ts"] < ex_ts]
        n_recent = len([t for t in trade_times if ex_ts - trade_count_window <= t < ex_ts])
        vol_spike = n_recent / 30.0 if n_recent else 0.0

        if open_pos is not None:
            ot = open_pos
            if ex_ts - ot.entry_ex_ts > max_hold_ms:
                exit_px = m
                pnl_pct = ot.direction * (exit_px - ot.entry) / (ot.entry + 1e-12)
                pnl_cash = notional * pnl_pct - notional * maker_roundtrip
                capital += pnl_cash
                trade_pnls.append(pnl_cash / notional)
                open_pos = None
            else:
                if ot.direction == 1:
                    hit_sl = bb <= ot.sl
                    hit_tp = ba >= ot.tp
                    if hit_sl:
                        exit_px = ot.sl
                    elif hit_tp:
                        exit_px = ot.tp
                    else:
                        exit_px = None
                else:
                    hit_sl = ba >= ot.sl
                    hit_tp = bb <= ot.tp
                    if hit_sl:
                        exit_px = ot.sl
                    elif hit_tp:
                        exit_px = ot.tp
                    else:
                        exit_px = None
                if exit_px is not None:
                    pnl_pct = ot.direction * (exit_px - ot.entry) / (ot.entry + 1e-12)
                    pnl_cash = notional * pnl_pct - notional * maker_roundtrip
                    capital += pnl_cash
                    trade_pnls.append(pnl_cash / notional)
                    open_pos = None

        if open_pos is not None:
            continue

        book_for_cds = {"bids": bids, "asks": asks}
        cds = compute_cds(book_for_cds, recent, vol_spike)

        if pending_signal is not None:
            direction, sig_ts, _cds = pending_signal
            if ex_ts > sig_ts:
                entry = m
                atr = rolling_atr_from_mids(mids_hist[:-1], 30)
                if atr <= 0:
                    atr = abs(ba - bb) * 5.0 + 1e-8
                tp_dist = tp_mult * atr
                sl_dist = sl_mult * atr
                if direction == 1:
                    tp = entry + tp_dist
                    sl = entry - sl_dist
                else:
                    tp = entry - tp_dist
                    sl = entry + sl_dist
                open_pos = OpenTrade(
                    direction=direction,
                    entry=entry,
                    entry_ex_ts=ex_ts,
                    tp=tp,
                    sl=sl,
                    tp_mult=tp_mult,
                    sl_mult=sl_mult,
                    atr=atr,
                )
                pending_signal = None
            continue

        vol_sum = sum(t["sz"] for t in recent)
        if vol_sum > 0:
            vwap = sum(t["px"] * t["sz"] for t in recent) / vol_sum
        else:
            vwap = m

        mu_dev = micro_price_dev(bids, asks, 5)
        long_ok = cds > cds_threshold and m < vwap and mu_dev > 0
        short_ok = cds < -cds_threshold and m > vwap and mu_dev < 0

        if long_ok:
            pending_signal = (1, ex_ts, cds)
        elif short_ok:
            pending_signal = (-1, ex_ts, cds)

    if not trade_pnls:
        return {
            "trades": 0.0,
            "win_rate_pct": 0.0,
            "expectancy_pct": 0.0,
            "total_pnl_usd": 0.0,
            "final_capital": capital,
        }

    arr = np.array(trade_pnls, dtype=float)
    return {
        "trades": float(len(arr)),
        "win_rate_pct": float((arr > 0).mean() * 100.0),
        "expectancy_pct": float(arr.mean() * 100.0),
        "total_pnl_usd": float(capital - 10_000.0),
        "final_capital": float(capital),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", type=Path, default=Path("data/raw/hl_btc_l2_chunks"))
    ap.add_argument("--parquet", type=Path, default=None, help="Single parquet file instead of directory")
    ap.add_argument("--cds-threshold", type=float, default=0.58)
    ap.add_argument("--lookback-ms", type=int, default=60_000)
    ap.add_argument("--tp-mult", type=float, default=3.4)
    ap.add_argument("--sl-mult", type=float, default=2.3)
    ap.add_argument("--max-hold-ms", type=int, default=900_000)
    ap.add_argument("--notional", type=float, default=20_000.0)
    ap.add_argument("--maker-roundtrip", type=float, default=0.0003)
    args = ap.parse_args()

    df = load_log_frames(args.log_dir, args.parquet)
    if len(df) < 30:
        logger.error("Too few rows (need ~30+); run hl_l2_logger.py longer to collect data.")
        return

    r = run_replay(
        df,
        cds_threshold=args.cds_threshold,
        trade_lookback_ms=args.lookback_ms,
        tp_mult=args.tp_mult,
        sl_mult=args.sl_mult,
        max_hold_ms=args.max_hold_ms,
        notional=args.notional,
        maker_roundtrip=args.maker_roundtrip,
    )
    logger.info("=== Replay result ===")
    for k, v in r.items():
        logger.info("%s: %s", k, v)
    pd.DataFrame([r]).to_csv("hl_replay_v21_result.csv", index=False)


if __name__ == "__main__":
    main()
