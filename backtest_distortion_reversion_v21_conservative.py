# -*- coding: utf-8 -*-
"""
Distortion Reversion v2.1 Conservative (OHLCV proxy only).
- No pandas_ta (Python 3.10 compatible).
- Fixes in_position bug from pasted snippet (was never reset).
- Entry at next bar open after signal at bar i close (stricter than same-bar close).
- Forward simulation uses only bars i+1..i+3; SL before TP if both hit same bar.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def atr(df: pd.DataFrame, length: int) -> pd.Series:
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / max(length, 1), adjust=False).mean()


def adx_series(df: pd.DataFrame, length: int = 14) -> pd.Series:
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr_ = atr(df, length).replace(0, np.nan)
    plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / length, adjust=False).mean() / atr_)
    minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / length, adjust=False).mean() / atr_)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100.0
    return dx.ewm(alpha=1.0 / length, adjust=False).mean()


def vwap_rolling(df: pd.DataFrame, length: int = 3) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (tp * df["volume"]).rolling(length, min_periods=length).sum()
    vv = df["volume"].rolling(length, min_periods=length).sum().replace(0, np.nan)
    return pv / vv


def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["timestamp"]).set_index("timestamp")
    df = (
        df.resample("5min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    return df.astype(float)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["atr_5"] = atr(out, 5)
    out["adx"] = adx_series(out, 14)
    bb_mid = out["close"].rolling(20, min_periods=20).mean()
    bb_std = out["close"].rolling(20, min_periods=20).std()
    bb_u = bb_mid + 2.0 * bb_std
    bb_l = bb_mid - 2.0 * bb_std
    out["bbw"] = (bb_u - bb_l) / bb_mid.replace(0, np.nan)
    out["vwap_15"] = vwap_rolling(out, 3)

    out["ret"] = out["close"].pct_change()
    out["vol_spike"] = out["volume"] / out["volume"].rolling(30, min_periods=30).mean().replace(0, np.nan)
    out["proxy_obi"] = (out["close"] - out["open"]) / (out["high"] - out["low"] + 1e-8)
    out["proxy_af"] = out["ret"] * out["volume"].rolling(5, min_periods=5).mean()
    out["cvd"] = (out["proxy_af"] * np.sign(out["ret"].fillna(0.0))).rolling(60, min_periods=30).sum()
    cvd_mean = out["cvd"].rolling(120, min_periods=60).mean()
    cvd_std = out["cvd"].rolling(120, min_periods=60).std().replace(0, np.nan)
    out["cvd_norm"] = (out["cvd"] - cvd_mean) / cvd_std

    raw_cds = (
        0.25 * out["proxy_obi"].clip(-4, 4)
        + 0.30 * np.sign(out["proxy_af"].fillna(0.0))
        + 0.20 * ((out["close"] - out["vwap_15"]) / (out["atr_5"] + 1e-8))
        + 0.15 * out["cvd_norm"].fillna(0.0)
        + 0.10 * np.sign(out["proxy_af"].fillna(0.0)) * out["vol_spike"].clip(0, 4).fillna(0.0)
    )
    cds_mean = raw_cds.rolling(200, min_periods=100).mean()
    cds_std = raw_cds.rolling(200, min_periods=100).std().replace(0, np.nan)
    out["cds"] = (raw_cds - cds_mean) / cds_std.replace(0, 1.0)
    return out


def get_regime(row: pd.Series) -> str:
    if pd.isna(row["adx"]) or pd.isna(row["bbw"]):
        return "STRONG"
    if row["adx"] < 24 and row["bbw"] < 1.6:
        return "RANGE"
    if row["adx"] < 35:
        return "WEAK"
    return "STRONG"


def run_backtest(
    df: pd.DataFrame,
    cds_threshold: float = 0.58,
    start_hour: int = 6,
    end_hour: int = 18,
    tp_mult: float = 3.4,
    sl_mult: float = 2.3,
    forward_bars: int = 3,
    initial_capital: float = 10_000.0,
    leverage: float = 3.0,
    maker_fee: float = 0.00015,
) -> dict:
    feat = add_indicators(df)
    capital = initial_capital
    equity: list[float] = [capital]
    trade_pnls: list[float] = []

    n = len(feat)
    i = 200
    while i < n - forward_bars - 2:
        row = feat.iloc[i]
        ts = row.name
        if not (start_hour <= ts.hour <= end_hour):
            i += 1
            continue
        if get_regime(row) == "STRONG":
            i += 1
            continue

        # Signal at bar i (uses only data <= i). Entry next bar open.
        if row["cds"] > cds_threshold and float(row["close"]) < float(row["vwap_15"]):
            direction = 1
        elif row["cds"] < -cds_threshold and float(row["close"]) > float(row["vwap_15"]):
            direction = -1
        else:
            i += 1
            continue

        atr_i = float(row["atr_5"])
        if not np.isfinite(atr_i) or atr_i <= 0:
            i += 1
            continue

        entry = float(feat.iloc[i + 1]["open"])
        tp_dist = atr_i * tp_mult
        sl_dist = atr_i * sl_mult
        exit_price: float | None = None
        exit_bar_offset = forward_bars

        for j in range(1, forward_bars + 1):
            fut = feat.iloc[i + 1 + j]
            if direction == 1:
                tp_hit = float(fut["high"]) >= entry + tp_dist
                sl_hit = float(fut["low"]) <= entry - sl_dist
                if sl_hit:
                    exit_price = entry - sl_dist
                    exit_bar_offset = j
                    break
                if tp_hit:
                    exit_price = entry + tp_dist
                    exit_bar_offset = j
                    break
            else:
                tp_hit = float(fut["low"]) <= entry - tp_dist
                sl_hit = float(fut["high"]) >= entry + sl_dist
                if sl_hit:
                    exit_price = entry + sl_dist
                    exit_bar_offset = j
                    break
                if tp_hit:
                    exit_price = entry - tp_dist
                    exit_bar_offset = j
                    break

        if exit_price is None:
            exit_price = float(feat.iloc[i + 1 + forward_bars]["close"])
            exit_bar_offset = forward_bars

        pnl_pct = direction * (exit_price - entry) / entry
        net_pnl = pnl_pct * leverage - (maker_fee * 2.0)
        capital *= 1.0 + net_pnl
        if capital <= 0:
            break
        trade_pnls.append(net_pnl)
        equity.append(capital)
        i += 1 + exit_bar_offset

    if not trade_pnls:
        return {
            "total_return_pct": 0.0,
            "win_rate_pct": 0.0,
            "expectancy_pct": 0.0,
            "max_dd_pct": 0.0,
            "trades": 0,
            "trades_per_day": 0.0,
            "sharpe": 0.0,
        }

    arr = np.array(trade_pnls, dtype=float)
    eq = np.array(equity, dtype=float)
    dd = (eq / np.maximum.accumulate(eq)) - 1.0
    days = max((feat.index[-1] - feat.index[0]).total_seconds() / 86400.0, 1e-9)
    bars_per_day = 288.0

    return {
        "total_return_pct": float((capital / initial_capital - 1.0) * 100.0),
        "win_rate_pct": float((arr > 0).mean() * 100.0),
        "expectancy_pct": float(arr.mean() * 100.0),
        "max_dd_pct": float(dd.min() * 100.0),
        "trades": int(len(trade_pnls)),
        "trades_per_day": float(len(trade_pnls) / (len(feat) / bars_per_day)),
        "sharpe": float((arr.mean() / arr.std()) * np.sqrt(len(arr))) if arr.std() > 0 else 0.0,
    }


def threshold_sensitivity(feat_df: pd.DataFrame, thresholds: list[float]) -> pd.DataFrame:
    rows = []
    for th in thresholds:
        r = run_backtest(feat_df, cds_threshold=th)
        r["cds_threshold"] = th
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    path = Path("data/raw/BTC_5m_hyperliquid.csv")
    if not path.exists():
        raise FileNotFoundError(path)

    df = load_data(path)
    logger.warning(
        "OHLCV proxy only: results are NOT representative of L2 order flow. "
        "Use for sanity check vs absurd Sharpe only."
    )

    base = run_backtest(df, cds_threshold=0.58)
    logger.info("=== v2.1 Conservative (fixed) ===")
    for k, v in base.items():
        logger.info("%s: %s", k, v)

    sens = threshold_sensitivity(df, [0.40, 0.50, 0.58, 0.66, 0.80])
    sens.to_csv("v21_conservative_threshold_sensitivity.csv", index=False)
    pd.DataFrame([base]).to_csv("v21_conservative_base_result.csv", index=False)
    logger.info("saved: v21_conservative_base_result.csv, v21_conservative_threshold_sensitivity.csv")
    logger.info("threshold sensitivity:\n%s", sens.to_string(index=False))


if __name__ == "__main__":
    main()
