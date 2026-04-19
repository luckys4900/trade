import logging
import pathlib
import pickle
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt
import pandas as pd

logger = logging.getLogger(__name__)


class DataFetcher:
    def __init__(self, exchange_id: str = "binance", testnet: bool = False):
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({"enableRateLimit": True})
        if testnet:
            self.exchange.set_sandbox_mode(True)
        self.cache_dir: pathlib.Path = pathlib.Path(__file__).parent / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, symbol: str, timeframe: str) -> pathlib.Path:
        safe = symbol.replace("/", "_")
        return self.cache_dir / f"{safe}_{timeframe}.pkl"

    def _load_cache(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        path = self._cache_path(symbol, timeframe)
        if path.exists():
            df = pd.read_pickle(path)
            logger.info("Cache loaded: %s (%d rows)", path.name, len(df))
            return df
        return None

    def _save_cache(self, df: pd.DataFrame, symbol: str, timeframe: str) -> None:
        path = self._cache_path(symbol, timeframe)
        df.to_pickle(path)
        logger.info("Cache saved: %s (%d rows)", path.name, len(df))

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        cached = self._load_cache(symbol, timeframe)
        since_ms = int(
            datetime.strptime(start_date, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .timestamp()
            * 1000
        )
        end_ms = int(
            datetime.strptime(end_date, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .timestamp()
            * 1000
        )

        if cached is not None and len(cached) > 0:
            last_ts = int(cached.index[-1].timestamp() * 1000)
            if last_ts >= end_ms:
                mask = (cached.index >= pd.Timestamp(start_date, tz="UTC")) & (
                    cached.index <= pd.Timestamp(end_date, tz="UTC")
                )
                return cached.loc[mask].copy()
            since_ms = last_ms = last_ts + 1
            all_rows = cached.values.tolist()
        else:
            all_rows = []

        logger.info(
            "Fetching %s %s from %s...",
            symbol,
            timeframe,
            pd.Timestamp(since_ms, unit="ms"),
        )

        while since_ms < end_ms:
            try:
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=since_ms, limit=1000
                )
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                logger.warning("API error: %s — retrying in 10s", e)
                time.sleep(10)
                continue

            if not ohlcv:
                break

            all_rows.extend(ohlcv)
            last_ts = ohlcv[-1][0]
            if last_ts <= since_ms:
                break
            since_ms = last_ts + 1
            time.sleep(self.exchange.rateLimit / 1000)

        if not all_rows:
            if cached is not None:
                return cached
            return pd.DataFrame()

        df = pd.DataFrame(
            all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = (
            df.drop_duplicates(subset=["timestamp"]).set_index("timestamp").sort_index()
        )
        df = df[~df.index.duplicated(keep="first")]

        mask = (df.index >= pd.Timestamp(start_date, tz="UTC")) & (
            df.index <= pd.Timestamp(end_date, tz="UTC")
        )
        df = df.loc[mask]

        if cached is not None:
            combined = pd.concat([cached, df])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            df = combined

        self._save_cache(df, symbol, timeframe)
        logger.info("Fetched %s %s: %d rows", symbol, timeframe, len(df))
        return df

    @staticmethod
    def validate_data(df: pd.DataFrame, label: str = "") -> bool:
        valid = True
        n = len(df)
        logger.info("[%s] Validating %d rows", label, n)

        if df.isnull().any().any():
            nulls = df.isnull().sum()
            logger.warning("[%s] Null values:\n%s", label, nulls)
            valid = False

        if n > 1:
            gaps = df.index.to_series().diff().dropna()
            expected = pd.Timedelta(hours=4)
            large_gaps = gaps[gaps > expected * 3]
            if len(large_gaps) > 0:
                logger.warning(
                    "[%s] %d gaps > 12h detected (max gap: %s)",
                    label,
                    len(large_gaps),
                    large_gaps.max(),
                )

        if n > 1:
            pct_change = df["close"].pct_change().abs()
            outliers = pct_change[pct_change > 5.0]
            if len(outliers) > 0:
                logger.warning(
                    "[%s] %d extreme price moves (>500%%)", label, len(outliers)
                )
                for idx in outliers.index:
                    logger.warning("  %s: %.1f%%", idx, pct_change.loc[idx] * 100)

        logger.info("[%s] Validation %s", label, "PASSED" if valid else "WARNINGS")
        return valid
