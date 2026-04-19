from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import ccxt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "backtest_results" / "btc_eth_pair_cache"
OUT_DIR = ROOT / "backtest_results"

START_DATE = "2023-01-01"
END_DATE = "2026-04-19"
TIMEFRAME = "1h"
INITIAL_CAPITAL = 100_000.0
RISK_PER_TRADE = 0.008
MAX_GROSS_LEVERAGE = 2.0
FEE_RATE = 0.0004
SLIPPAGE_RATE = 0.0002
MIN_IS_TRADES = 25
CORR_FILTER_MIN = 0.60
WF_SPLITS = 6

PARAM_GRID = {
    "beta_window": [72, 168],
    "z_window": [48, 72, 96],
    "z_entry": [1.5, 2.0, 2.5],
    "z_exit": [0.0, 0.5],
    "z_stop": [3.0, 3.5, 4.0],
    "max_hold": [12, 24, 48],
}


@dataclass
class Position:
    side: str
    entry_time: pd.Timestamp
    entry_eth: float
    entry_btc: float
    eth_qty: float
    btc_qty: float
    beta: float
    entry_z: float
    spread_std: float
    max_hold: int
    bars_held: int = 0


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    side: str
    exit_reason: str
    beta: float
    entry_z: float
    exit_z: float
    eth_qty: float
    btc_qty: float
    entry_eth: float
    exit_eth: float
    entry_btc: float
    exit_btc: float
    gross_pnl: float
    funding_pnl: float
    fee_cost: float
    slippage_cost: float
    net_pnl: float
    holding_bars: int


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("btc_eth_resid_pair")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def fetch_ohlcv_cached(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"{_safe_name(symbol)}_{timeframe}_ohlcv.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["timestamp"]).set_index("timestamp")
        return df.loc[start_date:end_date].copy()

    since_ms = exchange.parse8601(f"{start_date}T00:00:00Z")
    end_ms = exchange.parse8601(f"{end_date}T00:00:00Z")
    rows: list[list[float]] = []
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    logger.info("Fetching OHLCV for %s", symbol)

    while since_ms < end_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= since_ms:
            break
        since_ms = last_ts + tf_ms
        time.sleep(exchange.rateLimit / 1000.0)
        if len(batch) < 1000:
            break

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = (
        pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        .dt.tz_convert("UTC")
        .dt.tz_localize(None)
    )
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    df.to_csv(cache_path)
    return df.loc[start_date:end_date].copy()


def fetch_funding_cached(
    exchange: ccxt.Exchange,
    symbol: str,
    start_date: str,
    end_date: str,
    logger: logging.Logger,
) -> pd.Series:
    cache_path = CACHE_DIR / f"{_safe_name(symbol)}_funding.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["timestamp"])
        return pd.Series(df["rate"].values, index=df["timestamp"], name=f"{symbol}_funding")

    since_ms = exchange.parse8601(f"{start_date}T00:00:00Z")
    end_ms = exchange.parse8601(f"{end_date}T00:00:00Z")
    rows: list[dict[str, float]] = []
    logger.info("Fetching funding for %s", symbol)

    while since_ms < end_ms:
        batch = exchange.fetch_funding_rate_history(symbol, since=since_ms, limit=1000)
        if not batch:
            break
        for item in batch:
            rows.append(
                {
                    "timestamp": (
                        pd.to_datetime(int(item["timestamp"]), unit="ms", utc=True)
                        .tz_convert("UTC")
                        .tz_localize(None)
                    ),
                    "rate": float(item["fundingRate"]),
                }
            )
        last_ts = int(batch[-1]["timestamp"])
        if last_ts <= since_ms:
            break
        since_ms = last_ts + 1
        time.sleep(exchange.rateLimit / 1000.0)
        if len(batch) < 1000:
            break

    df = pd.DataFrame(rows).drop_duplicates("timestamp").sort_values("timestamp")
    df.to_csv(cache_path, index=False)
    return pd.Series(df["rate"].values, index=df["timestamp"], name=f"{symbol}_funding")


def prepare_dataset(logger: logging.Logger) -> pd.DataFrame:
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    exchange.load_markets()

    btc = fetch_ohlcv_cached(exchange, "BTC/USDT:USDT", TIMEFRAME, START_DATE, END_DATE, logger)
    eth = fetch_ohlcv_cached(exchange, "ETH/USDT:USDT", TIMEFRAME, START_DATE, END_DATE, logger)
    funding_btc = fetch_funding_cached(exchange, "BTC/USDT:USDT", START_DATE, END_DATE, logger)
    funding_eth = fetch_funding_cached(exchange, "ETH/USDT:USDT", START_DATE, END_DATE, logger)

    common = btc.index.intersection(eth.index)
    df = pd.DataFrame(index=common)
    for prefix, src in [("btc", btc), ("eth", eth)]:
        for col in ["open", "high", "low", "close", "volume"]:
            df[f"{prefix}_{col}"] = src.loc[common, col]

    df["btc_ret"] = np.log(df["btc_close"]).diff()
    df["eth_ret"] = np.log(df["eth_close"]).diff()
    df["funding_btc"] = funding_btc.reindex(common).fillna(0.0)
    df["funding_eth"] = funding_eth.reindex(common).fillna(0.0)
    return df.dropna().copy()


def build_features(df: pd.DataFrame, beta_window: int, z_window: int) -> pd.DataFrame:
    out = df.copy()
    cov = out["eth_ret"].rolling(beta_window).cov(out["btc_ret"])
    var = out["btc_ret"].rolling(beta_window).var()
    out["beta"] = (cov / var.replace(0.0, np.nan)).shift(1)
    out["spread"] = np.log(out["eth_close"]) - out["beta"] * np.log(out["btc_close"])
    out["spread_mean"] = out["spread"].rolling(z_window).mean().shift(1)
    out["spread_std"] = out["spread"].rolling(z_window).std().shift(1)
    out["zscore"] = (out["spread"] - out["spread_mean"]) / out["spread_std"].replace(0.0, np.nan)
    out["corr"] = out["eth_ret"].rolling(beta_window).corr(out["btc_ret"]).shift(1)
    return out.dropna().copy()


def iter_grid() -> Iterable[dict[str, float | int]]:
    for beta_window in PARAM_GRID["beta_window"]:
        for z_window in PARAM_GRID["z_window"]:
            for z_entry in PARAM_GRID["z_entry"]:
                for z_exit in PARAM_GRID["z_exit"]:
                    for z_stop in PARAM_GRID["z_stop"]:
                        for max_hold in PARAM_GRID["max_hold"]:
                            yield {
                                "beta_window": beta_window,
                                "z_window": z_window,
                                "z_entry": z_entry,
                                "z_exit": z_exit,
                                "z_stop": z_stop,
                                "max_hold": max_hold,
                            }


def compute_funding_pnl(position: Position, exit_time: pd.Timestamp, df: pd.DataFrame) -> float:
    funding_slice = df.loc[
        (df.index > position.entry_time) & (df.index <= exit_time),
        ["funding_btc", "funding_eth"],
    ]
    if funding_slice.empty:
        return 0.0

    eth_notional = position.eth_qty * position.entry_eth
    btc_notional = position.btc_qty * position.entry_btc

    if position.side == "LONG_SPREAD":
        eth_sign = 1.0
        btc_sign = -1.0
    else:
        eth_sign = -1.0
        btc_sign = 1.0

    eth_funding = float((-eth_sign * eth_notional * funding_slice["funding_eth"]).sum())
    btc_funding = float((-btc_sign * btc_notional * funding_slice["funding_btc"]).sum())
    return eth_funding + btc_funding


def calc_trade(
    position: Position,
    exit_time: pd.Timestamp,
    exit_reason: str,
    exit_z: float,
    row: pd.Series,
    df: pd.DataFrame,
) -> Trade:
    exit_eth = float(row["eth_open"])
    exit_btc = float(row["btc_open"])

    if position.side == "LONG_SPREAD":
        gross_pnl = (
            position.eth_qty * (exit_eth - position.entry_eth)
            - position.btc_qty * (exit_btc - position.entry_btc)
        )
    else:
        gross_pnl = (
            -position.eth_qty * (exit_eth - position.entry_eth)
            + position.btc_qty * (exit_btc - position.entry_btc)
        )

    funding_pnl = compute_funding_pnl(position, exit_time, df)
    open_notional = position.eth_qty * position.entry_eth + position.btc_qty * position.entry_btc
    close_notional = position.eth_qty * exit_eth + position.btc_qty * exit_btc
    fee_cost = (open_notional + close_notional) * FEE_RATE
    slippage_cost = (open_notional + close_notional) * SLIPPAGE_RATE
    net_pnl = gross_pnl + funding_pnl - fee_cost - slippage_cost

    return Trade(
        entry_time=str(position.entry_time),
        exit_time=str(exit_time),
        side=position.side,
        exit_reason=exit_reason,
        beta=position.beta,
        entry_z=position.entry_z,
        exit_z=exit_z,
        eth_qty=position.eth_qty,
        btc_qty=position.btc_qty,
        entry_eth=position.entry_eth,
        exit_eth=exit_eth,
        entry_btc=position.entry_btc,
        exit_btc=exit_btc,
        gross_pnl=float(gross_pnl),
        funding_pnl=float(funding_pnl),
        fee_cost=float(fee_cost),
        slippage_cost=float(slippage_cost),
        net_pnl=float(net_pnl),
        holding_bars=position.bars_held,
    )


def run_backtest(
    feature_df: pd.DataFrame,
    params: dict[str, float | int],
    capital: float,
) -> tuple[pd.DataFrame, pd.Series]:
    trades: list[Trade] = []
    equity = capital
    equity_points: list[tuple[pd.Timestamp, float]] = []
    position: Position | None = None

    timestamps = list(feature_df.index)
    for i in range(len(timestamps) - 1):
        ts = timestamps[i]
        next_ts = timestamps[i + 1]
        row = feature_df.iloc[i]
        next_row = feature_df.iloc[i + 1]

        if position is not None:
            position.bars_held += 1
            adverse_z = float(row["zscore"])
            exit_reason = None
            if position.side == "LONG_SPREAD":
                if adverse_z >= float(params["z_stop"]):
                    exit_reason = "STOP_LOSS"
                elif adverse_z >= -float(params["z_exit"]):
                    exit_reason = "MEAN_REVERT"
            else:
                if adverse_z <= -float(params["z_stop"]):
                    exit_reason = "STOP_LOSS"
                elif adverse_z <= float(params["z_exit"]):
                    exit_reason = "MEAN_REVERT"

            if position.bars_held >= int(params["max_hold"]) and exit_reason is None:
                exit_reason = "TIME_STOP"

            if exit_reason is not None:
                trade = calc_trade(position, next_ts, exit_reason, float(row["zscore"]), next_row, feature_df)
                equity += trade.net_pnl
                trades.append(trade)
                equity_points.append((next_ts, equity))
                position = None
                continue

        if position is not None:
            continue

        if float(row["corr"]) < CORR_FILTER_MIN:
            continue

        entry_z = float(row["zscore"])
        if abs(entry_z) > float(params["z_stop"]):
            continue

        side = None
        if entry_z <= -float(params["z_entry"]):
            side = "LONG_SPREAD"
        elif entry_z >= float(params["z_entry"]):
            side = "SHORT_SPREAD"
        if side is None:
            continue

        spread_std = float(row["spread_std"])
        stop_delta = (float(params["z_stop"]) - abs(entry_z)) * spread_std
        if stop_delta <= 0 or np.isnan(stop_delta):
            continue

        risk_cash = equity * RISK_PER_TRADE
        base_notional = risk_cash / stop_delta
        max_leg_notional = equity * MAX_GROSS_LEVERAGE / (1.0 + abs(float(row["beta"])))
        leg_notional = min(base_notional, max_leg_notional)
        if leg_notional <= 0:
            continue

        beta = abs(float(row["beta"]))
        entry_eth = float(next_row["eth_open"])
        entry_btc = float(next_row["btc_open"])
        eth_qty = leg_notional / entry_eth
        btc_qty = (leg_notional * beta) / entry_btc
        if eth_qty <= 0 or btc_qty <= 0:
            continue

        position = Position(
            side=side,
            entry_time=next_ts,
            entry_eth=entry_eth,
            entry_btc=entry_btc,
            eth_qty=float(eth_qty),
            btc_qty=float(btc_qty),
            beta=float(row["beta"]),
            entry_z=entry_z,
            spread_std=spread_std,
            max_hold=int(params["max_hold"]),
        )

    trade_df = pd.DataFrame([asdict(t) for t in trades])
    equity_curve = pd.Series(
        [x[1] for x in equity_points],
        index=[x[0] for x in equity_points],
        dtype=float,
        name="equity",
    )
    return trade_df, equity_curve


def calc_metrics(trade_df: pd.DataFrame, equity_curve: pd.Series, capital: float) -> dict[str, float | int | bool]:
    if trade_df.empty:
        return {
            "total_pnl": 0.0,
            "total_return_pct": 0.0,
            "n_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
            "sharpe": 0.0,
            "avg_hold_hours": 0.0,
            "t_stat": 0.0,
            "p_value": 1.0,
            "significant": False,
            "final_equity": capital,
        }

    pnls = trade_df["net_pnl"].to_numpy(dtype=float)
    wins = pnls[pnls > 0]
    losses = np.abs(pnls[pnls < 0])
    win_rate = float((pnls > 0).mean() * 100.0)
    profit_factor = float(wins.sum() / losses.sum()) if len(losses) and losses.sum() > 0 else 0.0

    if equity_curve.empty:
        equity_curve = pd.Series([capital + pnls.sum()], dtype=float)
    peak = equity_curve.cummax()
    dd = (equity_curve / peak - 1.0) * 100.0
    max_dd_pct = float(dd.min()) if not dd.empty else 0.0

    returns = equity_curve.diff().dropna()
    sharpe = 0.0
    if len(returns) > 1 and returns.std(ddof=0) > 0:
        sharpe = float(returns.mean() / returns.std(ddof=0) * np.sqrt(24 * 365))

    t_stat = 0.0
    p_value = 1.0
    if len(pnls) > 1 and np.std(pnls, ddof=1) > 0:
        t_stat = float(np.mean(pnls) / (np.std(pnls, ddof=1) / np.sqrt(len(pnls))))
        try:
            from scipy import stats as sp_stats

            p_value = float(sp_stats.ttest_1samp(pnls, 0.0).pvalue)
        except Exception:
            p_value = 1.0

    return {
        "total_pnl": float(pnls.sum()),
        "total_return_pct": float(pnls.sum() / capital * 100.0),
        "n_trades": int(len(trade_df)),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_dd_pct": max_dd_pct,
        "sharpe": sharpe,
        "avg_hold_hours": float(trade_df["holding_bars"].mean() if "holding_bars" in trade_df else 0.0),
        "t_stat": t_stat,
        "p_value": p_value,
        "significant": bool(p_value < 0.05),
        "final_equity": float(capital + pnls.sum()),
    }


def score_is_metrics(metrics: dict[str, float | int | bool]) -> float:
    if int(metrics["n_trades"]) < MIN_IS_TRADES:
        return -1e9
    if float(metrics["profit_factor"]) <= 0:
        return -1e9
    return (
        float(metrics["profit_factor"]) * 100.0
        + float(metrics["total_return_pct"])
        + float(metrics["sharpe"]) * 10.0
        - abs(float(metrics["max_dd_pct"])) * 2.0
    )


def run_walk_forward(df: pd.DataFrame, logger: logging.Logger) -> dict[str, object]:
    n = len(df)
    split_size = n // WF_SPLITS
    split_results: list[dict[str, object]] = []
    all_oos_trades: list[pd.DataFrame] = []
    all_oos_eq: list[pd.Series] = []
    param_history: list[dict[str, float | int]] = []

    for split_idx in range(2, WF_SPLITS):
        is_end = split_idx * split_size
        oos_end = min((split_idx + 1) * split_size, n)
        if oos_end <= is_end:
            continue

        is_df = df.iloc[:is_end].copy()
        oos_df = df.iloc[is_end:oos_end].copy()

        best_score = -1e18
        best_params: dict[str, float | int] | None = None
        best_is_metrics: dict[str, float | int | bool] | None = None

        for params in iter_grid():
            feat_is = build_features(is_df, int(params["beta_window"]), int(params["z_window"]))
            trades_is, eq_is = run_backtest(feat_is, params, INITIAL_CAPITAL)
            metrics_is = calc_metrics(trades_is, eq_is, INITIAL_CAPITAL)
            score = score_is_metrics(metrics_is)
            if score > best_score:
                best_score = score
                best_params = params
                best_is_metrics = metrics_is

        if best_params is None or best_is_metrics is None:
            continue

        feat_oos = build_features(oos_df, int(best_params["beta_window"]), int(best_params["z_window"]))
        trades_oos, eq_oos = run_backtest(feat_oos, best_params, INITIAL_CAPITAL)
        metrics_oos = calc_metrics(trades_oos, eq_oos, INITIAL_CAPITAL)

        split_results.append(
            {
                "split": split_idx,
                "params": best_params,
                "is_metrics": best_is_metrics,
                "oos_metrics": metrics_oos,
            }
        )
        param_history.append(best_params)
        if not trades_oos.empty:
            all_oos_trades.append(trades_oos)
        if not eq_oos.empty:
            all_oos_eq.append(eq_oos)

        logger.info(
            "Split %d | IS PF %.2f N %d -> OOS PF %.2f N %d Return %.2f%%",
            split_idx,
            float(best_is_metrics["profit_factor"]),
            int(best_is_metrics["n_trades"]),
            float(metrics_oos["profit_factor"]),
            int(metrics_oos["n_trades"]),
            float(metrics_oos["total_return_pct"]),
        )

    combined_trades = pd.concat(all_oos_trades, ignore_index=True) if all_oos_trades else pd.DataFrame()
    combined_eq = pd.concat(all_oos_eq).sort_index() if all_oos_eq else pd.Series(dtype=float)
    combined_metrics = calc_metrics(combined_trades, combined_eq, INITIAL_CAPITAL)
    return {
        "split_results": split_results,
        "param_history": param_history,
        "oos_trades": combined_trades,
        "oos_equity": combined_eq,
        "oos_metrics": combined_metrics,
    }


def adoption_checks(metrics: dict[str, float | int | bool], split_results: list[dict[str, object]]) -> dict[str, bool]:
    pf_ok = float(metrics["profit_factor"]) > 1.20
    trades_ok = int(metrics["n_trades"]) >= 80
    sharpe_ok = float(metrics["sharpe"]) > 1.0
    dd_ok = abs(float(metrics["max_dd_pct"])) < 15.0
    t_ok = bool(metrics["significant"])
    split_pf_ok = sum(
        1 for x in split_results if float(x["oos_metrics"]["profit_factor"]) > 1.0
    ) >= max(1, len(split_results) // 2)
    return {
        "oos_pf_gt_1_20": pf_ok,
        "oos_trades_ge_80": trades_ok,
        "oos_sharpe_gt_1": sharpe_ok,
        "max_dd_lt_15pct": dd_ok,
        "t_test_significant": t_ok,
        "majority_splits_pf_gt_1": split_pf_ok,
    }


def main() -> None:
    ensure_dirs()
    logger = setup_logger()
    logger.info("Preparing BTC/ETH residual pair dataset")
    df = prepare_dataset(logger)
    logger.info("Dataset rows: %d | period: %s -> %s", len(df), df.index.min(), df.index.max())

    wf = run_walk_forward(df, logger)
    metrics = wf["oos_metrics"]
    checks = adoption_checks(metrics, wf["split_results"])
    adopt = all(checks.values())

    result_payload = {
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "timeframe": TIMEFRAME,
            "initial_capital": INITIAL_CAPITAL,
            "risk_per_trade": RISK_PER_TRADE,
            "max_gross_leverage": MAX_GROSS_LEVERAGE,
            "fee_rate": FEE_RATE,
            "slippage_rate": SLIPPAGE_RATE,
            "corr_filter_min": CORR_FILTER_MIN,
            "wf_splits": WF_SPLITS,
        },
        "oos_metrics": metrics,
        "checks": checks,
        "adopt": adopt,
        "split_results": wf["split_results"],
    }

    with open(OUT_DIR / "btc_eth_residual_pair_results.json", "w", encoding="utf-8") as handle:
        json.dump(result_payload, handle, indent=2, default=str)
    wf["oos_trades"].to_csv(OUT_DIR / "btc_eth_residual_pair_oos_trades.csv", index=False)

    logger.info("===== BTC/ETH Residual Pair OOS Report =====")
    logger.info("Trades: %d", int(metrics["n_trades"]))
    logger.info("Return: %.2f%%", float(metrics["total_return_pct"]))
    logger.info("PF: %.3f", float(metrics["profit_factor"]))
    logger.info("Sharpe: %.2f", float(metrics["sharpe"]))
    logger.info("Max DD: %.2f%%", float(metrics["max_dd_pct"]))
    logger.info("t-stat: %.3f | p=%.4f", float(metrics["t_stat"]), float(metrics["p_value"]))
    logger.info("Adopt: %s", "YES" if adopt else "NO")
    for name, passed in checks.items():
        logger.info("[%s] %s", "PASS" if passed else "FAIL", name)


if __name__ == "__main__":
    main()
