# -*- coding: utf-8 -*-
"""
Qwen OCPM Strategy - Signal Monitor with Alerts
Monitors market and shows popup/alert when entry signal approaches
"""

import os
import sys
import time
import threading
import winsound
from datetime import datetime, timedelta
from ctypes import windll

import pandas as pd
import numpy as np
import requests

# Strategy parameters
EMA_FAST = 21
EMA_SLOW = 55
RSI_PERIOD = 14
RSI_PULLBACK_LONG = 48.0
RSI_PULLBACK_SHORT = 52.0
ATR_PERIOD = 14
ATR_SL_MULT = 3.0
ATR_TP_MULT = 6.0
RSI_OVERHEAT = 70.0

CHECK_INTERVAL = 60  # seconds
SYMBOL = "BTC/USDT"
TIMEFRAME = "4h"
LOOKBACK_BARS = 200

# Alert state
last_alert_time = None
ALERT_COOLDOWN = 1800  # 30 minutes between alerts


def fetch_ohlcv():
    """Fetch OHLCV from Binance public API (no API key needed)"""
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": "BTCUSDT",
        "interval": TIMEFRAME.replace("h", "h").replace("m", "m"),
        "limit": LOOKBACK_BARS,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["datetime"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms", utc=True).dt.tz_localize(None)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["datetime", "open", "high", "low", "close", "volume"]].sort_values("datetime").reset_index(drop=True)


def compute_indicators(df):
    """Compute EMA, RSI, ATR, trend, signals"""
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df["ema_fast_slope"] = df["ema_fast"].pct_change(10)

    df["trend"] = "RANGE"
    df.loc[(df["close"] > df["ema_slow"]) & (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast_slope"] > 0), "trend"] = "UPTREND"
    df.loc[(df["close"] < df["ema_slow"]) & (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast_slope"] < 0), "trend"] = "DOWNTREND"

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)

    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/ATR_PERIOD, min_periods=ATR_PERIOD).mean()

    # Signal conditions
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

    # Proximity warning: approaching signal conditions
    df["long_warning"] = (
        (df["trend"] == "UPTREND") &
        (df["rsi"] <= RSI_PULLBACK_LONG + 5) &
        (df["rsi"] > RSI_PULLBACK_LONG) &
        (df["rsi"] < 55)
    ).astype(int)

    df["short_warning"] = (
        (df["trend"] == "DOWNTREND") &
        (df["rsi"] >= RSI_PULLBACK_SHORT - 5) &
        (df["rsi"] < RSI_PULLBACK_SHORT) &
        (df["rsi"] > 45)
    ).astype(int)

    return df


def show_windows_popup(title, message, icon_type="info"):
    """Show Windows popup notification"""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=10, icon_path=None, threaded=True)
    except ImportError:
        pass

    # Fallback: MessageBox
    try:
        MB_ICONINFORMATION = 0x40
        MB_ICONWARNING = 0x30
        MB_OK = 0x0
        icon = MB_ICONINFORMATION if icon_type == "info" else MB_ICONWARNING
        windll.user32.MessageBoxW(0, message, title, MB_OK | icon)
    except Exception:
        pass


def play_alert_sound():
    """Play alert sound"""
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        time.sleep(0.3)
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        time.sleep(0.3)
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


def check_signals(df):
    """Check for signals on the latest bars"""
    signals = []

    for i in range(max(0, len(df) - 3), len(df)):
        row = df.iloc[i]

        if row["long_entry"] == 1:
            atr = row["atr"]
            entry = row["close"]
            signals.append({
                "type": "LONG",
                "level": "SIGNAL",
                "datetime": row["datetime"],
                "price": entry,
                "sl": entry - (ATR_SL_MULT * atr),
                "tp": entry + (ATR_TP_MULT * atr),
                "rsi": row["rsi"],
                "trend": row["trend"],
                "atr": atr,
            })

        elif row["short_entry"] == 1:
            atr = row["atr"]
            entry = row["close"]
            signals.append({
                "type": "SHORT",
                "level": "SIGNAL",
                "datetime": row["datetime"],
                "price": entry,
                "sl": entry + (ATR_SL_MULT * atr),
                "tp": entry - (ATR_TP_MULT * atr),
                "rsi": row["rsi"],
                "trend": row["trend"],
                "atr": atr,
            })

        elif row["long_warning"] == 1:
            signals.append({
                "type": "LONG",
                "level": "WARNING",
                "datetime": row["datetime"],
                "price": row["close"],
                "rsi": row["rsi"],
                "trend": row["trend"],
            })

        elif row["short_warning"] == 1:
            signals.append({
                "type": "SHORT",
                "level": "WARNING",
                "datetime": row["datetime"],
                "price": row["close"],
                "rsi": row["rsi"],
                "trend": row["trend"],
            })

    return signals


def monitor_loop():
    """Main monitoring loop"""
    global last_alert_time

    print("=" * 70)
    print(" Qwen OCPM Signal Monitor - Alert System")
    print("=" * 70)
    print()
    print(f"Monitoring: {SYMBOL} {TIMEFRAME}")
    print(f"Check interval: {CHECK_INTERVAL}s")
    print(f"Alert cooldown: {ALERT_COOLDOWN}s")
    print()
    print("Waiting for signals... (Press Ctrl+C to stop)")
    print("-" * 70)

    while True:
        try:
            now = datetime.now()
            print(f"[{now.strftime('%H:%M:%S')}] Checking...")

            df = fetch_ohlcv()
            df = compute_indicators(df)

            current_price = df.iloc[-1]["close"]
            current_rsi = df.iloc[-1]["rsi"]
            current_trend = df.iloc[-1]["trend"]

            print(f"  Price: ${current_price:,.2f} | RSI: {current_rsi:.1f} | Trend: {current_trend}")

            signals = check_signals(df)

            if signals:
                for sig in signals:
                    # Check cooldown
                    if last_alert_time and (now - last_alert_time).total_seconds() < ALERT_COOLDOWN:
                        print(f"  >> Signal detected but in cooldown period")
                        continue

                    if sig["level"] == "SIGNAL":
                        last_alert_time = now
                        play_alert_sound()

                        title = f"Qwen OCPM - {sig['type']} ENTRY SIGNAL"
                        msg = (f"{sig['type']} Entry\n"
                               f"Price: ${sig['price']:,.2f}\n"
                               f"SL: ${sig['sl']:,.2f}\n"
                               f"TP: ${sig['tp']:,.2f}\n"
                               f"RSI: {sig['rsi']:.1f}\n"
                               f"ATR: ${sig['atr']:,.2f}")

                        print(f"\n  *** {title} ***")
                        print(f"  {msg}")
                        print()

                        show_windows_popup(title, msg)

                    elif sig["level"] == "WARNING":
                        print(f"  >> WARNING: {sig['type']} approaching (RSI: {sig['rsi']:.1f})")

            else:
                # Show proximity info
                last = df.iloc[-1]
                if last["trend"] == "UPTREND":
                    dist_to_long = last["rsi"] - RSI_PULLBACK_LONG
                    if 0 < dist_to_long < 10:
                        print(f"  >> LONG approaching: RSI {last['rsi']:.1f} (need <= {RSI_PULLBACK_LONG})")
                elif last["trend"] == "DOWNTREND":
                    dist_to_short = RSI_PULLBACK_SHORT - last["rsi"]
                    if 0 < dist_to_short < 10:
                        print(f"  >> SHORT approaching: RSI {last['rsi']:.1f} (need >= {RSI_PULLBACK_SHORT})")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nMonitor stopped by user.")
            break
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_loop()
