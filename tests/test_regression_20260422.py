from __future__ import annotations

import re
from datetime import datetime

from modules.macro_integrity import compute_alpha_score, predict_gap
from run_jpx_backtest import generate_report


def test_no_nan_alpha_inflation() -> None:
    report, _ = generate_report(code="2802", start="2026-01-01", end="2026-02-28", alpha_component=float("nan"), mock_source="SYNTHETIC")
    assert "alpha_raw(100.0)" not in report
    assert "50.0 (Neutral" in report or "α成分(N/A)" in report


def test_no_plus5_gap_when_driver_missing() -> None:
    result = predict_gap({"N225_change": None, "WTI_change": 0.0}, {"N225": 0.8117, "WTI": -0.08})
    assert result["status"] == "UNAVAILABLE"
    assert result["gap_pct"] is None


def test_g0_not_use_unrealistic_tp() -> None:
    report, _ = generate_report(
        code="2802",
        start="2026-01-01",
        end="2026-02-28",
        nikkei_change_pct=5.0,
        nikkei_futures_change_pct=0.0,
        alpha_component=0.0,
        mock_source="SYNTHETIC",
    )
    if "G0" in report:
        assert "窓埋め確率=0%" not in report or "TP縮小" in report or "DEGRADED" in report


def test_data_provenance_always_present() -> None:
    report, _ = generate_report(code="2802", start="2026-01-01", end="2026-02-28", mock_source="SYNTHETIC")
    assert "Data Provenance" in report


def test_executive_summary_at_top() -> None:
    report, _ = generate_report(code="2802", start="2026-01-01", end="2026-02-28", mock_source="SYNTHETIC")
    first_h1 = re.search(r"^# (.+)$", report, re.MULTILINE)
    assert first_h1 is not None
    assert "エグゼクティブサマリー" in first_h1.group(1)


def test_synthetic_data_triggers_warning() -> None:
    report, _ = generate_report(code="2802", start="2026-01-01", end="2026-02-28", mock_source="SYNTHETIC")
    assert "PAPER_TRADE_ONLY" in report
    assert "SYNTHETIC" in report


def test_iran_event_triggers_reduce_position() -> None:
    report, _ = generate_report(code="2802", start="2026-01-01", end="2026-02-28", today=datetime(2026, 4, 22), mock_source="SYNTHETIC")
    assert "REDUCE_POSITION" in report
    assert "オーバーナイト" in report
    assert "14:00" in report


def test_ajinomoto_earnings_proximity() -> None:
    report, _ = generate_report(code="2802", start="2026-01-01", end="2026-02-28", today=datetime(2026, 4, 22), mock_source="SYNTHETIC")
    assert "2026-05-07" in report
    assert "決算プレミアム期" in report


def test_gap_breakdown_detects_cli_yf_mismatch() -> None:
    report, _ = generate_report(
        code="2802",
        start="2026-01-01",
        end="2026-02-28",
        nikkei_change_pct=-1.28,
        yfinance_n225_overnight=0.27,
        mock_source="SYNTHETIC",
    )
    assert "⚠️矛盾" in report
    assert "合成ルール" in report


def test_compute_alpha_score_nan_neutral() -> None:
    assert compute_alpha_score(float("nan")) == 50.0
