"""JPX day-trade report runner with auditing-focused integrity output."""

from __future__ import annotations

import argparse
import io
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from backtesting import Backtest

from jpx_strategy import JPXRSISwing
from jquants_data_loader import JQuantsDataLoader
from modules.data_freshness import DataStalenessError, enforce_data_freshness
from modules.data_provenance import DataProvenance, DataSource, render_data_provenance_block
from modules.event_calendar import EARNINGS_CALENDAR, check_today_events, render_earnings_proximity_block
from modules.macro_integrity import compute_alpha_score, fetch_realtime_proxies, predict_gap_with_proxy
from modules.portfolio_logic import compute_hold_vs_cut_ev
from modules.regime import ACTION_BIAS, determine_regime
from modules.scenario_engine import apply_backtest_quality_gate, generate_g0_scenario
from modules.sector_classifier import get_sector_context, should_show_sox_in_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("run_jpx_backtest")
JST = timezone(timedelta(hours=9))

ACTION_RULES: dict[str, list[str]] = {
    "REDUCE_POSITION": [
        "ポジションサイズは通常の 30% 以下に固定",
        "オーバーナイト保有 絶対禁止",
        "14:00 以降の新規エントリー 禁止",
        "イベント時刻の前後30分は手仕舞いまたは手出し無用",
        "両建てヘッジも本日は検討候補",
    ],
    "NO_TRADE": [
        "本日は観察のみ / 新規エントリー全面禁止",
        "既存ポジションは前場中に半分利確または損切り",
        "ザラ場中のニュースフロー監視に専念",
    ],
    "NORMAL": ["通常運用。ただしSL/TP規律は厳守"],
    "AGGRESSIVE": ["有利な環境。通常サイズ×1.2 まで拡大可", "1日最大DDは総資金の2%で停止"],
}


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift(1)).abs(),
            (df["Low"] - df["Close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_series = tr.ewm(alpha=1 / period, min_periods=period).mean()
    last_atr = float(atr_series.iloc[-1])
    if math.isnan(last_atr) or last_atr <= 0:
        return float((df["High"] - df["Low"]).tail(20).mean())
    return last_atr


def _gap_fill_stats(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    hist = df.copy()
    hist["prev_close"] = hist["Close"].shift(1)
    hist["gap_pct"] = ((hist["Open"] - hist["prev_close"]) / hist["prev_close"] * 100.0).abs()
    hist = hist.dropna(subset=["prev_close", "gap_pct"])

    def _bucket(mask: pd.Series) -> dict[str, float]:
        sub = hist[mask]
        if sub.empty:
            return {"fill_prob": 0.0, "n": 0.0}
        fill = (
            (
                ((sub["Open"] - sub["prev_close"]) > 0) & (sub["Low"] <= sub["prev_close"])
            )
            | (
                ((sub["Open"] - sub["prev_close"]) <= 0) & (sub["High"] >= sub["prev_close"])
            )
        ).mean()
        return {"fill_prob": float(fill), "n": float(len(sub))}

    return {
        "small": _bucket(hist["gap_pct"] <= 1.0),
        "medium": _bucket((hist["gap_pct"] > 1.0) & (hist["gap_pct"] <= 3.0)),
        "large": _bucket(hist["gap_pct"] > 3.0),
    }


def _extract_backtest_quality(stats: pd.Series) -> dict[str, Any]:
    n_trades = int(stats.get("# Trades", 0) or 0)
    sharpe_raw = stats.get("Sharpe Ratio", 0.0)
    sharpe = 0.0 if sharpe_raw is None or (isinstance(sharpe_raw, float) and math.isnan(sharpe_raw)) else float(sharpe_raw)
    validity = n_trades >= 20 and sharpe >= 1.0
    return {"validity": validity, "n_trades": n_trades, "sharpe": sharpe}


def _render_macro_cross_section(proxies: dict[str, dict[str, Any]]) -> str:
    def fmt(name: str, prefix: str = "", suffix: str = "") -> tuple[str, str, str, str]:
        item = proxies.get(name, {})
        if "latest" not in item:
            return ("N/A", "N/A", str(item.get("timestamp", "N/A")), "🟡 stale")
        latest = f"{prefix}{item['latest']:.2f}{suffix}"
        change = f"{item.get('change_pct', 0.0):+.2f}%"
        ts = str(item.get("timestamp", "N/A"))
        fresh_icon = str(item.get("fresh_icon", "🟡 stale"))
        return latest, change, ts, fresh_icon

    cme_l, cme_c, cme_t, cme_f = fmt("CME_N225", suffix="円")
    wti_l, wti_c, wti_t, wti_f = fmt("WTI", prefix="$")
    brent_l, brent_c, brent_t, brent_f = fmt("BRENT", prefix="$")
    jpy_l, jpy_c, jpy_t, jpy_f = fmt("USDJPY")
    vix_l, vix_c, vix_t, vix_f = fmt("VIX")
    gld_l, gld_c, gld_t, gld_f = fmt("GOLD", prefix="$")

    return (
        "## マクロ横断ダッシュボード\n\n"
        "| 指標 | 最新値 | 変化率(24h) | 取得時刻 | 鮮度 |\n"
        "|---|---|---|---|---|\n"
        f"| CME日経先物 | {cme_l} | {cme_c} | {cme_t} | {cme_f} |\n"
        f"| WTI原油 | {wti_l} | {wti_c} | {wti_t} | {wti_f} |\n"
        f"| ブレント原油 | {brent_l} | {brent_c} | {brent_t} | {brent_f} |\n"
        f"| USD/JPY | {jpy_l} | {jpy_c} | {jpy_t} | {jpy_f} |\n"
        f"| VIX | {vix_l} | {vix_c} | {vix_t} | {vix_f} |\n"
        f"| 金(GC=F) | {gld_l} | {gld_c} | {gld_t} | {gld_f} |\n"
    )


def _render_env_score_summary(components: dict[str, float], final_score: float, alpha_note: str) -> str:
    return (
        "### 環境スコア内訳 (検算可能)\n\n"
        "```\n"
        f"VIX      {components['vix_raw']:.1f}/100 × 28% = {components['vix_raw']*0.28:.2f}\n"
        f"Trend    {components['trend_raw']:.1f}/100 × 24% = {components['trend_raw']*0.24:.2f}\n"
        f"Liquid   {components['liquidity_raw']:.1f}/100 × 20% = {components['liquidity_raw']*0.20:.2f}\n"
        f"Gap      {components['gap_raw']:.1f}/100 × 16% = {components['gap_raw']*0.16:.2f}\n"
        f"Alpha    {components['alpha_raw']:.1f}/100 × 12% = {components['alpha_raw']*0.12:.2f}\n"
        "─────────────────────────────\n"
        f"合計                           {final_score:.2f}/100\n"
        "```\n\n"
        "判定ロジック:\n"
        "- >=70: 高品質 / 通常サイズ\n"
        "- 50-69: 中品質 / サイズ×0.7\n"
        "- 30-49: 低品質 / サイズ×0.4\n"
        "- <30: 超低品質 / NO_TRADE 推奨\n\n"
        f"注記: {alpha_note}\n"
    )


def _render_action_discipline_block(action_bias: str, events: list[dict[str, Any]]) -> str:
    rules = ACTION_RULES.get(action_bias, ACTION_RULES["NORMAL"])
    lines = [f"## 本日の行動規律 (action_bias={action_bias})", ""]
    if events:
        lines.append("発動イベント:")
        for e in events:
            lines.append(f"- `{e.get('time','当日')}`: **{e.get('event','イベント')}** (risk={e.get('risk_level','UNKNOWN')})")
        lines.append("")
    lines.append("厳守ルール:")
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {rule}")
    return "\n".join(lines)


def _render_scenario_eligibility_block(gap_pct: float | None, gap_stats: dict[str, dict[str, float]]) -> str:
    if gap_pct is None:
        g0_status = "採用不可"
        g0_reason = "ギャップ予測が計算不能(プライマリドライバー欠損)"
    elif gap_pct < 0:
        g0_status = "採用不可"
        g0_reason = f"ギャップが負({gap_pct:+.2f}%)。G0はGU専用。"
    elif gap_pct >= 3.0 and gap_stats["large"]["fill_prob"] < 0.10:
        g0_status = "条件付き"
        g0_reason = f"large窓埋め確率={gap_stats['large']['fill_prob']:.0%}(n={int(gap_stats['large']['n'])})でTP縮小。"
    else:
        g0_status = "採用"
        g0_reason = f"ギャップ条件適合({gap_pct:+.2f}%)。"

    return (
        "### シナリオ採否マトリクス\n\n"
        "| ID | 名称 | 方向 | 採否 | 理由 |\n"
        "|---|---|---|---|---|\n"
        f"| G0 | ギャップ押し目 | LONG | {g0_status} | {g0_reason} |\n"
        "| S2 | VWAP回帰 | LONG | 採用 | 標準押し目候補 |\n"
        "| C1 | 期中リバーサル | LONG | 採用 | GD時の主戦略 |\n"
        "| C2 | 窓埋めショート | SHORT | 条件付き | 反発失敗時のみ |\n\n"
        "### ギャップ分類別・窓埋め統計\n\n"
        "| 分類 | 閾値 | 窓埋め確率 | サンプル数 |\n"
        "|---|---|---|---|\n"
        f"| small | |gap|<=1% | {gap_stats['small']['fill_prob']:.0%} | n={int(gap_stats['small']['n'])} |\n"
        f"| medium | 1%<|gap|<=3% | {gap_stats['medium']['fill_prob']:.0%} | n={int(gap_stats['medium']['n'])} |\n"
        f"| large | |gap|>3% | {gap_stats['large']['fill_prob']:.0%} | n={int(gap_stats['large']['n'])} |\n"
    )


def _render_backtest_scope_disclaimer(backtest: dict[str, Any]) -> str:
    validity = bool(backtest["validity"])
    return (
        "## バックテスト 範囲明示 (重要)\n\n"
        "### バックテスト設定\n"
        f"- 戦略種別: {backtest['strategy_type']}\n"
        f"- 時間足: **{backtest['timeframe']}**\n"
        f"- 期間: {backtest['period_start']} 〜 {backtest['period_end']} ({backtest['n_bars']} bars)\n"
        f"- 取引コスト: 片道 {backtest['commission_bps']}bps + スリッページ {backtest['slippage_bps']}bps\n"
        f"- トレード数: {backtest['n_trades']}\n\n"
        "### 適用範囲警告\n"
        f"このバックテストは **{backtest['timeframe']}** ベース。デイトレ執行を直接保証しません。\n\n"
        f"- n={backtest['n_trades']} {'(>=30で統計的有意)' if backtest['n_trades'] >= 30 else '(不足)'}\n"
        f"- Sharpe={backtest['sharpe']:.2f} {'(>=1.0で実運用可)' if backtest['sharpe'] >= 1.0 else '(不足)'}\n"
        f"- 妥当性判定: {'PASS' if validity else 'FAIL'}\n\n"
        f"{'シナリオは実資金投入可。' if validity else '全シナリオ PAPER_TRADE_ONLY。'}\n"
    )


def _expected_open(last_close: float, gap_pct: float | None) -> float | None:
    if gap_pct is None:
        return None
    return last_close * (1.0 + gap_pct / 100.0)


def _render_executive_summary(
    provenance: DataProvenance,
    env_score: float,
    gap_pct: float | None,
    expected_open: float | None,
    events: list[dict[str, Any]],
    size_mult: float,
    best_scenario: str,
    best_rrr: float,
) -> str:
    if not provenance.is_trustworthy_for_live_trading:
        verdict = "🚨 REPORT_DISABLED"
        one_liner = "データが合成/不明のため実取引判断に使用不可。観察のみ。"
    elif env_score < 20:
        verdict = "🔴 NO_TRADE"
        one_liner = "環境超低品質 + イベントリスク高。終日観察優先。"
    elif events:
        verdict = "🟡 REDUCED"
        one_liner = f"サイズ縮小運用。{events[0].get('event','重大イベント')}まで14:00 cutoff厳守。"
    elif env_score >= 70:
        verdict = "🟢 NORMAL"
        one_liner = f"通常運用可。優先シナリオ: {best_scenario}"
    else:
        verdict = "🟠 CAUTIOUS"
        one_liner = "条件付きで小サイズ。フィルタ厳格化。"

    gap_txt = "UNAVAILABLE" if gap_pct is None else f"{gap_pct:+.2f}%"
    open_txt = "N/A" if expected_open is None else f"{expected_open:,.0f}円"
    event_txt = events[0].get("event", "なし") if events else "なし"
    rating = "🔴超低品質" if env_score < 30 else "🟠低品質" if env_score < 50 else "🟡中品質" if env_score < 70 else "🟢高品質"
    return (
        "# エグゼクティブサマリー\n\n"
        f"## 本日の総合判定: **{verdict}**\n\n"
        f"**{one_liner}**\n\n"
        "| 要素 | 値 |\n"
        "|---|---|\n"
        f"| 環境スコア | **{env_score:.1f}/100** ({rating}) |\n"
        f"| ギャップ予測 | **{gap_txt}** -> 寄り目安 {open_txt} |\n"
        f"| 主要イベント | {event_txt} |\n"
        f"| データ品質 | {provenance.source.value} |\n"
        f"| 推奨サイズ | 通常の **{size_mult:.0%}** |\n"
        f"| 優先シナリオ | **{best_scenario}** (RRR={best_rrr:.1f}) |\n"
    )


def _load_market_data(code: str, start: str, end: str, *, no_cache: bool = False) -> tuple[pd.DataFrame, DataProvenance]:
    now_jst = datetime.now(JST)
    chain: list[str] = []
    loader = JQuantsDataLoader()
    if loader.cli is not None:
        chain.append("jquants(試行)")
        if no_cache:
            try:
                raw = loader.cli.get_prices_daily_quotes(code=code, from_date=start, to_date=end)
            except Exception as exc:
                LOGGER.warning("J-Quants fetch failed (no_cache): %s", exc)
                raw = pd.DataFrame()
            if not raw.empty:
                df = raw.rename(
                    columns={
                        "Open": "Open",
                        "High": "High",
                        "Low": "Low",
                        "Close": "Close",
                        "Volume": "Volume",
                    }
                )
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
                df = df[["Open", "High", "Low", "Close", "Volume"]]
                prov = DataProvenance(
                    source=DataSource.JQUANTS,
                    fetched_at=now_jst,
                    as_of=pd.Timestamp(df.index[-1]).to_pydatetime().replace(tzinfo=JST),
                    fallback_chain=chain + ["jquants(成功・no_cache)"],
                )
                return df, prov
            chain.append("jquants(失敗・no_cache)")
        else:
            df = loader.get_daily_quotes(code, start, end)
            if not df.empty:
                prov = DataProvenance(
                    source=DataSource.JQUANTS,
                    fetched_at=now_jst,
                    as_of=pd.Timestamp(df.index[-1]).to_pydatetime().replace(tzinfo=JST),
                    fallback_chain=chain + ["jquants(成功)"],
                )
                return df, prov
            chain.append("jquants(失敗)")
    else:
        chain.append("jquants(未設定)")

    try:
        import yfinance as yf

        chain.append("yfinance(試行)")
        ticker = f"{code}.T"
        ydf = yf.Ticker(ticker).history(
            start=start,
            end=end,
            interval="1d",
            auto_adjust=False,
            actions=True,
            prepost=bool(no_cache),
        )
        if not ydf.empty:
            ydf = ydf.rename(columns={"Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"})
            ydf = ydf[["Open", "High", "Low", "Close", "Volume"]]
            prov = DataProvenance(
                source=DataSource.YFINANCE_REALTIME,
                fetched_at=now_jst,
                as_of=pd.Timestamp(ydf.index[-1]).to_pydatetime().replace(tzinfo=JST),
                fallback_chain=chain + ["yfinance(成功)"],
            )
            return ydf, prov
        chain.append("yfinance(失敗)")
    except Exception:
        chain.append("yfinance(失敗)")

    if no_cache:
        prov = DataProvenance(
            source=DataSource.UNKNOWN,
            fetched_at=now_jst,
            as_of=now_jst,
            fallback_chain=chain + ["no_cache: synthetic禁止"],
        )
        return pd.DataFrame(), prov

    synth = loader._synth_daily(code, start, end)
    prov = DataProvenance(
        source=DataSource.SYNTHETIC,
        fetched_at=now_jst,
        as_of=pd.Timestamp(synth.index[-1]).to_pydatetime().replace(tzinfo=JST),
        fallback_chain=chain + ["synthetic(採用)"],
    )
    return synth, prov


def generate_report(
    code: str = "2802",
    start: str = "2023-01-01",
    end: str = "2026-04-22",
    cash: float = 1_000_000,
    nikkei_change_pct: float | None = None,
    nikkei_futures_change_pct: float | None = None,
    wti_change_pct: float | None = None,
    alpha_component: float | None = None,
    macro_sentiment: str = "RISK_ON",
    news_bias: str = "BEARISH",
    pdc_timestamp: str | None = None,
    position_entry: float | None = None,
    position_shares: int = 0,
    position_side: str = "long",
    today: datetime | None = None,
    mock_source: str | None = None,
    yfinance_n225_overnight: float | None = None,
    no_cache: bool = False,
) -> tuple[str, pd.Series]:
    df, provenance = _load_market_data(code, start, end, no_cache=no_cache)
    if mock_source:
        try:
            provenance.source = DataSource[mock_source]
        except Exception:
            pass
    if df.empty:
        raise RuntimeError("No data fetched.")

    pdc_data = {
        "ticker": code,
        "timestamp": pdc_timestamp or datetime.now(timezone.utc).isoformat(),
        "close": float(df["Close"].iloc[-1]),
    }
    limited_report = False
    try:
        _ = enforce_data_freshness(pdc_data, max_staleness_hours=20)
    except DataStalenessError:
        limited_report = True

    now_jst = today.astimezone(JST) if today else datetime.now(JST)
    proxies = fetch_realtime_proxies(now_jst) if 8 <= now_jst.hour <= 9 else {}
    cme_proxy = float(proxies["CME_N225"]["change_pct"]) if "CME_N225" in proxies and "change_pct" in proxies["CME_N225"] else None

    betas = {"N225": 0.8117, "N225FUT": 0.25, "WTI": -0.08, "USDJPY": -0.536}
    drivers = {"N225_change": nikkei_change_pct, "N225FUT_change": nikkei_futures_change_pct, "WTI_change": wti_change_pct}
    gap_result = predict_gap_with_proxy(
        drivers=drivers,
        betas=betas,
        cme_change=cme_proxy,
        yfinance_hint=yfinance_n225_overnight if yfinance_n225_overnight is not None else cme_proxy,
    )

    alpha_score = compute_alpha_score(alpha_component)
    alpha_note = "α成分(N/A) -> 50.0 (Neutral・N/A起因)" if alpha_component is None or (isinstance(alpha_component, float) and math.isnan(alpha_component)) else "α成分は実値を採用"
    regime = determine_regime(macro_sentiment, news_bias)
    action_bias = "REDUCE_POSITION" if check_today_events(now_jst, code) else "NORMAL"
    size_mult = ACTION_BIAS[regime]["size_mult"] * (0.3 if action_bias == "REDUCE_POSITION" else 1.0)

    events = check_today_events(now_jst, code)
    earnings_block = render_earnings_proximity_block(code, now_jst)

    atr = _calculate_atr(df)
    earning_cfg = EARNINGS_CALENDAR.get(code)
    if earning_cfg and "決算プレミアム期" in earnings_block:
        atr *= float(earning_cfg.get("atr_expansion", 1.0))

    gap_stats = _gap_fill_stats(df)
    gap_fill_prob = gap_stats["large"]["fill_prob"] if gap_stats["large"]["n"] > 0 else 0.0
    scenarios: list[dict[str, Any]] = []
    if gap_result.get("gap_pct") is not None and float(gap_result["gap_pct"]) > 0:
        entry = float(df["Close"].iloc[-1]) * (1.0 + float(gap_result["gap_pct"]) / 100.0)
        g0 = generate_g0_scenario(entry=entry, pmh=entry + 3.0 * atr, gap_fill_prob=gap_fill_prob, atr=atr)
        g0["name"] = "G0"
        g0["max_size_pct"] = 30.0
        scenarios.append(g0)
    scenarios.extend(
        [
            {"name": "S2", "entry": float(df["Close"].iloc[-1]), "sl": float(df["Close"].iloc[-1]) - 0.4 * atr, "tp": float(df["Close"].iloc[-1]) + 1.2 * atr, "rrr": 3.0, "max_size_pct": 30.0},
            {"name": "C1", "entry": float(df["Close"].iloc[-1]) - 1.0 * atr, "sl": float(df["Close"].iloc[-1]) - 1.3 * atr, "tp": float(df["Close"].iloc[-1]) + 0.1 * atr, "rrr": 3.67, "max_size_pct": 30.0},
        ]
    )

    bt = Backtest(df, JPXRSISwing, cash=cash, commission=0.001, trade_on_close=True, exclusive_orders=True)
    stats = bt.run()
    quality = _extract_backtest_quality(stats)
    scenarios = apply_backtest_quality_gate(scenarios, quality)
    if provenance.source in {DataSource.SYNTHETIC, DataSource.UNKNOWN, DataSource.YFINANCE_CACHED}:
        scenarios = apply_backtest_quality_gate(scenarios, {"validity": False, "n_trades": quality["n_trades"], "sharpe": quality["sharpe"]})

    components = {"vix_raw": 17.0, "trend_raw": 20.0 if regime == "BULL_FADING" else 55.0, "liquidity_raw": 16.0 if limited_report else 45.0, "gap_raw": 5.0 if gap_result.get("gap_pct") is not None else 0.0, "alpha_raw": alpha_score}
    env_score = (
        components["vix_raw"] * 0.28
        + components["trend_raw"] * 0.24
        + components["liquidity_raw"] * 0.20
        + components["gap_raw"] * 0.16
        + components["alpha_raw"] * 0.12
    )
    if action_bias == "REDUCE_POSITION":
        env_score -= 10.0
    env_score = max(0.0, min(100.0, env_score))

    best = max(scenarios, key=lambda s: float(s.get("rrr", 0.0)))
    gap_pct = gap_result.get("gap_pct")
    expected_open = _expected_open(float(df["Close"].iloc[-1]), float(gap_pct)) if gap_pct is not None else None

    output = io.StringIO()
    if provenance.source == DataSource.SYNTHETIC:
        output.write("**SYNTHETIC**\n\n")
    output.write(render_data_provenance_block(provenance) + "\n\n")
    output.write(
        _render_executive_summary(
            provenance=provenance,
            env_score=env_score,
            gap_pct=float(gap_pct) if gap_pct is not None else None,
            expected_open=expected_open,
            events=events,
            size_mult=size_mult,
            best_scenario=str(best.get("name", "N/A")),
            best_rrr=float(best.get("rrr", 0.0)),
        )
    )
    output.write("\n\n")
    output.write(_render_env_score_summary(components, env_score, alpha_note) + "\n")
    output.write(_render_action_discipline_block(action_bias, events) + "\n\n")
    output.write(_render_macro_cross_section(proxies) + "\n\n")
    output.write(_render_scenario_eligibility_block(float(gap_pct) if gap_pct is not None else None, gap_stats) + "\n\n")
    if "audit" in gap_result:
        output.write(gap_result["audit"].render() + "\n\n")

    if earnings_block:
        output.write(earnings_block + "\n")

    if position_entry is not None and position_shares > 0:
        pos = {"entry_price": position_entry, "shares": position_shares, "entered_at": now_jst.strftime("%Y-%m-%d %H:%M:%S"), "side": position_side}
        market = {"current_price": float(df["Close"].iloc[-1]), "tp_price": float(df["Close"].iloc[-1]) + atr, "sl_price": float(df["Close"].iloc[-1]) - atr}
        hold = compute_hold_vs_cut_ev(pos, market)
        output.write("## 5.X 保有継続 vs 損切再エントリー EV比較\n")
        output.write(f"- entry_price: {hold.get('entry_price')}\n- shares: {hold.get('shares')}\n")
        output.write(f"- hold_ev_jpy: {hold.get('hold_ev_jpy', 0):.2f}\n- cut_reentry_ev_jpy: {hold.get('cut_reentry_ev_jpy', 0):.2f}\n\n")
    else:
        output.write(
            "## 5.X 保有継続 vs 損切再エントリー EV比較\n"
            "⏭️ **スキップ**: ポジション未保有のため本セクションは適用外。\n"
            "保有時は `--position-entry=<価格> --position-shares=<枚数>` を指定して再実行。\n\n"
        )

    bt_meta = {
        "strategy_type": "JPXRSISwing",
        "timeframe": "日足",
        "period_start": str(df.index[0])[:10],
        "period_end": str(df.index[-1])[:10],
        "n_bars": len(df),
        "commission_bps": 10,
        "slippage_bps": 0,
        "n_trades": quality["n_trades"],
        "sharpe": quality["sharpe"],
        "validity": quality["validity"],
    }
    output.write(_render_backtest_scope_disclaimer(bt_meta) + "\n")
    output.write("\n## BACKTEST RAW STATS\n\n")
    output.write(f"```\n{stats}\n```\n")
    return output.getvalue(), stats


def run_jpx_backtest(**kwargs: Any) -> None:
    report_kwargs = dict(kwargs)
    output_path = report_kwargs.pop("output_path", None)
    report_kwargs.pop("verbose", None)
    report_kwargs.pop("dump_config", None)
    report, stats = generate_report(**report_kwargs)
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("cp932", errors="replace").decode("cp932", errors="replace"))
    if output_path:
        Path(str(output_path)).write_text(report, encoding="utf-8")
    try:
        # Create plot only on explicit normal run.
        code = str(kwargs.get("code", "2802"))
        start = str(kwargs.get("start", "2023-01-01"))
        end = str(kwargs.get("end", "2026-04-22"))
        cash = float(kwargs.get("cash", 1_000_000))
        df, _ = _load_market_data(code, start, end, no_cache=bool(kwargs.get("no_cache")))
        bt = Backtest(df, JPXRSISwing, cash=cash, commission=0.001, trade_on_close=True, exclusive_orders=True)
        _ = bt.run()
        filename = f"jpx_backtest_{code}.html"
        bt.plot(filename=filename, open_browser=False)
        LOGGER.info("Chart saved to %s", filename)
    except Exception as exc:
        LOGGER.warning("Could not save chart: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JPX Stock Backtest Runner with macro integrity")
    parser.add_argument("--code", type=str, default="2802")
    parser.add_argument("--start", type=str, default="2023-01-01")
    parser.add_argument("--end", type=str, default="2026-04-22")
    parser.add_argument("--cash", type=float, default=1_000_000)
    parser.add_argument("--nikkei-change-pct", type=float, default=None)
    parser.add_argument("--nikkei-futures-change-pct", type=float, default=None)
    parser.add_argument("--wti-change-pct", type=float, default=None)
    parser.add_argument("--alpha-component", type=float, default=None)
    parser.add_argument("--macro-sentiment", type=str, default="RISK_ON", choices=["RISK_ON", "RISK_OFF", "NEUTRAL"])
    parser.add_argument("--news-bias", type=str, default="BEARISH", choices=["BULLISH", "NEUTRAL", "BEARISH"])
    parser.add_argument("--pdc-timestamp", type=str, default=None)
    parser.add_argument("--position-entry", type=float, default=None)
    parser.add_argument("--position-shares", type=int, default=0)
    parser.add_argument("--position-side", choices=["long", "short"], default="long")
    parser.add_argument("--output-path", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--dump-config", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        LOGGER.setLevel(logging.DEBUG)
    if args.dump_config:
        LOGGER.info("Config: %s", vars(args))

    run_jpx_backtest(
        code=args.code,
        start=args.start,
        end=args.end,
        cash=args.cash,
        nikkei_change_pct=args.nikkei_change_pct,
        nikkei_futures_change_pct=args.nikkei_futures_change_pct,
        wti_change_pct=args.wti_change_pct,
        alpha_component=args.alpha_component,
        macro_sentiment=args.macro_sentiment,
        news_bias=args.news_bias,
        pdc_timestamp=args.pdc_timestamp,
        position_entry=args.position_entry,
        position_shares=args.position_shares,
        position_side=args.position_side,
        output_path=args.output_path,
        no_cache=args.no_cache,
        verbose=args.verbose,
    )
