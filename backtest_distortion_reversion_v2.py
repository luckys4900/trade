from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import math
from typing import Dict, List

import numpy as np
import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int  # +1 long, -1 short
    entry_price: float
    exit_price: float
    gross_return: float
    net_return: float
    reason: str


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr = pd.concat(
        [
            (high - low),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr.replace(0, np.nan))
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return adx.fillna(0.0)


def rolling_hurst(close: pd.Series, window: int = 100, lags: List[int] | None = None) -> pd.Series:
    if lags is None:
        lags = [2, 4, 8, 16, 32]

    values = close.to_numpy()
    hurst_vals = np.full(len(values), np.nan)

    for i in range(window, len(values)):
        segment = values[i - window : i]
        if np.any(segment <= 0):
            continue
        tau = []
        valid_lags = []
        for lag in lags:
            if lag >= len(segment):
                continue
            diff = segment[lag:] - segment[:-lag]
            std = np.std(diff)
            if std > 0:
                tau.append(std)
                valid_lags.append(lag)
        if len(tau) < 2:
            continue
        slope = np.polyfit(np.log(valid_lags), np.log(tau), 1)[0]
        hurst_vals[i] = float(slope)

    return pd.Series(hurst_vals, index=close.index).fillna(0.5)


def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    df = df.sort_values("timestamp").set_index("timestamp")
    return df.astype(float)


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ret_1"] = out["close"].pct_change()
    out["ret_3"] = out["close"].pct_change(3)

    out["atr_5m"] = (
        pd.concat(
            [
                out["high"] - out["low"],
                (out["high"] - out["close"].shift(1)).abs(),
                (out["low"] - out["close"].shift(1)).abs(),
            ],
            axis=1,
        )
        .max(axis=1)
        .ewm(alpha=1.0 / 14, adjust=False)
        .mean()
    )
    out["atr_ratio"] = out["atr_5m"] / out["atr_5m"].rolling(5).mean().replace(0, np.nan)

    tp = (out["high"] + out["low"] + out["close"]) / 3.0
    out["vwap_15"] = (tp * out["volume"]).rolling(3).sum() / out["volume"].rolling(3).sum()
    out["micro_dev_proxy"] = (out["close"] - out["vwap_15"]) / out["close"].replace(0, np.nan)

    out["flow_proxy"] = out["ret_1"].rolling(12).sum()
    out["obi_proxy"] = (out["close"] - out["close"].rolling(12).mean()) / out["close"].rolling(12).std()

    vol_1m_proxy = out["volume"]
    vol_30m_avg_proxy = out["volume"].rolling(6).mean()
    out["vol_spike"] = vol_1m_proxy / vol_30m_avg_proxy.replace(0, np.nan)

    out["adx"] = compute_adx(out, 14)
    out["hurst"] = rolling_hurst(out["close"], 100)
    bb_mid = out["close"].rolling(20).mean()
    bb_std = out["close"].rolling(20).std()
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std
    out["bbw"] = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)

    out["bbw_p75"] = out["bbw"].rolling(500).quantile(0.75)
    out["atr_p40"] = out["atr_5m"].rolling(500).quantile(0.40)
    out["atr_p85"] = out["atr_5m"].rolling(500).quantile(0.85)
    out["vol_med"] = out["volume"].rolling(500).median()

    # Composite Distortion Score (proxy version from OHLCV only)
    def squash(series: pd.Series, scale: float) -> pd.Series:
        return np.tanh(series / scale)

    out["cds"] = (
        0.25 * squash(out["obi_proxy"].fillna(0.0), 1.5)
        + 0.30 * squash(out["flow_proxy"].fillna(0.0), 0.01)
        + 0.20 * squash(-out["micro_dev_proxy"].fillna(0.0), 0.002)
        + 0.15 * np.sign(out["flow_proxy"].fillna(0.0)) * np.minimum(out["vol_spike"].fillna(0.0) / 3.0, 1.0)
        + 0.10 * np.sign(out["flow_proxy"].fillna(0.0)) * np.minimum(out["atr_ratio"].fillna(0.0) / 2.0, 1.0)
    )

    out["hour"] = out.index.hour
    return out.dropna()


