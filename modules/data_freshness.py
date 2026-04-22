from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


class DataStalenessError(RuntimeError):
    pass


def refetch_from_multiple_sources(ticker: str) -> dict[str, Any] | None:
    # TODO: wire actual data vendors.
    return None


def enforce_data_freshness(
    pdc_data: dict[str, Any],
    max_staleness_hours: int = 20,
    refetcher: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    ts = pdc_data["timestamp"]
    if isinstance(ts, str):
        ts_dt = datetime.fromisoformat(ts)
    else:
        ts_dt = ts
    if ts_dt.tzinfo is None:
        ts_dt = ts_dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    staleness_hours = (now - ts_dt).total_seconds() / 3600.0
    if staleness_hours <= max_staleness_hours:
        return pdc_data

    fetch = refetcher or refetch_from_multiple_sources
    fresh = fetch(str(pdc_data.get("ticker", "")))
    if fresh is None:
        raise DataStalenessError(
            f"PDC data is {staleness_hours:.1f}h old. Refresh failed. Cannot generate reliable report."
        )
    return fresh

