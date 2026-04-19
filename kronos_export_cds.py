# -*- coding: utf-8 -*-
"""
Optional **external order-flow export** → CDS (same weights as hl_replay_backtest_v21.compute_cds).

IMPORTANT (repo terminology):
  - This file is NOT `SYSTEM/kronos_predictor.py` (forecasting model used in live bot).
  - Use this when you have a **third-party** (or custom) OFI/MBO export as CSV and want
    replay backtests to use those features instead of recomputing from HL logs.

Expected usage from `hl_replay_backtest_v21_full.py`:
  --export-csv path/to/dir_or_file.csv

CSV columns (aliases accepted; first non-null wins):
  Timestamp (one of):
    ex_ts (int, ms) | timestamp (ISO or ms number) | time_ms
  Features (at least twobi + af recommended; others default 0):
    aggregated_imbalance, twobi_l5, twobi          → TWOBI_L5 [-1,1] approx
    orderflow_delta, agg_flow, af                → aggressive flow; sign() used if |x|>1 ok
    microprice_dev, micro_price_dev, mu_dev      → micro-price skew vs mid
    cvd_norm, cvd_normalized                     → normalized CVD contribution
    volume_spike, vol_spike                      → spike ratio (capped at 3 in formula)

If a row is missing required fields, replay falls back to log-derived `compute_cds`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_TS_CANDS = ["ex_ts", "timestamp", "time_ms", "ts", "time"]
_TW_CANDS = ["aggregated_imbalance", "twobi_l5", "twobi"]
_AF_CANDS = ["orderflow_delta", "agg_flow", "af"]
_MU_CANDS = ["microprice_dev", "micro_price_dev", "mu_dev"]
_CVD_CANDS = ["cvd_norm", "cvd_normalized"]
_VS_CANDS = ["volume_spike", "vol_spike"]


def _first_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def _to_ex_ts_ms(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        s = series.astype("float64")
        # Heuristic: 13-digit ms vs seconds
        med = float(s.median()) if len(s) else 0.0
        if med > 1e12:
            return s.astype("int64")
        if med > 1e9:
            return (s * 1000.0).astype("int64")
        return (s * 1000.0).astype("int64")
    return pd.to_datetime(series, utc=True, errors="coerce").astype("int64") // 1_000_000


def load_orderflow_export_csv(path: Path) -> pd.DataFrame:
    """Load one CSV file or concatenate all *.csv in a directory."""
    paths: List[Path]
    if path.is_dir():
        paths = sorted(path.glob("*.csv"))
        if not paths:
            raise FileNotFoundError(f"No CSV files in {path}")
    else:
        if not path.exists():
            raise FileNotFoundError(path)
        paths = [path]

    parts = [pd.read_csv(p) for p in paths]
    df = pd.concat(parts, ignore_index=True)
    ts_col = _first_col(df, _TS_CANDS)
    if ts_col is None:
        raise ValueError(f"Need one of timestamp columns: {_TS_CANDS}; got {list(df.columns)}")

    out = pd.DataFrame()
    out["ex_ts"] = _to_ex_ts_ms(df[ts_col])

    def pick(cands: List[str]) -> pd.Series:
        c = _first_col(df, cands)
        if c is None:
            return pd.Series(np.nan, index=df.index, dtype="float64")
        return pd.to_numeric(df[c], errors="coerce")

    out["twobi"] = pick(_TW_CANDS)
    out["af"] = pick(_AF_CANDS)
    out["mu_dev"] = pick(_MU_CANDS)
    out["cvd_norm"] = pick(_CVD_CANDS)
    out["vol_spike"] = pick(_VS_CANDS)

    out = out.sort_values("ex_ts").drop_duplicates(subset=["ex_ts"], keep="last")
    out = out.reset_index(drop=True)
    logger.info("orderflow export: %s rows, ex_ts [%s .. %s]", len(out), out["ex_ts"].iloc[0], out["ex_ts"].iloc[-1])
    return out


class OrderflowExportLookup:
    """Nearest feature row at or before exchange time (ms), no lookahead."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._ts = frame["ex_ts"].to_numpy(dtype=np.int64)
        self._frame = frame

    def row_at_or_before(self, ex_ts: int) -> Optional[pd.Series]:
        i = int(np.searchsorted(self._ts, ex_ts, side="right") - 1)
        if i < 0:
            return None
        return self._frame.iloc[i]


def compute_cds_from_export_row(s: pd.Series, vol_spike_replay: float) -> Optional[float]:
    """
    CDS from one export row (same weight layout as replay `compute_cds`).
    Returns None if twobi or af is missing — caller should use log-derived CDS.
    """
    tw = s.get("twobi")
    af = s.get("af")
    if tw is None or af is None or not (np.isfinite(tw) and np.isfinite(af)):
        return None
    mu = float(s["mu_dev"]) if "mu_dev" in s.index and np.isfinite(s["mu_dev"]) else 0.0
    cvd_n = s.get("cvd_norm", np.nan)
    if cvd_n is not None and np.isfinite(cvd_n):
        cvd_term = float(np.clip(float(cvd_n), -1.0, 1.0))
    else:
        cvd_term = 0.0
    vs_raw = s.get("vol_spike", np.nan)
    if vs_raw is not None and np.isfinite(vs_raw):
        vs = min(float(vs_raw), 3.0)
    else:
        vs = min(float(vol_spike_replay), 3.0)
    af_s = np.sign(float(af))
    return (
        0.25 * float(tw)
        + 0.30 * af_s
        + 0.20 * mu
        + 0.15 * cvd_term
        + 0.10 * af_s * vs
    )


def build_lookup(path: Path) -> OrderflowExportLookup:
    return OrderflowExportLookup(load_orderflow_export_csv(path))
