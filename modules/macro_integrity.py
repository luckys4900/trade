from __future__ import annotations

from dataclasses import dataclass
import math
from datetime import datetime
from typing import Any, Callable


def compute_alpha_score(alpha_20d: float | None) -> float:
    """αスコアを0-100へマップ。NaN時はNeutral=50。"""
    if alpha_20d is None:
        return 50.0
    if isinstance(alpha_20d, float) and math.isnan(alpha_20d):
        return 50.0
    return max(0.0, min(100.0, 50.0 + float(alpha_20d) * 5.0))


@dataclass
class GapPredictionBreakdown:
    """ギャップ予測の完全な監査証跡。"""

    inputs: dict[str, dict[str, Any]]
    cli_overrides: dict[str, float] | None = None
    fusion_rule: str = ""
    raw_prediction: float = 0.0
    conservative_factor: float = 0.7
    final_prediction: float = 0.0

    def render(self) -> str:
        lines = ["### ギャップ予測 監査証跡", ""]
        lines.append("| ドライバー | yfinance | CLI入力 | 採用値 | 出所 | β | インパクト |")
        lines.append("|---|---|---|---|---|---|---|")
        for name, info in self.inputs.items():
            yf = info.get("yfinance_value", "—")
            cli = info.get("cli_value", "—")
            used = info.get("used_value", "—")
            src = info.get("source", "—")
            beta = float(info.get("beta", 0.0))
            impact = float(info.get("impact", 0.0))

            mismatch = ""
            if yf != "—" and cli != "—":
                try:
                    if abs(float(yf) - float(cli)) > 0.5:
                        mismatch = " ⚠️矛盾"
                except Exception:
                    pass
            lines.append(
                f"| {name} | {yf} | {cli} | **{used}**{mismatch} | {src} | {beta:.3f} | {impact:+.2f}% |"
            )

        lines.append("")
        lines.append(f"**合成ルール**: {self.fusion_rule}")
        lines.append(
            f"**生予測**: {self.raw_prediction:+.2f}% × 保守補正{self.conservative_factor} = **{self.final_prediction:+.2f}%**"
        )
        return "\n".join(lines)


def fetch_cme_nikkei_overnight_change(
    provider: Callable[[], float | None] | None = None,
) -> float | None:
    """
    N225欠損時のCME先物プロキシ取得。
    providerを渡せばテストで外部依存を排除できる。
    """
    if provider is not None:
        return provider()

    try:
        import yfinance as yf

        nkd = yf.Ticker("NKD=F").history(period="2d", interval="1h")
        if nkd.empty or len(nkd["Close"]) < 25:
            return None
        latest = float(nkd["Close"].iloc[-1])
        prev = float(nkd["Close"].iloc[-25])
        if prev == 0:
            return None
        return (latest - prev) / prev * 100.0
    except Exception:
        return None


def predict_gap(
    drivers: dict[str, float | None],
    betas: dict[str, float],
    clip_pct: float = 5.0,
) -> dict[str, Any]:
    """
    欠損対応ギャップ予測:
    - Tier1(N225)欠損でUNAVAILABLE
    - Tier2欠損は0インパクト
    """
    n225 = drivers.get("N225_change")
    if n225 is None or (isinstance(n225, float) and math.isnan(n225)):
        return {
            "gap_pct": None,
            "status": "UNAVAILABLE",
            "reason": "Primary driver (N225) missing. Cannot forecast.",
            "fallback_suggestion": "Use CME futures overnight change as proxy.",
        }

    total_impact = 0.0
    breakdown: dict[str, dict[str, Any]] = {}
    for name, beta in betas.items():
        key = f"{name}_change"
        change = drivers.get(key)
        if change is None or (isinstance(change, float) and math.isnan(change)):
            breakdown[name] = {"beta": beta, "change": "N/A", "impact": 0.0}
            continue
        impact = beta * float(change)
        total_impact += impact
        breakdown[name] = {"beta": beta, "change": float(change), "impact": impact}

    raw = total_impact
    adjusted = raw * 0.7
    clipped = max(-clip_pct, min(clip_pct, adjusted))
    return {
        "gap_pct": clipped,
        "raw": raw,
        "adjusted": adjusted,
        "status": "OK",
        "breakdown": breakdown,
    }