def classify_regime(row: pd.Series) -> str:
    if row["adx"] > 35 and row["hurst"] > 0.55:
        return "STRONG_TREND"
    if (25 <= row["adx"] <= 35) or (0.45 <= row["hurst"] <= 0.55):
        return "WEAK_TREND"
    if row["adx"] < 25 and row["hurst"] < 0.45 and row["bbw"] < row["bbw_p75"]:
        return "RANGE"
    return "WEAK_TREND"


def run_backtest(df: pd.DataFrame) -> Dict[str, float]:
    tp = 0.0040
    sl = 0.0025
    time_stop_bars = 3  # 15 minutes on 5m bars
    fee_roundtrip = 0.00042  # 0.042%

    trades: List[Trade] = []
    equity = 10_000.0
    equity_curve = [equity]
    pos = 0
    entry_price = 0.0
    entry_idx = -1
    entry_time = None

    for i in range(1, len(df) - 1):
        row = df.iloc[i]
        regime = classify_regime(row)

        if pos == 0:
            in_active_hours = 4 <= int(row["hour"]) < 20
            atr_ok = row["atr_p40"] <= row["atr_5m"] <= row["atr_p85"]
            vol_ok = row["volume"] > (row["vol_med"] * 0.6)
            spread_proxy_ok = (row["high"] - row["low"]) / row["close"] <= 0.0010

            threshold = 0.65 if regime == "WEAK_TREND" else 0.55
            if regime == "STRONG_TREND":
                threshold = 999.0

            long_sig = row["cds"] > threshold and row["close"] < row["vwap_15"] and row["flow_proxy"] > 0
            short_sig = row["cds"] < -threshold and row["close"] > row["vwap_15"] and row["flow_proxy"] < 0

            if in_active_hours and atr_ok and vol_ok and spread_proxy_ok and (long_sig or short_sig):
                pos = 1 if long_sig else -1
                entry_price = float(row["close"])
                entry_idx = i
                entry_time = df.index[i]
            continue

        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        hold_bars = i - entry_idx
        exit_reason = ""
        exit_price = close

        if pos == 1:
            tp_price = entry_price * (1.0 + tp)
            sl_price = entry_price * (1.0 - sl)
            if high >= tp_price:
                exit_price = tp_price
                exit_reason = "TP"
            elif low <= sl_price:
                exit_price = sl_price
                exit_reason = "SL"
        else:
            tp_price = entry_price * (1.0 - tp)
            sl_price = entry_price * (1.0 + sl)
            if low <= tp_price:
                exit_price = tp_price
                exit_reason = "TP"
            elif high >= sl_price:
                exit_price = sl_price
                exit_reason = "SL"

        if not exit_reason and hold_bars >= time_stop_bars:
            exit_reason = "TIME_STOP"

        if exit_reason:
            gross_ret = ((exit_price / entry_price) - 1.0) * pos
            net_ret = gross_ret - fee_roundtrip
            equity *= 1.0 + net_ret
            trades.append(
                Trade(
                    entry_time=entry_time,
                    exit_time=df.index[i],
                    side=pos,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    gross_return=gross_ret,
                    net_return=net_ret,
                    reason=exit_reason,
                )
            )
            equity_curve.append(equity)
            pos = 0
            entry_price = 0.0
            entry_idx = -1
            entry_time = None

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

    logger.info("loading data: %s", data_path)
    raw = load_data(data_path)
    feat = prepare_features(raw)
    logger.info("rows(raw/features): %s / %s", len(raw), len(feat))

    result = run_backtest(feat)
    logger.info("========== Backtest Result (Proxy v2.0) ==========")
    for k, v in result.items():
        logger.info("%s: %.4f", k, v)

    pd.DataFrame([result]).to_csv("distortion_reversion_v2_backtest_report.csv", index=False)
    logger.info("saved: distortion_reversion_v2_backtest_report.csv")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("backtest failed: %s", exc)
        raise
