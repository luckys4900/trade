from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "backtest_results"
FUNDING_DIR = DATA_DIR / "funding"

TARGET_START = pd.Timestamp("2023-01-01 00:00:00")
TARGET_END = pd.Timestamp("2025-09-30 20:00:00")
COMMISSION_PER_SIDE = 0.000225
RISK_PER_TRADE = 0.008
MAX_POSITIONS = 6
SECTOR_LIMIT = 2
RS_LOOKBACK_BARS = 84  # 14 days on 4h bars
TIME_STOP_BARS = 126  # 21 days on 4h bars
SUPER_TREND_PERIOD = 10
SUPER_TREND_MULT = 3.0
VOLUME_MULTIPLIER = 1.75
MIN_SYMBOLS_FOR_RS = 5
REQUEST_TIMEOUT = 30

SECTOR_MAP: dict[str, str] = {
    "AAVE": "defi",
    "ACE": "gaming",
    "ADA": "layer1",
    "AIXBT": "ai",
    "APE": "nft",
    "APT": "layer1",
    "AR": "infra",
    "ARB": "layer2",
    "DOGE": "meme",
    "ETH": "layer1",
    "LINK": "oracle",
    "PEPE": "meme",
    "SOL": "layer1",
    "SUI": "layer1",
    "WIF": "meme",
    "0G": "ai",
    "2Z": "ai",
}


@dataclass
class Position:
    symbol: str
    sector: str
    entry_time: str
    entry_price: float
    size: float
    stop_price: float
    entry_fee: float
    bars_held: int = 0
    partial_taken: bool = False
    trail_active: bool = False
    realized_partial_gross: float = 0.0
    realized_partial_net: float = 0.0


@dataclass
class Trade:
    symbol: str
    sector: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    size: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    bars_held: int
    exit_reason: str
    regime_on: bool
    partial_taken: bool


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("rsm_d_proxy")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def ensure_dirs() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    FUNDING_DIR.mkdir(parents=True, exist_ok=True)


def request_json(url: str, params: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    logger.info("Fetching %s", url)
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    time.sleep(1.25)
    return response.json()


def load_or_fetch_series(
    cache_path: Path,
    url: str,
    params: dict[str, Any],
    json_key: str,
    logger: logging.Logger,
) -> pd.Series:
    if cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["date"])
        return pd.Series(df["value"].to_numpy(), index=df["date"], name=cache_path.stem)

    payload = request_json(url, params, logger)
    raw_values = payload
    for key in json_key.split("."):
        raw_values = raw_values[key]
    records = []
    for ts, value in raw_values:
        date = pd.to_datetime(int(ts), unit="ms").normalize()
        records.append({"date": date, "value": float(value)})
    df = pd.DataFrame(records).drop_duplicates("date").sort_values("date")
    df.to_csv(cache_path, index=False)
    return pd.Series(df["value"].to_numpy(), index=df["date"], name=cache_path.stem)


