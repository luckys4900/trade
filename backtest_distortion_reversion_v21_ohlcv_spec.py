"""
Distortion Reversion v2.1 — OHLCV-native spec (2026-04-13 design doc).

Five signals, composite score, ATR(14)-scaled TP/SL, ADX(10) regime + post-trend cooldown.
Keeps backtest_distortion_reversion_v2.py unchanged for v2.0 baseline comparison.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int
    entry_price: float
    exit_price: float
    gross_return: float
    net_return: float
    reason: str


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr = compute_atr(df, period).replace(0, np.nan)
    plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr)
    minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1.0 / period, adjust=False).mean().fillna(0.0)


def compute_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"]
    day = pd.Series(df.index.normalize(), index=df.index)
    cum_pv = pv.groupby(day).cumsum()
    cum_v = df["volume"].groupby(day).cumsum().replace(0, np.nan)
    return cum_pv / cum_v


def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    missing = {"timestamp", "open", "high", "low", "close", "volume"}.difference(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    df = df.sort_values("timestamp").set_index("timestamp")
    return df.astype(float)


def prepare_features_v21(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["atr_14"] = compute_atr(out, 14)
    out["adx_10"] = compute_adx(out, 10)
    out["rsi_8"] = compute_rsi(out["close"], 8)
    out["vwap_d"] = session_vwap(out)

    vol_sma20 = out["volume"].rolling(20, min_periods=20).mean()
    out["vol_ratio"] = out["volume"] / vol_sma20.replace(0, np.nan)

    bb_mid = out["close"].rolling(20, min_periods=20).mean()
    bb_std = out["close"].rolling(20, min_periods=20).std()
    out["bb_u"] = bb_mid + 2.0 * bb_std
    out["bb_l"] = bb_mid - 2.0 * bb_std

    dev = (out["close"] - out["vwap_d"]) / out["atr_14"].replace(0, np.nan)

    rsi = out["rsi_8"]
    rsi_term = np.where(
        rsi < 25.0,
        (25.0 - rsi) / 25.0,
        np.where(rsi > 75.0, -(rsi - 75.0) / 25.0, 0.0),
    )

    vwap_term = np.clip(-dev.to_numpy(dtype=float) / 1.5, -1.0, 1.0)
    vwap_term = np.where(np.isfinite(vwap_term), vwap_term, 0.0)

    bear_candle = out["close"] < out["open"]
    bull_candle = out["close"] > out["open"]
    vol_term = np.where(
        (out["vol_ratio"] > 2.0) & bear_candle,
        1.0,
        np.where((out["vol_ratio"] > 2.0) & bull_candle, -1.0, 0.0),
    )

    bb_long = (out["low"] < out["bb_l"]) & (out["close"] > out["bb_l"])
    bb_short = (out["high"] > out["bb_u"]) & (out["close"] < out["bb_u"])
    bb_term = np.where(bb_long, 1.0, np.where(bb_short, -1.0, 0.0))

    body = (out["close"] - out["open"]).abs()
    lo_w = np.minimum(out["open"], out["close"]) - out["low"]
    up_w = out["high"] - np.maximum(out["open"], out["close"])
    body_safe = body.replace(0, np.nan)
    wick_long = lo_w > 2.0 * body_safe
    wick_short = up_w > 2.0 * body_safe
    wick_term = np.where(wick_long.fillna(False), 1.0, np.where(wick_short.fillna(False), -1.0, 0.0))

    out["v21_score"] = (
        0.25 * rsi_term
        + 0.25 * vwap_term
        + 0.25 * vol_term
        + 0.15 * bb_term
        + 0.10 * wick_term
    )

    # Binary alignment (design doc: entry when at least 3 of 5 fire in same direction)
    rsi_long_b = (rsi < 25.0).astype(np.int32)
    rsi_short_b = (rsi > 75.0).astype(np.int32)
    vwap_long_b = (dev < -1.5).astype(np.int32)
    vwap_short_b = (dev > 1.5).astype(np.int32)
    vol_long_b = ((out["vol_ratio"] > 2.0) & bear_candle).astype(np.int32)
    vol_short_b = ((out["vol_ratio"] > 2.0) & bull_candle).astype(np.int32)
    bb_long_b = bb_long.astype(np.int32)
    bb_short_b = bb_short.astype(np.int32)
    wick_long_b = wick_long.fillna(False).astype(np.int32)
    wick_short_b = wick_short.fillna(False).astype(np.int32)
    out["long_n"] = rsi_long_b + vwap_long_b + vol_long_b + bb_long_b + wick_long_b
    out["short_n"] = rsi_short_b + vwap_short_b + vol_short_b + bb_short_b + wick_short_b
    out["hour"] = out.index.hour

    # Optional quality filters (same spirit as v2.0 script; not in prose spec but stabilizes bar quality)
    out["atr_p40"] = out["atr_14"].rolling(500, min_periods=100).quantile(0.40)
    out["atr_p85"] = out["atr_14"].rolling(500, min_periods=100).quantile(0.85)
    out["vol_med"] = out["volume"].rolling(500, min_periods=100).median()

    return out.dropna()


def run_backtest_v21(
    df: pd.DataFrame,
    score_threshold: float = 0.55,
    entry_rule: str = "min_aligned",
    min_aligned_signals: int = 3,
    tp_atr: float = 2.0,
    sl_atr: float = 1.5,
    time_stop_bars: int = 9,
    fee_roundtrip: float = 0.00042,
    adx_trend_level: float = 30.0,
    cooldown_bars: int = 6,
    active_hour_start: int = 4,
    active_hour_end: int = 20,
    use_vol_atr_filters: bool = True,
) -> Dict[str, float]:
    trades: List[Trade] = []
    equity = 10_000.0
    equity_curve: List[float] = [equity]
    cooldown_left = 0

    n = len(df)
    i = 1
    while i < n - 2:
        row = df.iloc[i]
        prev_adx_high = float(df.iloc[i - 1]["adx_10"]) >= adx_trend_level
        cur_adx_high = float(row["adx_10"]) >= adx_trend_level

        if cur_adx_high:
            i += 1
            continue

        if prev_adx_high and not cur_adx_high:
            cooldown_left = cooldown_bars

        if cooldown_left > 0:
            cooldown_left -= 1
            i += 1
            continue

        in_hours = active_hour_start <= int(row["hour"]) < active_hour_end
        spread_ok = (float(row["high"]) - float(row["low"])) / max(float(row["close"]), 1e-12) <= 0.0010
        atr_ok = True
        vol_ok = True
        if use_vol_atr_filters:
            atr_ok = float(row["atr_p40"]) <= float(row["atr_14"]) <= float(row["atr_p85"])
            vol_ok = float(row["volume"]) > float(row["vol_med"]) * 0.6

        sc = float(row["v21_score"])
        atr_sig = float(row["atr_14"])
        ln = int(row["long_n"])
        sn = int(row["short_n"])
        if entry_rule == "weighted":
            long_ok = sc > score_threshold
            short_ok = sc < -score_threshold
        elif entry_rule == "min_aligned":
            long_ok = ln >= min_aligned_signals and ln > sn
            short_ok = sn >= min_aligned_signals and sn > ln
        else:
            raise ValueError(f"unknown entry_rule: {entry_rule}")

        if not (in_hours and spread_ok and atr_ok and vol_ok and (long_ok or short_ok)):
            i += 1
            continue
        if not (atr_sig > 0 and np.isfinite(atr_sig)):
            i += 1
            continue

        side = 1 if long_ok else -1
        ei = i + 1
        if ei >= n:
            break
        entry_price = float(df.iloc[ei]["open"])
        entry_time = df.index[ei]
        tp_dist = tp_atr * atr_sig
        sl_dist = sl_atr * atr_sig

        exit_reason = ""
        exit_price = entry_price
        exit_time = entry_time
        last_j = min(time_stop_bars - 1, n - ei - 1)

        for j in range(last_j + 1):
            bar = df.iloc[ei + j]
            hi, lo, cl = float(bar["high"]), float(bar["low"]), float(bar["close"])
            exit_time = df.index[ei + j]
            if side == 1:
                sl_px = entry_price - sl_dist
                tp_px = entry_price + tp_dist
                if lo <= sl_px:
                    exit_price = sl_px
                    exit_reason = "SL"
                    break
                if hi >= tp_px:
                    exit_price = tp_px
                    exit_reason = "TP"
                    break
            else:
                sl_px = entry_price + sl_dist
                tp_px = entry_price - tp_dist
                if hi >= sl_px:
                    exit_price = sl_px
                    exit_reason = "SL"
                    break
                if lo <= tp_px:
                    exit_price = tp_px
                    exit_reason = "TP"
                    break
            exit_price = cl

        if not exit_reason:
            exit_reason = "TIME_STOP"
            exit_price = float(df.iloc[ei + last_j]["close"])
            exit_time = df.index[ei + last_j]

        gross_ret = ((exit_price / entry_price) - 1.0) * side
        net_ret = gross_ret - fee_roundtrip
        equity *= 1.0 + net_ret
        trades.append(
            Trade(
                entry_time=entry_time,
                exit_time=exit_time,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_return=gross_ret,
                net_return=net_ret,
                reason=exit_reason,
            )
        )
        equity_curve.append(equity)
        i = ei + last_j + 1

    if not trades:
        return {
            "trades": 0.0,
            "return_pct": 0.0,
            "max_dd_pct": 0.0,
            "win_rate_pct": 0.0,
            "expectancy_pct": 0.0,
            "expectancy_bps": 0.0,
            "sharpe": 0.0,
            "monthly_est_pct": 0.0,
            "tp_rate_pct": 0.0,
            "sl_rate_pct": 0.0,
            "time_stop_rate_pct": 0.0,
        }

    trade_returns = np.array([t.net_return for t in trades], dtype=float)
    days = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    win_rate = float(np.mean(trade_returns > 0))
    expectancy = float(np.mean(trade_returns))
    ret_std = float(np.std(trade_returns))
    trades_per_year = len(trades) / max(days / 365.0, 1e-9)
    sharpe = (expectancy / ret_std) * math.sqrt(trades_per_year) if ret_std > 0 else 0.0

    curve = np.array(equity_curve, dtype=float)
    running_max = np.maximum.accumulate(curve)
    dd = (curve - running_max) / running_max
    max_dd = float(np.min(dd))
    months = max(days / 30.0, 1.0)
    monthly_est = (curve[-1] / curve[0]) ** (1.0 / months) - 1.0
    reasons = pd.Series([t.reason for t in trades]).value_counts(normalize=True)

    return {
        "trades": float(len(trades)),
        "return_pct": (curve[-1] / curve[0] - 1.0) * 100.0,
        "max_dd_pct": max_dd * 100.0,
        "win_rate_pct": win_rate * 100.0,
        "expectancy_pct": expectancy * 100.0,
        "expectancy_bps": expectancy * 10_000.0,
        "sharpe": sharpe,
        "monthly_est_pct": monthly_est * 100.0,
        "tp_rate_pct": reasons.get("TP", 0.0) * 100.0,
        "sl_rate_pct": reasons.get("SL", 0.0) * 100.0,
        "time_stop_rate_pct": reasons.get("TIME_STOP", 0.0) * 100.0,
    }


def main() -> None:
    data_path = Path("data/raw/BTC_5m_hyperliquid.csv")
    if not data_path.exists():
        raise FileNotFoundError(f"data file not found: {data_path}")

    raw = load_data(data_path)
    feat = prepare_features_v21(raw)
    logger.info("rows(raw/features): %s / %s", len(raw), len(feat))

    rows = []
    for rule, label in [("min_aligned", "v21_min3"), ("weighted", "v21_weighted055")]:
        r_f = run_backtest_v21(feat, entry_rule=rule, use_vol_atr_filters=True)
        r_nf = run_backtest_v21(feat, entry_rule=rule, use_vol_atr_filters=False)
        logger.info("========== v2.1 %s | ATR/vol filters ON ==========", label)
        for k, v in r_f.items():
            logger.info("%s: %.4f", k, v)
        logger.info("========== v2.1 %s | filters OFF ==========", label)
        for k, v in r_nf.items():
            logger.info("%s: %.4f", k, v)
        rows.append({"variant": f"{label}_atr_vol_on", **r_f})
        rows.append({"variant": f"{label}_filters_off", **r_nf})

    out_csv = Path("distortion_reversion_v21_ohlcv_spec_report.csv")
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    logger.info("saved: %s", out_csv)


if __name__ == "__main__":
    main()
