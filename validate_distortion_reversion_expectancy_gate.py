"""
Distortion reversion strategies — expectancy gate for auto-invest eligibility.

Rule: include in automated trading ONLY if post-fee mean return per trade > 0
      AND minimum trade count is met (default 80 on multi-year 5m data).

Outputs: distortion_reversion_expectancy_gate_report.csv + Japanese verdict to log.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MIN_TRADES_FOR_GATE = 80
DATA_PATH = Path("data/raw/BTC_5m_hyperliquid.csv")


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _verdict(row: Dict[str, Any]) -> tuple[str, str]:
    n = float(row.get("trades", 0))
    e_bps = float(row.get("expectancy_bps", 0))
    if n < MIN_TRADES_FOR_GATE:
        return "REJECT", f"取引数不足 n={int(n)} < {MIN_TRADES_FOR_GATE}"
    if e_bps <= 0:
        return "REJECT", f"手数料後期待値<=0 ({e_bps:.3f} bps/トレード)"
    return "PASS", f"E_net>0 ({e_bps:.3f} bps/トレード), n={int(n)}"


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(DATA_PATH)

    root = Path(__file__).resolve().parent
    v2 = _load_module(root / "backtest_distortion_reversion_v2.py", "dr_v2")
    v21 = _load_module(root / "backtest_distortion_reversion_v21_ohlcv_spec.py", "dr_v21")

    raw_v2 = v2.load_data(DATA_PATH)
    feat_v2 = v2.prepare_features(raw_v2)
    res_v2 = v2.run_backtest(feat_v2)

    raw_21 = v21.load_data(DATA_PATH)
    feat_21 = v21.prepare_features_v21(raw_21)

    rows: List[Dict[str, Any]] = []

    def add_row(name: str, d: Dict[str, float]) -> None:
        if "expectancy_bps" not in d:
            d = {**d, "expectancy_bps": float(d.get("expectancy_pct", 0)) * 100.0}
        verdict, reason = _verdict(d)
        rows.append({"strategy": name, "auto_invest_verdict": verdict, "gate_reason_ja": reason, **d})

    add_row("v2.0_OHLCV_proxy_CDS", res_v2)

    for rule, tag in [("min_aligned", "v2.1_min3"), ("weighted", "v2.1_w055")]:
        for filt, filt_tag in [(True, "atr_vol_on"), (False, "filters_off")]:
            r = v21.run_backtest_v21(feat_21, entry_rule=rule, use_vol_atr_filters=filt)
            add_row(f"{tag}_{filt_tag}", r)

    out = root / "distortion_reversion_expectancy_gate_report.csv"
    pd.DataFrame(rows).to_csv(out, index=False)

    logger.info("========== 自動投資ゲート（手数料後・トレード平均リターン） ==========")
    logger.info("データ: %s", DATA_PATH)
    logger.info("合格条件: expectancy_bps > 0 かつ trades >= %s", MIN_TRADES_FOR_GATE)
    logger.info("保存: %s", out)
    for row in rows:
        logger.info("[%s] %s — %s", row["strategy"], row["auto_invest_verdict"], row["gate_reason_ja"])
        logger.info(
            "  trades=%.0f WR=%.2f%% E_net=%.4f%% (%.2f bps) Sharpe=%.4f tot_ret=%.2f%%",
            row["trades"],
            row["win_rate_pct"],
            row["expectancy_pct"],
            row["expectancy_bps"],
            row["sharpe"],
            row["return_pct"],
        )

    any_pass = any(r["auto_invest_verdict"] == "PASS" for r in rows)
    if not any_pass:
        logger.info("結論: いずれのDistortion戦略も自動投資に含めない（期待値またはサンプル不足）。")
    else:
        logger.info("結論: PASS の戦略のみ自動投資候補。実運用前にウォークフォワードで再検証すること。")


if __name__ == "__main__":
    main()
