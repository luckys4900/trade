# -*- coding: utf-8 -*-
"""
Qwen OCPM Strategy - Next Entry Signal Chart
Shows next potential entry with Entry Price, TP, SL on interactive chart
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add trade directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Strategy parameters (same as onchain_pullback_momentum.py)
EMA_FAST = 21
EMA_SLOW = 55
RSI_PERIOD = 14
RSI_PULLBACK_LONG = 48.0
RSI_PULLBACK_SHORT = 52.0
ATR_PERIOD = 14
ATR_SL_MULT = 3.0
ATR_TP_MULT = 6.0
RSI_OVERHEAT = 70.0

# Data config
SYMBOL = "BTC/USDT"
TIMEFRAME = "4h"
LOOKBACK_DAYS = 90


def fetch_ohlcv():
    """Fetch OHLCV data from Binance"""
    import ccxt
    ex = ccxt.binance({"enableRateLimit": True})
    since = ex.parse8601((datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    rows = []
    while True:
        b = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, since=since, limit=1000)
        if not b:
            break
        rows.extend(b)
        since = b[-1][0] + 1
        if len(b) < 1000:
            break
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
    df = df[["datetime", "open", "high", "low", "close", "volume"]].astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
    return df.sort_values("datetime").reset_index(drop=True)


def compute_indicators(df):
    """Compute EMA, RSI, ATR, and signals"""
    # EMA
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df["ema_fast_slope"] = df["ema_fast"].pct_change(10)

    # Trend
    df["trend"] = "RANGE"
    df.loc[(df["close"] > df["ema_slow"]) & (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast_slope"] > 0), "trend"] = "UPTREND"
    df.loc[(df["close"] < df["ema_slow"]) & (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast_slope"] < 0), "trend"] = "DOWNTREND"

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)

    # ATR
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/ATR_PERIOD, min_periods=ATR_PERIOD).mean()

    # Signals
    df["long_entry"] = (
        (df["trend"] == "UPTREND") &
        (df["rsi_prev"] <= RSI_PULLBACK_LONG) &
        (df["rsi"] > df["rsi_prev"]) &
        (df["rsi"] < 55)
    ).astype(int)

    df["short_entry"] = (
        (df["trend"] == "DOWNTREND") &
        (df["rsi_prev"] >= RSI_PULLBACK_SHORT) &
        (df["rsi"] < df["rsi_prev"]) &
        (df["rsi"] > 45)
    ).astype(int)

    return df


def find_next_signal(df):
    """Find the NEXT potential entry signal (most recent bar that meets criteria)"""
    # Check if current/latest bar is a signal
    last = df.iloc[-1]
    signals = []

    if last["long_entry"] == 1:
        atr = last["atr"]
        entry = last["close"]
        sl = entry - (ATR_SL_MULT * atr)
        tp = entry + (ATR_TP_MULT * atr)
        signals.append({
            "type": "LONG",
            "datetime": last["datetime"],
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "atr": atr,
            "rsi": last["rsi"],
            "trend": last["trend"],
            "rr": ATR_TP_MULT / ATR_SL_MULT,
        })

    if last["short_entry"] == 1:
        atr = last["atr"]
        entry = last["close"]
        sl = entry + (ATR_SL_MULT * atr)
        tp = entry - (ATR_TP_MULT * atr)
        signals.append({
            "type": "SHORT",
            "datetime": last["datetime"],
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "atr": atr,
            "rsi": last["rsi"],
            "trend": last["trend"],
            "rr": ATR_TP_MULT / ATR_SL_MULT,
        })

    # If no current signal, find the most recent one in the data
    if not signals:
        for i in range(len(df) - 1, max(0, len(df) - 200), -1):
            row = df.iloc[i]
            if row["long_entry"] == 1:
                atr = row["atr"]
                entry = row["close"]
                signals.append({
                    "type": "LONG",
                    "datetime": row["datetime"],
                    "entry": entry,
                    "sl": entry - (ATR_SL_MULT * atr),
                    "tp": entry + (ATR_TP_MULT * atr),
                    "atr": atr,
                    "rsi": row["rsi"],
                    "trend": row["trend"],
                    "rr": ATR_TP_MULT / ATR_SL_MULT,
                })
                break
            elif row["short_entry"] == 1:
                atr = row["atr"]
                entry = row["close"]
                signals.append({
                    "type": "SHORT",
                    "datetime": row["datetime"],
                    "entry": entry,
                    "sl": entry + (ATR_SL_MULT * atr),
                    "tp": entry - (ATR_TP_MULT * atr),
                    "atr": atr,
                    "rsi": row["rsi"],
                    "trend": row["trend"],
                    "rr": ATR_TP_MULT / ATR_SL_MULT,
                })
                break

    return signals


def build_chart(df, signals):
    """Build interactive Plotly chart"""
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.5, 0.25, 0.25],
        subplot_titles=("BTC/USDT 4H - Price & Signals", "RSI (14)", "Trend Regime")
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df["datetime"],
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="BTC/USDT",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
    ), row=1, col=1)

    # EMA lines
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["ema_fast"], name="EMA 21", line=dict(color="#ff9800", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["ema_slow"], name="EMA 55", line=dict(color="#2196f3", width=1.5)), row=1, col=1)

    # Signal markers and TP/SL lines
    for sig in signals:
        color = "#26a69a" if sig["type"] == "LONG" else "#ef5350"
        arrow = "▲" if sig["type"] == "LONG" else "▼"

        # Entry marker
        fig.add_trace(go.Scatter(
            x=[sig["datetime"]], y=[sig["entry"]],
            mode="markers+text",
            marker=dict(symbol="triangle-up" if sig["type"] == "LONG" else "triangle-down", size=18, color=color, line=dict(width=2, color="white")),
            text=[f"{arrow} {sig['type']} ENTRY"],
            textposition="top center" if sig["type"] == "LONG" else "bottom center",
            textfont=dict(size=11, color=color),
            name=f"{sig['type']} Entry",
            hovertext=f"Entry: ${sig['entry']:,.2f}<br>SL: ${sig['sl']:,.2f}<br>TP: ${sig['tp']:,.2f}<br>ATR: ${sig['atr']:,.2f}<br>RSI: {sig['rsi']:.1f}<br>R:R = 1:{sig['rr']:.1f}",
            hoverinfo="text",
        ), row=1, col=1)

        # TP line
        fig.add_trace(go.Scatter(
            x=[df["datetime"].iloc[-1] - timedelta(days=7), df["datetime"].iloc[-1]],
            y=[sig["tp"], sig["tp"]],
            mode="lines",
            line=dict(color="#4caf50", width=2, dash="dash"),
            name=f"TP ${sig['tp']:,.0f}",
            hoverinfo="name",
        ), row=1, col=1)

        # SL line
        fig.add_trace(go.Scatter(
            x=[df["datetime"].iloc[-1] - timedelta(days=7), df["datetime"].iloc[-1]],
            y=[sig["sl"], sig["sl"]],
            mode="lines",
            line=dict(color="#f44336", width=2, dash="dash"),
            name=f"SL ${sig['sl']:,.0f}",
            hoverinfo="name",
        ), row=1, col=1)

        # Entry price line
        fig.add_trace(go.Scatter(
            x=[df["datetime"].iloc[-1] - timedelta(days=7), df["datetime"].iloc[-1]],
            y=[sig["entry"], sig["entry"]],
            mode="lines",
            line=dict(color=color, width=1.5, dash="dot"),
            name=f"Entry ${sig['entry']:,.0f}",
            hoverinfo="name",
        ), row=1, col=1)

        # TP/SL zone fill
        if sig["type"] == "LONG":
            fig.add_trace(go.Scatter(
                x=[df["datetime"].iloc[-1] - timedelta(days=7), df["datetime"].iloc[-1], df["datetime"].iloc[-1], df["datetime"].iloc[-1] - timedelta(days=7)],
                y=[sig["entry"], sig["entry"], sig["tp"], sig["tp"]],
                fill="toself",
                fillcolor="rgba(76,175,80,0.15)",
                line=dict(width=0),
                name="TP Zone",
                showlegend=False,
                hoverinfo="skip",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=[df["datetime"].iloc[-1] - timedelta(days=7), df["datetime"].iloc[-1], df["datetime"].iloc[-1], df["datetime"].iloc[-1] - timedelta(days=7)],
                y=[sig["entry"], sig["entry"], sig["sl"], sig["sl"]],
                fill="toself",
                fillcolor="rgba(244,67,54,0.15)",
                line=dict(width=0),
                name="SL Zone",
                showlegend=False,
                hoverinfo="skip",
            ), row=1, col=1)

    # RSI chart
    fig.add_trace(go.Scatter(x=df["datetime"], y=df["rsi"], name="RSI(14)", line=dict(color="#9c27b0", width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", row=2, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="#999", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", row=2, col=1)
    fig.add_hline(y=RSI_PULLBACK_LONG, line_dash="dot", line_color="#ff9800", row=2, col=1)
    fig.add_hline(y=RSI_PULLBACK_SHORT, line_dash="dot", line_color="#ff9800", row=2, col=1)

    # Trend regime
    trend_colors = {"UPTREND": "#26a69a", "DOWNTREND": "#ef5350", "RANGE": "#999"}
    for trend, color in trend_colors.items():
        mask = df["trend"] == trend
        fig.add_trace(go.Scatter(
            x=df.loc[mask, "datetime"],
            y=[1] * mask.sum(),
            mode="markers",
            marker=dict(color=color, size=8),
            name=trend,
            showlegend=True,
        ), row=3, col=1)

    # Layout
    fig.update_layout(
        title=dict(
            text="Qwen OCPM Strategy - Next Entry Signal | BTC/USDT 4H",
            font=dict(size=16),
            x=0.5,
        ),
        height=900,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
    )

    fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="Trend", visible=False, row=3, col=1)

    return fig


def main():
    print("=" * 70)
    print(" Qwen OCPM Strategy - Next Entry Signal Chart")
    print("=" * 70)
    print()
    print("Fetching OHLCV data...")
    df = fetch_ohlcv()
    print(f"Data: {len(df)} bars ({df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]})")

    print("Computing indicators...")
    df = compute_indicators(df)

    print("Finding next entry signal...")
    signals = find_next_signal(df)

    if signals:
        for sig in signals:
            print(f"\n  Type:    {sig['type']}")
            print(f"  Time:    {sig['datetime']}")
            print(f"  Entry:   ${sig['entry']:,.2f}")
            print(f"  SL:      ${sig['sl']:,.2f}")
            print(f"  TP:      ${sig['tp']:,.2f}")
            print(f"  ATR:     ${sig['atr']:,.2f}")
            print(f"  RSI:     {sig['rsi']:.1f}")
            print(f"  R:R:     1:{sig['rr']:.1f}")
            print(f"  Trend:   {sig['trend']}")
    else:
        print("\n  No active signal found. Chart will show recent signals.")

    print("\nBuilding chart...")
    fig = build_chart(df, signals)

    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocpm_signal_chart.html")
    fig.write_html(output_file)
    print(f"\nChart saved: {output_file}")
    print("Opening in browser...")

    import webbrowser
    webbrowser.open(f"file://{output_file}")


if __name__ == "__main__":
    main()
