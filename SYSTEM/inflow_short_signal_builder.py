# -*- coding: utf-8 -*-
"""
Build inflow_short_signal.json for the live bot (EV1 supplementary short-bias).

Run after btc_inflow_monitor updates events (e.g. cron every 5-15 min):
    python SYSTEM/inflow_short_signal_builder.py

Output: <project_root>/inflow_short_signal.json
"""

from __future__ import annotations

import json
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
sys.path.insert(0, DATA_DIR)
sys.path.insert(0, PROJECT_ROOT)

from btc_inflow_backtest import fetch_historical_prices, load_events  # noqa: E402
from btc_inflow_backtest_daily import fetch_daily_ohlcv  # noqa: E402
from btc_inflow_strategy_pro_backtest import build_4h_ma50, build_daily_features  # noqa: E402
from inflow_short_eval import evaluate_latest_signal  # noqa: E402

OUT_FILE = os.path.join(PROJECT_ROOT, "inflow_short_signal.json")

logger = logging.getLogger("inflow_sig")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    events = load_events(min_btc=50, external_only=True)
    dfeat = build_daily_features(fetch_daily_ohlcv())
    feat4 = build_4h_ma50(fetch_historical_prices())
    ts_d = dfeat["timestamp"].values.astype("int64")
    ts_4h = feat4["timestamp"].values.astype("int64")

    out, _ = evaluate_latest_signal(events, dfeat, feat4, ts_d, ts_4h)
    out["timestamp"] = int(__import__("time").time() * 1000)

    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    os.replace(tmp, OUT_FILE)
    logger.info("Wrote %s valid=%s signal=%s strength=%s", OUT_FILE, out["valid"], out["signal"], out["strength"])


if __name__ == "__main__":
    main()
