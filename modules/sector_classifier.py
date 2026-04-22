from __future__ import annotations

SECTOR_MAP: dict[str, dict[str, object]] = {
    "2802": {
        "gics": "Consumer Staples",
        "sub": "Food",
        "defensive": True,
        "primary_beta_ref": "TOPIX_FOOD",
        "sox_correlation": 0.10,
    },
    "6871": {
        "gics": "Information Technology",
        "sub": "Semiconductor",
        "defensive": False,
        "primary_beta_ref": "SOX",
        "sox_correlation": 0.75,
    },
    "1605": {
        "gics": "Energy",
        "sub": "Oil & Gas",
        "defensive": False,
        "primary_beta_ref": "BRENT",
        "sox_correlation": 0.05,
    },
}


def get_sector_context(ticker: str) -> dict[str, object]:
    return SECTOR_MAP.get(ticker, {})


def should_show_sox_in_report(ticker: str) -> bool:
    info = get_sector_context(ticker)
    return float(info.get("sox_correlation", 0.0)) >= 0.30

