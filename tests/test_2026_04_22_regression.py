from __future__ import annotations

from datetime import datetime

from modules.event_calendar import check_today_events
from modules.macro_integrity import compute_alpha_score, predict_gap, predict_gap_with_proxy
from modules.regime import ACTION_BIAS, determine_regime
from modules.scenario_engine import generate_g0_scenario
from modules.sector_classifier import get_sector_context, should_show_sox_in_report


def test_gap_prediction_with_missing_nikkei() -> None:
    drivers = {"N225_change": float("nan"), "Gold_change": -1.05}
    betas = {"N225": 0.8117, "Gold": 0.1}
    result = predict_gap(drivers, betas)
    assert result["status"] == "UNAVAILABLE"
    assert result["gap_pct"] is None


def test_cme_proxy_fallback() -> None:
    drivers = {"N225_change": float("nan"), "N225FUT_change": -1.28, "WTI_change": 0.0}
    betas = {"N225": 0.8117, "N225FUT": 0.25, "WTI": -0.08}
    result = predict_gap_with_proxy(drivers, betas, cme_change=-1.28)
    assert result["gap_pct"] < 0
    assert result["gap_pct"] > -2.0


def test_alpha_nan_handling() -> None:
    assert compute_alpha_score(float("nan")) == 50.0
    assert compute_alpha_score(0.0) == 50.0
    assert compute_alpha_score(10.0) == 100.0
    assert compute_alpha_score(-10.0) == 0.0


def test_g0_scenario_with_zero_gap_fill_prob() -> None:
    result = generate_g0_scenario(entry=4730, pmh=4957, gap_fill_prob=0.0, atr=100)
    assert result["status"] in ("DEGRADED", "EXCLUDED")
    if result["status"] == "DEGRADED":
        assert result["tp"] < 4957


def test_event_calendar_iran_truce() -> None:
    events = check_today_events(datetime(2026, 4, 22), "2802")
    assert any("イラン停戦期限" in str(e.get("event", "")) for e in events)
    assert any(e.get("action_bias") == "REDUCE_POSITION" for e in events)


def test_sector_classifier_ajinomoto() -> None:
    info = get_sector_context("2802")
    assert info["defensive"] is True
    assert should_show_sox_in_report("2802") is False


def test_regime_bull_fading() -> None:
    regime = determine_regime("RISK_ON", "BEARISH")
    assert regime == "BULL_FADING"
    assert ACTION_BIAS[regime]["size_mult"] == 0.5

