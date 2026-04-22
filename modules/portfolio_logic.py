from __future__ import annotations

from typing import Any


def compute_hold_vs_cut_ev(position: dict[str, Any] | None, market: dict[str, Any]) -> dict[str, Any]:
    if position is None or float(position.get("shares", 0)) == 0:
        return {
            "section_status": "SKIPPED",
            "reason": "No open position. Hold/Cut analysis not applicable.",
        }

    entry_price = float(position["entry_price"])
    shares = float(position["shares"])
    now = float(market.get("current_price", entry_price))
    tp = float(market.get("tp_price", now))
    sl = float(market.get("sl_price", now))

    hold_ev = (tp - now) * 0.5 + (sl - now) * 0.5
    cut_ev = (tp - entry_price) * 0.5 + (sl - entry_price) * 0.5
    return {
        "section_status": "OK",
        "entry_price": entry_price,
        "shares": shares,
        "entered_at": position.get("entered_at"),
        "hold_ev_jpy": hold_ev * shares,
        "cut_reentry_ev_jpy": cut_ev * shares,
    }