def predict_gap_with_proxy(
    drivers: dict[str, float | None],
    betas: dict[str, float],
    cme_change: float | None = None,
    yfinance_hint: float | None = None,
) -> dict[str, Any]:
    patch = dict(drivers)
    audit_inputs: dict[str, dict[str, Any]] = {}
    fusion_rule = "CLI値があればCLI優先、欠損時のみyfinanceプロキシ採用。"

    n225 = patch.get("N225_change")
    if n225 is None or (isinstance(n225, float) and math.isnan(n225)):
        cli_val = drivers.get("N225_change")
        if cme_change is None:
            cme_change = fetch_cme_nikkei_overnight_change()
        if cme_change is not None:
            patch["N225_change"] = cme_change
            out = predict_gap(patch, betas)
            out["proxy_used"] = "CME_N225"
            out["proxy_change"] = cme_change
            audit_inputs["N225"] = {
                "yfinance_value": yfinance_hint if yfinance_hint is not None else "—",
                "cli_value": cli_val if cli_val is not None else "—",
                "used_value": cme_change,
                "source": "CME_PROXY",
                "beta": betas.get("N225", 0.0),
                "impact": betas.get("N225", 0.0) * float(cme_change),
            }
            out["audit"] = GapPredictionBreakdown(
                inputs=audit_inputs,
                fusion_rule=fusion_rule,
                raw_prediction=float(out.get("raw", 0.0)),
                final_prediction=float(out.get("gap_pct", 0.0)),
            )
            return out

    out = predict_gap(patch, betas)
    if out.get("status") == "OK":
        for name, beta in betas.items():
            key = f"{name}_change"
            val = patch.get(key)
            audit_inputs[name] = {
                "yfinance_value": yfinance_hint if name == "N225" and yfinance_hint is not None else "—",
                "cli_value": drivers.get(key, "—"),
                "used_value": val if val is not None else "—",
                "source": "CLI" if drivers.get(key) is not None else "MODEL",
                "beta": beta,
                "impact": float(out["breakdown"][name]["impact"]) if name in out["breakdown"] else 0.0,
            }
    out["audit"] = GapPredictionBreakdown(
        inputs=audit_inputs,
        fusion_rule=fusion_rule,
        raw_prediction=float(out.get("raw", 0.0)) if out.get("status") == "OK" else 0.0,
        final_prediction=float(out.get("gap_pct", 0.0)) if out.get("gap_pct") is not None else 0.0,
    )
    return out


def fetch_realtime_proxies(now_jst: datetime) -> dict[str, dict[str, Any]]:
    proxies: dict[str, dict[str, Any]] = {}
    now_iso = now_jst.isoformat()
    try:
        import yfinance as yf

        nkd = yf.Ticker("NKD=F").history(period="2d", interval="15m")
        if not nkd.empty:
            proxies["CME_N225"] = {
                "latest": float(nkd["Close"].iloc[-1]),
                "change_pct": (float(nkd["Close"].iloc[-1]) / float(nkd["Close"].iloc[0]) - 1) * 100,
                "timestamp": str(nkd.index[-1]),
                "fresh": True,
                "fresh_icon": "🟢 fresh",
            }
    except Exception as exc:
        proxies["CME_N225"] = {"error": str(exc), "timestamp": now_iso, "fresh": False, "fresh_icon": "🟡 stale"}

    try:
        import yfinance as yf

        wti = yf.Ticker("CL=F").history(period="2d", interval="15m")
        if not wti.empty:
            proxies["WTI"] = {
                "latest": float(wti["Close"].iloc[-1]),
                "change_pct": (float(wti["Close"].iloc[-1]) / float(wti["Close"].iloc[0]) - 1) * 100,
                "timestamp": str(wti.index[-1]),
                "fresh": True,
                "fresh_icon": "🟢 fresh",
            }
    except Exception as exc:
        proxies["WTI"] = {"error": str(exc), "timestamp": now_iso, "fresh": False, "fresh_icon": "🟡 stale"}

    try:
        import yfinance as yf

        brent = yf.Ticker("BZ=F").history(period="2d", interval="15m")
        if not brent.empty:
            proxies["BRENT"] = {
                "latest": float(brent["Close"].iloc[-1]),
                "change_pct": (float(brent["Close"].iloc[-1]) / float(brent["Close"].iloc[0]) - 1) * 100,
                "timestamp": str(brent.index[-1]),
                "fresh": True,
                "fresh_icon": "🟢 fresh",
            }
    except Exception as exc:
        proxies["BRENT"] = {"error": str(exc), "timestamp": now_iso, "fresh": False, "fresh_icon": "🟡 stale"}

    try:
        import yfinance as yf

        jpy = yf.Ticker("JPY=X").history(period="2d", interval="15m")
        if not jpy.empty:
            proxies["USDJPY"] = {
                "latest": float(jpy["Close"].iloc[-1]),
                "change_pct": (float(jpy["Close"].iloc[-1]) / float(jpy["Close"].iloc[0]) - 1) * 100,
                "timestamp": str(jpy.index[-1]),
                "fresh": True,
                "fresh_icon": "🟢 fresh",
            }
    except Exception as exc:
        proxies["USDJPY"] = {"error": str(exc), "timestamp": now_iso, "fresh": False, "fresh_icon": "🟡 stale"}

    try:
        import yfinance as yf

        vix = yf.Ticker("^VIX").history(period="2d", interval="15m")
        if not vix.empty:
            proxies["VIX"] = {
                "latest": float(vix["Close"].iloc[-1]),
                "change_pct": (float(vix["Close"].iloc[-1]) / float(vix["Close"].iloc[0]) - 1) * 100,
                "timestamp": str(vix.index[-1]),
                "fresh": True,
                "fresh_icon": "🟢 fresh",
            }
    except Exception as exc:
        proxies["VIX"] = {"error": str(exc), "timestamp": now_iso, "fresh": False, "fresh_icon": "🟡 stale"}

    try:
        import yfinance as yf

        gold = yf.Ticker("GC=F").history(period="2d", interval="15m")
        if not gold.empty:
            proxies["GOLD"] = {
                "latest": float(gold["Close"].iloc[-1]),
                "change_pct": (float(gold["Close"].iloc[-1]) / float(gold["Close"].iloc[0]) - 1) * 100,
                "timestamp": str(gold.index[-1]),
                "fresh": True,
                "fresh_icon": "🟢 fresh",
            }
    except Exception as exc:
        proxies["GOLD"] = {"error": str(exc), "timestamp": now_iso, "fresh": False, "fresh_icon": "🟡 stale"}

    return proxies