def load_regime_data(frames: dict[str, pd.DataFrame], logger: logging.Logger) -> pd.DataFrame:
    btc_path = ROOT / "btc_usdt_4h_unified.csv"
    btc_df = pd.read_csv(btc_path, parse_dates=["datetime"]).set_index("datetime").sort_index()
    btc_daily = btc_df["close"].resample("1D").last().dropna().to_frame(name="btc_close")
    btc_daily["btc_close_sma200"] = btc_daily["btc_close"].rolling(200).mean()

    alt_norm_frames = []
    for symbol, df in frames.items():
        daily_close = df["close"].resample("1D").last().dropna()
        if daily_close.empty:
            continue
        base_value = float(daily_close.iloc[0])
        if base_value <= 0:
            continue
        alt_norm_frames.append((daily_close / base_value).rename(symbol))
    if not alt_norm_frames:
        raise RuntimeError("No altcoin daily series available for regime proxy.")

    alt_index = pd.concat(alt_norm_frames, axis=1).mean(axis=1, skipna=True).rename("alt_index")
    regime = btc_daily.join(alt_index, how="inner").dropna()
    regime["btc_norm"] = regime["btc_close"] / float(regime["btc_close"].iloc[0])
    regime["btc_relative_proxy"] = regime["btc_norm"] / regime["alt_index"]
    regime["btc_d_sma20"] = regime["btc_relative_proxy"].rolling(20).mean()
    regime["btc_d_sma50"] = regime["btc_relative_proxy"].rolling(50).mean()
    regime["regime_on"] = (
        (regime["btc_relative_proxy"] < regime["btc_d_sma20"])
        & (regime["btc_d_sma20"] < regime["btc_d_sma50"])
        & (regime["btc_close"] > regime["btc_close_sma200"])
    )
    logger.info("Using BTC relative-underperformance proxy instead of raw BTC.D")
    return regime


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def compute_supertrend(
    df: pd.DataFrame, period: int = SUPER_TREND_PERIOD, multiplier: float = SUPER_TREND_MULT
) -> tuple[pd.Series, pd.Series]:
    atr = compute_atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=float)

    for idx in range(len(df)):
        if idx == 0 or pd.isna(atr.iloc[idx]):
            supertrend.iloc[idx] = np.nan
            direction.iloc[idx] = np.nan
            continue

        prev_idx = idx - 1
        prev_supertrend = supertrend.iloc[prev_idx]
        prev_direction = direction.iloc[prev_idx]
        if pd.isna(prev_supertrend) or pd.isna(prev_direction):
            supertrend.iloc[idx] = lower_basic.iloc[idx]
            direction.iloc[idx] = 1.0
            continue

        upper = upper_basic.iloc[idx]
        lower = lower_basic.iloc[idx]

        if upper < prev_supertrend or df["close"].iloc[prev_idx] > prev_supertrend:
            final_upper = upper
        else:
            final_upper = prev_supertrend

        if lower > prev_supertrend or df["close"].iloc[prev_idx] < prev_supertrend:
            final_lower = lower
        else:
            final_lower = prev_supertrend

        if prev_direction == 1.0:
            if df["close"].iloc[idx] < final_lower:
                supertrend.iloc[idx] = final_upper
                direction.iloc[idx] = -1.0
            else:
                supertrend.iloc[idx] = final_lower
                direction.iloc[idx] = 1.0
        else:
            if df["close"].iloc[idx] > final_upper:
                supertrend.iloc[idx] = final_lower
                direction.iloc[idx] = 1.0
            else:
                supertrend.iloc[idx] = final_upper
                direction.iloc[idx] = -1.0
    return supertrend, direction


def load_symbol_frames(logger: logging.Logger) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for path in sorted(DATA_DIR.glob("*_USDT_4h_730d.csv")):
        symbol = path.name.split("_")[0]
        if symbol not in SECTOR_MAP:
            logger.info("Skipping %s because sector map is undefined", symbol)
            continue
        df = pd.read_csv(path, parse_dates=["datetime"]).set_index("datetime").sort_index()
        df = df[(df.index >= TARGET_START) & (df.index <= TARGET_END)].copy()
        if len(df) < 400:
            logger.info("Skipping %s because data is too short (%d bars)", symbol, len(df))
            continue
        df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["rsi14"] = compute_rsi(df["close"], 14)
        df["atr14"] = compute_atr(df, 14)
        df["vol_sma20"] = df["volume"].rolling(20).mean()
        df["rs_14d"] = df["close"] / df["close"].shift(RS_LOOKBACK_BARS) - 1.0
        df["swing_low_20"] = df["low"].shift(1).rolling(20).min()
        st_line, st_dir = compute_supertrend(df)
        df["supertrend"] = st_line
        df["supertrend_dir"] = st_dir
        df["sector"] = SECTOR_MAP[symbol]
        df["symbol"] = symbol
        frames[symbol] = df
    return frames


