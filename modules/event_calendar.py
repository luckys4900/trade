from __future__ import annotations

from datetime import datetime, timedelta

EVENT_CALENDAR: dict[str, list[dict[str, object]]] = {
    "2026-04-22": [
        {
            "time": "2026-04-22 22:00 JST",
            "event": "米イラン停戦期限切れ",
            "risk_level": "CRITICAL",
            "impact_sectors": ["ALL"],
            "action_bias": "REDUCE_POSITION",
            "notes": "トランプ氏『延長しない』発言。ホルムズ海峡封鎖継続中。",
        }
    ],
    "2026-05-07": [
        {
            "ticker": "2802",
            "event": "味の素 本決算発表",
            "risk_level": "HIGH",
            "pre_earnings_drift_days": 10,
        }
    ],
}

EARNINGS_CALENDAR: dict[str, dict[str, object]] = {
    "2802": {
        "next_earnings_date": "2026-05-07",
        "type": "本決算",
        "pre_drift_days": 10,
        "atr_expansion": 1.3,
        "overnight_restriction": True,
    }
}

JPX_HOLIDAYS_2026: set[str] = {
    "2026-01-01",
    "2026-01-12",
    "2026-02-11",
    "2026-02-23",
    "2026-03-20",
    "2026-04-29",
    "2026-05-04",
    "2026-05-05",
    "2026-05-06",
    "2026-07-20",
    "2026-08-11",
    "2026-09-21",
    "2026-09-22",
    "2026-09-23",
    "2026-10-12",
    "2026-11-03",
    "2026-11-23",
}


def _business_days_until(current: datetime, target: datetime) -> int:
    if target.date() <= current.date():
        return 0
    d = current + timedelta(days=1)
    count = 0
    while d.date() <= target.date():
        d_str = d.strftime("%Y-%m-%d")
        if d.weekday() < 5 and d_str not in JPX_HOLIDAYS_2026:
            count += 1
        d += timedelta(days=1)
    return count


def check_today_events(date_jst: datetime, ticker: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    date_str = date_jst.strftime("%Y-%m-%d")
    events.extend(EVENT_CALENDAR.get(date_str, []))

    for key, evts in EVENT_CALENDAR.items():
        for ev in evts:
            if str(ev.get("ticker", "")) != ticker:
                continue
            target = datetime.strptime(key, "%Y-%m-%d")
            bdays_to = _business_days_until(date_jst, target)
            pre_days = int(ev.get("pre_earnings_drift_days", 0))
            if 0 < bdays_to <= pre_days:
                events.append({**ev, "days_to": bdays_to, "status": "PRE_EARNINGS"})
    return events


def calc_business_days(today: datetime, target: datetime) -> int:
    return _business_days_until(today, target)


def render_earnings_proximity_block(ticker: str, today: datetime) -> str:
    info = EARNINGS_CALENDAR.get(ticker)
    if not info:
        return ""
    ed = datetime.strptime(str(info["next_earnings_date"]), "%Y-%m-%d")
    biz_days = calc_business_days(today, ed)
    if biz_days <= 0:
        return ""

    if biz_days > int(info["pre_drift_days"]):
        return (
            f"### 次回決算: {info['next_earnings_date']} ({info['type']})\n"
            f"- 残り営業日: **{biz_days}日**\n"
            f"- プレドリフト期間(残り{info['pre_drift_days']}日以下)には未到達\n"
            "- 通常運用可\n"
        )

    urgency = "🚨 直近" if biz_days <= 3 else "⚠️ 警戒"
    return (
        f"### 決算プレミアム期 (常時表示) {urgency}\n\n"
        "| 項目 | 値 |\n"
        "|---|---|\n"
        f"| 次回決算 | **{info['next_earnings_date']}** ({info['type']}) |\n"
        f"| 残り営業日 | **{biz_days}日** |\n"
        f"| ATR拡張係数 | ×{info['atr_expansion']} |\n"
        f"| オーバーナイト | {'❌ 禁止' if info['overnight_restriction'] else '許容'} |\n"
        "| 推奨サイズ | 通常の 70% 以下 |\n\n"
        f"根拠: 決算発表{info['pre_drift_days']}営業日前からボラ拡大が起きやすい。\n"
    )

