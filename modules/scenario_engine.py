from __future__ import annotations

from typing import Any


def generate_g0_scenario(
    gap_info: dict[str, Any] | None = None,
    entry: float = 0.0,
    pmh: float = 0.0,
    gap_fill_prob: float = 0.0,
    atr: float = 100.0,
) -> dict[str, Any]:
    if gap_fill_prob < 0.10:
        tp = entry + (pmh - entry) * 0.25
        tp_rationale = f"窓25%埋め (完全埋め確率{gap_fill_prob:.0%}のため段階利確)"
        status = "DEGRADED"
    elif gap_fill_prob < 0.30:
        tp = entry + (pmh - entry) * 0.50
        tp_rationale = f"窓50%埋め (完全埋め確率{gap_fill_prob:.0%}のため)"
        status = "PARTIAL"
    else:
        tp = pmh
        tp_rationale = "寄り値回帰(完全埋め)"
        status = "FULL"

    sl = entry - atr * 0.20
    risk = entry - sl
    reward = tp - entry
    rrr = reward / risk if risk > 0 else 0.0

    if rrr < 1.0:
        return {
            "status": "EXCLUDED",
            "reason": f"RRR={rrr:.2f}<1.0 + 窓埋め確率<10%",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rrr": rrr,
        }

    warning = None
    if rrr > 5.0:
        warning = f"RRR={rrr:.1f}は非現実的。SLタッチ率が高くなる可能性。"

    return {
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rrr": rrr,
        "tp_rationale": tp_rationale,
        "status": status,
        "warning": warning,
    }


def apply_backtest_quality_gate(scenarios: list[dict[str, Any]], backtest: dict[str, Any]) -> list[dict[str, Any]]:
    if not backtest.get("validity", False):
        for s in scenarios:
            s["execution_mode"] = "PAPER_TRADE_ONLY"
            s["warning"] = (
                f"バックテストn={backtest.get('n_trades', 0)}, "
                f"Sharpe={float(backtest.get('sharpe', 0.0)):.2f}, 妥当性=False。実資金投入非推奨。"
            )
            s["max_size_pct"] = min(float(s.get("max_size_pct", 100.0)), 10.0)
    return scenarios