def build_inventory(frames: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for symbol, df in frames.items():
        inventory.append(
            {
                "symbol": symbol,
                "sector": SECTOR_MAP[symbol],
                "bars": int(len(df)),
                "start": str(df.index.min()),
                "end": str(df.index.max()),
            }
        )
    return inventory


def get_funding_fee_map(
    symbol: str, timestamps: list[pd.Timestamp], logger: logging.Logger
) -> dict[pd.Timestamp, float]:
    cache_path = FUNDING_DIR / f"{symbol}_binance_funding.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["timestamp"])
        return dict(zip(df["timestamp"], df["rate"]))

    try:
        import ccxt  # type: ignore
    except Exception:
        logger.warning("ccxt is unavailable; funding for %s will be treated as zero", symbol)
        return {}

    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    unified_symbol = f"{symbol}/USDT:USDT"
    if unified_symbol not in exchange.load_markets():
        logger.info("Funding unavailable on Binance USDM for %s", unified_symbol)
        return {}

    start_ms = int(timestamps[0].timestamp() * 1000)
    end_ms = int(timestamps[-1].timestamp() * 1000)
    all_rows: list[dict[str, Any]] = []
    since = start_ms
    while since < end_ms:
        batch = exchange.fetch_funding_rate_history(unified_symbol, since=since, limit=1000)
        if not batch:
            break
        for row in batch:
            ts = pd.to_datetime(int(row["timestamp"]), unit="ms")
            all_rows.append({"timestamp": ts, "rate": float(row["fundingRate"])})
        last_ms = int(batch[-1]["timestamp"])
        since = last_ms + 1
        if len(batch) < 1000:
            break
        time.sleep(0.25)
    if not all_rows:
        return {}
    pd.DataFrame(all_rows).drop_duplicates("timestamp").sort_values("timestamp").to_csv(
        cache_path, index=False
    )
    return {row["timestamp"]: row["rate"] for row in all_rows}


def compute_funding_cost(
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    position_value: float,
    funding_map: dict[pd.Timestamp, float],
) -> float:
    if not funding_map:
        return 0.0
    total = 0.0
    for ts, rate in funding_map.items():
        if entry_time < ts <= exit_time:
            total += position_value * float(rate)
    return total


def run_backtest(
    frames: dict[str, pd.DataFrame],
    regime: pd.DataFrame,
    logger: logging.Logger,
) -> tuple[dict[str, Any], list[Trade]]:
    master_index = pd.Index(sorted(set().union(*[df.index for df in frames.values()])))
    master_index = master_index[(master_index >= TARGET_START) & (master_index <= TARGET_END)]

    rs_table = pd.DataFrame({symbol: df["rs_14d"] for symbol, df in frames.items()}).reindex(master_index)
    row_cache: dict[str, pd.DataFrame] = {symbol: df.reindex(master_index) for symbol, df in frames.items()}

    funding_maps = {
        symbol: get_funding_fee_map(symbol, master_index.to_list(), logger) for symbol in frames.keys()
    }

    equity = 100_000.0
    equity_curve: list[dict[str, Any]] = []
    positions: dict[str, Position] = {}
    trades: list[Trade] = []
    pending_entries: list[tuple[pd.Timestamp, str]] = []

    for idx, ts in enumerate(master_index):
        regime_key = ts.normalize()
        regime_row = regime.loc[regime_key] if regime_key in regime.index else None
        if regime_row is None or pd.isna(regime_row.get("regime_on", np.nan)):
            equity_curve.append({"timestamp": ts, "equity": equity})
            continue

        next_ts = master_index[idx + 1] if idx + 1 < len(master_index) else None

        # Execute pending entries at current bar open.
        current_pending = [item for item in pending_entries if item[0] == ts]
        pending_entries = [item for item in pending_entries if item[0] != ts]
        for _, symbol in current_pending:
            if symbol in positions:
                continue
            if len(positions) >= MAX_POSITIONS:
                continue
            row = row_cache[symbol].loc[ts]
            if row.isna().any():
                continue
            sector = SECTOR_MAP[symbol]
            if sum(1 for pos in positions.values() if pos.sector == sector) >= SECTOR_LIMIT:
                continue
            entry_price = float(row["open"])
            swing_low = float(row["swing_low_20"])
            atr = float(row["atr14"])
            if entry_price <= 0 or pd.isna(swing_low) or pd.isna(atr):
                continue
            stop_price = min(swing_low, entry_price - max(entry_price - swing_low, 2.8 * atr))
            stop_distance = entry_price - stop_price
            if stop_distance <= 0:
                continue
            risk_amount = equity * RISK_PER_TRADE
            size = risk_amount / stop_distance
            notional = size * entry_price
            entry_fee = notional * COMMISSION_PER_SIDE
            if notional + entry_fee > equity:
                size = (equity * 0.95) / entry_price
                notional = size * entry_price
                entry_fee = notional * COMMISSION_PER_SIDE
            if size <= 0:
                continue
            positions[symbol] = Position(
                symbol=symbol,
                sector=sector,
                entry_time=str(ts),
                entry_price=entry_price,
                size=float(size),
                stop_price=float(stop_price),
                entry_fee=float(entry_fee),
            )

        # Exit logic.
        closed_symbols: list[str] = []
        for symbol, position in positions.items():
            row = row_cache[symbol].loc[ts]
            if row.isna().any():
                continue
            open_px = float(row["open"])
            high_px = float(row["high"])
            low_px = float(row["low"])
            close_px = float(row["close"])
            supertrend = float(row["supertrend"])
            position.bars_held += 1

            current_return = close_px / position.entry_price - 1.0
            if current_return >= 0.18:
                position.trail_active = True

            if current_return >= 0.28 and not position.partial_taken:
                partial_size = position.size * 0.5
                partial_exit_fee = partial_size * close_px * COMMISSION_PER_SIDE
                partial_gross = (close_px - position.entry_price) * partial_size
                equity += partial_gross - partial_exit_fee
                position.size -= partial_size
                position.partial_taken = True
                position.trail_active = True
                position.realized_partial_gross += partial_gross
                position.realized_partial_net += partial_gross - partial_exit_fee

            exit_reason = None
            exit_price = None

            if low_px <= position.stop_price:
                exit_reason = "stop_loss"
                exit_price = position.stop_price
            elif position.trail_active and not math.isnan(supertrend) and low_px <= supertrend:
                exit_reason = "supertrend_trail"
                exit_price = supertrend
            elif position.bars_held >= TIME_STOP_BARS:
                exit_reason = "time_stop"
                exit_price = open_px

            if exit_reason is None:
                continue

            final_leg_gross = (float(exit_price) - position.entry_price) * position.size
            exit_fee = position.size * float(exit_price) * COMMISSION_PER_SIDE
            funding_cost = compute_funding_cost(
                pd.Timestamp(position.entry_time),
                ts,
                position.size * position.entry_price,
                funding_maps[symbol],
            )
            gross_pnl = position.realized_partial_gross + final_leg_gross
            net_pnl = (
                position.realized_partial_net
                + final_leg_gross
                - position.entry_fee
                - exit_fee
                - funding_cost
            )
            equity += net_pnl
            trades.append(
                Trade(
                    symbol=symbol,
                    sector=position.sector,
                    entry_time=position.entry_time,
                    exit_time=str(ts),
                    entry_price=position.entry_price,
                    exit_price=float(exit_price),
                    size=position.size,
                    gross_pnl=float(gross_pnl),
                    net_pnl=float(net_pnl),
                    return_pct=float((float(exit_price) / position.entry_price - 1.0) * 100.0),
                    bars_held=position.bars_held,
                    exit_reason=exit_reason,
                    regime_on=bool(regime_row["regime_on"]),
                    partial_taken=position.partial_taken,
                )
            )
            closed_symbols.append(symbol)

        for symbol in closed_symbols:
            positions.pop(symbol, None)

        # Mark-to-market equity.
        mtm = equity
        for symbol, position in positions.items():
            row = row_cache[symbol].loc[ts]
            if row.isna().any():
                continue
            mtm += (float(row["close"]) - position.entry_price) * position.size

        equity_curve.append({"timestamp": ts, "equity": mtm})

        # Entry signal evaluation on close; execution on next open.
        if not bool(regime_row["regime_on"]) or next_ts is None:
            continue
        rs_row = rs_table.loc[ts].dropna()
        if len(rs_row) < MIN_SYMBOLS_FOR_RS:
            continue
        top_n = max(1, math.ceil(len(rs_row) * 0.2))
        top_symbols = set(rs_row.sort_values(ascending=False).head(top_n).index)

        for symbol in top_symbols:
            if symbol in positions or any(s == symbol for _, s in pending_entries):
                continue
            if len(positions) + len(pending_entries) >= MAX_POSITIONS:
                break
            row = row_cache[symbol].loc[ts]
            if row.isna().any():
                continue
            if float(row["rsi14"]) < 54.0:
                continue
            if float(row["close"]) <= float(row["ema21"]):
                continue
            if float(row["volume"]) <= float(row["vol_sma20"]) * VOLUME_MULTIPLIER:
                continue
            if float(row["supertrend_dir"]) != 1.0:
                continue
            sector = SECTOR_MAP[symbol]
            current_sector = sum(1 for pos in positions.values() if pos.sector == sector)
            queued_sector = sum(1 for _, s in pending_entries if SECTOR_MAP[s] == sector)
            if current_sector + queued_sector >= SECTOR_LIMIT:
                continue
            pending_entries.append((next_ts, symbol))

    equity_df = pd.DataFrame(equity_curve).set_index("timestamp")
    trade_df = pd.DataFrame([asdict(trade) for trade in trades])
    metrics = summarize_results(equity_df, trade_df, regime)
    return metrics, trades


def summarize_results(
    equity_df: pd.DataFrame, trade_df: pd.DataFrame, regime: pd.DataFrame
) -> dict[str, Any]:
    if equity_df.empty:
        return {"error": "No equity data"}

    start_equity = float(equity_df["equity"].iloc[0])
    final_equity = float(equity_df["equity"].iloc[-1])
    total_return = final_equity / start_equity - 1.0
    daily_equity = equity_df["equity"].resample("1D").last().dropna()
    daily_returns = daily_equity.pct_change().dropna()
    sharpe = 0.0
    if daily_returns.std(ddof=0) > 0:
        sharpe = float(np.sqrt(365.0) * daily_returns.mean() / daily_returns.std(ddof=0))
    peak = equity_df["equity"].cummax()
    drawdown = equity_df["equity"] / peak - 1.0
    max_drawdown = float(drawdown.min())
    years = (equity_df.index[-1] - equity_df.index[0]).total_seconds() / (365.25 * 24 * 3600)
    cagr = float((final_equity / start_equity) ** (1 / years) - 1.0) if years > 0 else 0.0
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else 0.0

    monthly_equity = daily_equity.resample("M").last().dropna()
    monthly_returns = monthly_equity.pct_change().dropna()
    monthly_win_rate = float((monthly_returns > 0).mean() * 100.0) if not monthly_returns.empty else 0.0

    if trade_df.empty:
        return {
            "start_equity": start_equity,
            "final_equity": final_equity,
            "total_return_pct": total_return * 100.0,
            "cagr_pct": cagr * 100.0,
            "max_drawdown_pct": max_drawdown * 100.0,
            "sharpe": sharpe,
            "calmar": calmar,
            "monthly_win_rate_pct": monthly_win_rate,
            "trades": 0,
        }

    wins = trade_df[trade_df["net_pnl"] > 0]
    losses = trade_df[trade_df["net_pnl"] <= 0]
    gross_profit = float(wins["net_pnl"].sum())
    gross_loss = abs(float(losses["net_pnl"].sum()))
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    expectancy_pct = float(trade_df["return_pct"].mean())

    regime_df = regime.copy()
    regime_df["date"] = regime_df.index
    trade_df["entry_date"] = pd.to_datetime(trade_df["entry_time"]).dt.normalize()
    trade_df = trade_df.merge(
        regime_df[["date", "regime_on"]],
        left_on="entry_date",
        right_on="date",
        how="left",
        suffixes=("", "_entry"),
    )
    regime_on_trades = trade_df[trade_df["regime_on_entry"] == True]
    regime_off_trades = trade_df[trade_df["regime_on_entry"] == False]

    def regime_stats(df: pd.DataFrame) -> dict[str, Any]:
        if df.empty:
            return {"trades": 0, "win_rate_pct": 0.0, "expectancy_pct": 0.0}
        return {
            "trades": int(len(df)),
            "win_rate_pct": float((df["net_pnl"] > 0).mean() * 100.0),
            "expectancy_pct": float(df["return_pct"].mean()),
        }

    return {
        "start_equity": start_equity,
        "final_equity": final_equity,
        "total_return_pct": total_return * 100.0,
        "cagr_pct": cagr * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "sharpe": sharpe,
        "calmar": calmar,
        "monthly_win_rate_pct": monthly_win_rate,
        "trades": int(len(trade_df)),
        "win_rate_pct": float((trade_df["net_pnl"] > 0).mean() * 100.0),
        "avg_win_pct": float(wins["return_pct"].mean()) if not wins.empty else 0.0,
        "avg_loss_pct": float(losses["return_pct"].mean()) if not losses.empty else 0.0,
        "expectancy_pct": expectancy_pct,
        "profit_factor": profit_factor,
        "regime_on": regime_stats(regime_on_trades),
        "regime_off": regime_stats(regime_off_trades),
        "analysis_start": str(equity_df.index.min()),
        "analysis_end": str(equity_df.index.max()),
    }


def write_outputs(
    metrics: dict[str, Any],
    trades: list[Trade],
    inventory: list[dict[str, Any]],
    regime: pd.DataFrame,
) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    with open(OUT_DIR / "rsm_d_proxy_results.json", "w", encoding="utf-8") as handle:
        json.dump({"metrics": metrics, "inventory": inventory}, handle, indent=2)
    pd.DataFrame([asdict(trade) for trade in trades]).to_csv(
        OUT_DIR / "rsm_d_proxy_trades.csv", index=False
    )
    inventory_df = pd.DataFrame(inventory)
    inventory_df.to_csv(OUT_DIR / "rsm_d_data_inventory.csv", index=False)
    regime.loc[(regime.index >= TARGET_START) & (regime.index <= TARGET_END)].to_csv(
        OUT_DIR / "rsm_d_regime_daily.csv"
    )


def main() -> None:
    ensure_dirs()
    logger = setup_logging()
    logger.info("Starting RSM-D proxy backtest")
    frames = load_symbol_frames(logger)
    if not frames:
        raise RuntimeError("No usable local 4h symbol data found.")
    inventory = build_inventory(frames)
    regime = load_regime_data(frames, logger)
    metrics, trades = run_backtest(frames, regime, logger)
    write_outputs(metrics, trades, inventory, regime)
    logger.info("Completed RSM-D proxy backtest")
    logger.info("Metrics: %s", json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
