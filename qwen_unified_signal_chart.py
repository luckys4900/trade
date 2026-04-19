# -*- coding: utf-8 -*-
"""
Qwen Unified Strategy - All Signals Chart
Shows OCPM, Range MR, RSI Swing v6 signals on one interactive chart
"""

import os, sys, json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Data config
TIMEFRAME = "4h"
LOOKBACK_DAYS = 90

# Colors per strategy
STRAT_COLORS = {
    "OCPM":     {"long": "#00e676", "short": "#ff1744", "line": "#42a5f5"},
    "RangeMR":  {"long": "#00b0ff", "short": "#ff9100", "line": "#ab47bc"},
    "RSISwing": {"long": "#76ff03", "short": "#d50000", "line": "#ffca28"},
}


def fetch_ohlcv():
    """Fetch OHLCV data from Hyperliquid (same as live bot)"""
    import ccxt
    ex = ccxt.hyperliquid({"enableRateLimit": True})
    since = ex.parse8601((datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    rows = []
    while True:
        try:
            b = ex.fetch_ohlcv("BTC/USDT:USDT", TIMEFRAME, since=since, limit=1000)
        except Exception as e:
            print(f"  Fetch error: {e}")
            break
        if not b: break
        rows.extend(b)
        since = b[-1][0] + 1
        if len(b) < 1000: break
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df.sort_values("datetime").reset_index(drop=True)


def compute_indicators(df):
    """Compute ALL indicators for ALL 3 strategies"""
    # === OCPM ===
    df["ocpm_ema_f"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ocpm_ema_s"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ocpm_slope"] = df["ocpm_ema_f"].pct_change(10)

    # Donchian for trend confirmation
    df["ocpm_donchian_high"] = df["high"].rolling(20).max()
    df["ocpm_donchian_low"] = df["low"].rolling(20).min()

    df["ocpm_trend"] = "RANGE"
    df.loc[(df["close"]>df["ocpm_ema_s"])&(df["ocpm_ema_f"]>df["ocpm_ema_s"])&(df["ocpm_slope"]>0),"ocpm_trend"]="UPTREND"
    df.loc[(df["close"]<df["ocpm_ema_s"])&(df["ocpm_ema_f"]<df["ocpm_ema_s"])&(df["ocpm_slope"]<0),"ocpm_trend"]="DOWNTREND"

    # === Shared RSI/ATR ===
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100/(1+gain/loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)

    tr = pd.concat([df["high"]-df["low"],
                    (df["high"]-df["close"].shift(1)).abs(),
                    (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, min_periods=14).mean()

    # OCPM signals (with Donchian filter)
    donchian_mid = (df["ocpm_donchian_high"] + df["ocpm_donchian_low"]) / 2
    df["ocpm_long"] = ((df["ocpm_trend"]=="UPTREND")
                       & (df["close"] > donchian_mid)
                       & (df["rsi_prev"]<=48.0)
                       & (df["rsi"]>df["rsi_prev"])
                       & (df["rsi"]<55)).astype(int)
    df["ocpm_short"] = ((df["ocpm_trend"]=="DOWNTREND")
                        & (df["close"] < donchian_mid)
                        & (df["rsi_prev"]>=52.0)
                        & (df["rsi"]<df["rsi_prev"])
                        & (df["rsi"]>45)).astype(int)

    # === Range MR ===
    df["bb_mid"] = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2.0*bb_std
    df["bb_lower"] = df["bb_mid"] - 2.0*bb_std

    df["ema_f"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_s"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema_conv"] = (df["ema_f"]-df["ema_s"]).abs()/df["close"]

    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = plus_dm.clip(lower=0).where(plus_dm>minus_dm, 0)
    minus_dm = minus_dm.clip(lower=0).where(minus_dm>plus_dm, 0)
    atr_raw = tr.ewm(alpha=1/14, min_periods=14).mean()
    plus_di = 100*(plus_dm.ewm(alpha=1/14, min_periods=14).mean()/atr_raw)
    minus_di = 100*(minus_dm.ewm(alpha=1/14, min_periods=14).mean()/atr_raw)
    dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0, np.nan)
    df["adx"] = dx.ewm(alpha=1/14, min_periods=14).mean()

    df["is_range"] = (df["adx"]<25.0) & (df["ema_conv"]<0.020)
    df["mr_long"] = (df["is_range"] & (df["low"]<=df["bb_lower"])
                     & (df["rsi_prev"]<=30.0) & (df["rsi"]>df["rsi_prev"])).astype(int)
    df["mr_short"] = (df["is_range"] & (df["high"]>=df["bb_upper"])
                      & (df["rsi_prev"]>=70.0) & (df["rsi"]<df["rsi_prev"])).astype(int)

    # === RSI Swing v6 ===
    df["rsi_swing_long"] = ((df["rsi_prev"]<=30.0) & (df["rsi"]>df["rsi_prev"])).astype(int)
    df["rsi_swing_short"] = ((df["rsi_prev"]>=70.0) & (df["rsi"]<df["rsi_prev"])).astype(int)

    return df


def extract_signals(df):
    """Extract all active signals from latest bars"""
    signals = []

    for i in range(max(0, len(df)-50), len(df)):
        r = df.iloc[i]
        atr = r.get("atr", 0)
        if atr <= 0: continue

        # OCPM
        if r["ocpm_long"] == 1:
            signals.append({
                "strat": "OCPM", "type": "LONG", "datetime": r["datetime"],
                "entry": r["close"], "sl": r["close"] - 3.0*atr,
                "tp": r["close"] + 6.0*atr, "atr": atr, "rsi": r["rsi"],
                "detail": f"UPTREND + RSI pullback ({r['rsi']:.1f})"
            })
        if r["ocpm_short"] == 1:
            signals.append({
                "strat": "OCPM", "type": "SHORT", "datetime": r["datetime"],
                "entry": r["close"], "sl": r["close"] + 3.0*atr,
                "tp": r["close"] - 6.0*atr, "atr": atr, "rsi": r["rsi"],
                "detail": f"DOWNTREND + RSI pullback ({r['rsi']:.1f})"
            })

        # Range MR
        if r["mr_long"] == 1:
            signals.append({
                "strat": "RangeMR", "type": "LONG", "datetime": r["datetime"],
                "entry": r["close"], "sl": r["bb_lower"] - 2.0*atr,
                "tp": r["bb_mid"], "atr": atr, "rsi": r["rsi"],
                "detail": f"BB lower ({r['bb_lower']:.0f}) + RSI OS ({r['rsi']:.1f})"
            })
        if r["mr_short"] == 1:
            signals.append({
                "strat": "RangeMR", "type": "SHORT", "datetime": r["datetime"],
                "entry": r["close"], "sl": r["bb_upper"] + 2.0*atr,
                "tp": r["bb_mid"], "atr": atr, "rsi": r["rsi"],
                "detail": f"BB upper ({r['bb_upper']:.0f}) + RSI OB ({r['rsi']:.1f})"
            })

        # RSI Swing
        if r["rsi_swing_long"] == 1:
            signals.append({
                "strat": "RSISwing", "type": "LONG", "datetime": r["datetime"],
                "entry": r["close"], "sl": r["close"] - 2.0*atr,
                "tp": r["close"] + 5.0*atr, "atr": atr, "rsi": r["rsi"],
                "detail": f"RSI oversold ({r['rsi']:.1f}) reversal"
            })
        if r["rsi_swing_short"] == 1:
            signals.append({
                "strat": "RSISwing", "type": "SHORT", "datetime": r["datetime"],
                "entry": r["close"], "sl": r["close"] + 2.0*atr,
                "tp": r["close"] - 5.0*atr, "atr": atr, "rsi": r["rsi"],
                "detail": f"RSI overbought ({r['rsi']:.1f}) reversal"
            })

    return signals


def build_chart(df, signals):
    """Build unified interactive chart"""
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.55, 0.25, 0.20],
        subplot_titles=("BTC/USDT 4H - All Strategy Signals", "RSI (14)", "ADX / Trend")
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df["datetime"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="BTC/USDT",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1)

    # EMA 21/55 (OCPM)
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["ocpm_ema_f"], name="EMA 21",
                             line=dict(color="#ff9800", width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["ocpm_ema_s"], name="EMA 55",
                             line=dict(color="#2196f3", width=1)), row=1, col=1)

    # BB Bands (Range MR)
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["bb_upper"], name="BB Upper",
                             line=dict(color="#ab47bc", width=0.8, dash="dot"), opacity=0.6), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["bb_lower"], name="BB Lower",
                             line=dict(color="#ab47bc", width=0.8, dash="dot"), opacity=0.6), row=1, col=1)

    # Signal markers
    for sig in signals:
        c = STRAT_COLORS[sig["strat"]]
        color = c["long"] if sig["type"] == "LONG" else c["short"]
        arrow = "▲" if sig["type"] == "LONG" else "▼"
        symbol = "triangle-up" if sig["type"] == "LONG" else "triangle-down"
        textpos = "top center" if sig["type"] == "LONG" else "bottom center"

        fig.add_trace(go.Scatter(
            x=[sig["datetime"]], y=[sig["entry"]],
            mode="markers+text",
            marker=dict(symbol=symbol, size=16, color=color, line=dict(width=2, color="white")),
            text=[f"{arrow} {sig['strat']}"],
            textposition=textpos,
            textfont=dict(size=10, color=color),
            name=f"{sig['strat']} {sig['type']}",
            hovertext=(f"<b>{sig['strat']} {sig['type']}</b><br>"
                       f"Entry: ${sig['entry']:,.2f}<br>"
                       f"SL: ${sig['sl']:,.2f}<br>"
                       f"TP: ${sig['tp']:,.2f}<br>"
                       f"ATR: ${sig['atr']:,.2f}<br>"
                       f"RSI: {sig['rsi']:.1f}<br>"
                       f"{sig['detail']}"),
            hoverinfo="text",
        ), row=1, col=1)

        # TP/SL lines (only for most recent signal per strategy)
        fig.add_trace(go.Scatter(
            x=[df["datetime"].iloc[-30], df["datetime"].iloc[-1]],
            y=[sig["tp"], sig["tp"]],
            mode="lines", line=dict(color="#4caf50", width=1.5, dash="dash"),
            name=f"TP {sig['strat']}", opacity=0.7,
            hoverinfo="name",
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=[df["datetime"].iloc[-30], df["datetime"].iloc[-1]],
            y=[sig["sl"], sig["sl"]],
            mode="lines", line=dict(color="#f44336", width=1.5, dash="dash"),
            name=f"SL {sig['strat']}", opacity=0.7,
            hoverinfo="name",
        ), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["rsi"], name="RSI(14)",
                             line=dict(color="#9c27b0", width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", row=2, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="#666", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", row=2, col=1)
    fig.add_hline(y=48, line_dash="dot", line_color="#ff9800", row=2, col=1)
    fig.add_hline(y=52, line_dash="dot", line_color="#ff9800", row=2, col=1)

    # ADX
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["adx"], name="ADX(14)",
                             line=dict(color="#ffca28", width=1.5)), row=3, col=1)
    fig.add_hline(y=25, line_dash="dash", line_color="#666", row=3, col=1)

    # Layout
    fig.update_layout(
        title=dict(text="Qwen Unified Strategy - All Signals | BTC/USDT 4H", font=dict(size=16), x=0.5),
        height=1000,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
        showlegend=True,
    )

    fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="ADX", row=3, col=1)

    return fig


def main():
    print("=" * 70)
    print(" Qwen Unified Strategy - All Signals Chart")
    print(" OCPM + Range MR + RSI Swing v6")
    print("=" * 70)
    print()
    print("Fetching OHLCV data...")
    df = fetch_ohlcv()
    print(f"Data: {len(df)} bars ({df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]})")

    print("Computing indicators...")
    df = compute_indicators(df)

    print("Extracting signals...")
    signals = extract_signals(df)

    if signals:
        print(f"\n  Found {len(signals)} signal(s):")
        for sig in signals:
            print(f"  [{sig['strat']}] {sig['type']} @ ${sig['entry']:,.2f} | "
                  f"SL ${sig['sl']:,.0f} | TP ${sig['tp']:,.0f} | {sig['detail']}")
    else:
        print("\n  No active signals. Chart shows recent history.")

    print("\nBuilding chart...")
    fig = build_chart(df, signals)

    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unified_signal_chart.html")
    fig.write_html(output_file)
    print(f"\nChart saved: {output_file}")
    print("Opening in browser...")

    import webbrowser
    webbrowser.open(f"file://{output_file}")


if __name__ == "__main__":
    main()
