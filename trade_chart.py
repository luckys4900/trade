#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC/USDT Trading Chart Viewer - RSI Swing v6 対応
hl_rsi_swing_v6.py のトレード状況をリアルタイムチャートで表示
- ATRベースのSL/TPを実ログから取得・表示
- EMA(50)フィルターを描画
- RSI 30/70 閾値で表示
"""

import os
import sys
import json
import glob
import re
import logging
import webbrowser
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ═══════════════════════════════════════════════════════════════════════════
# ロギング設定
# ═══════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 設定読み込み
# ═══════════════════════════════════════════════════════════════════════════

def load_config():
    """config.json を読み込む"""
    config_path = Path(__file__).parent / "config.json"

    if not config_path.exists():
        logger.error(f"config.json not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    logger.info(f"Config loaded: timeframe={config.get('timeframe', '4h')}, sl_atr={config.get('sl_atr', 1.5)}, tp_atr={config.get('tp_atr', 3.0)}")
    return config

# ═══════════════════════════════════════════════════════════════════════════
# ログ解析：エントリー・SL・TP情報取得（新しい形式）
# ═══════════════════════════════════════════════════════════════════════════

def get_entry_price_from_log(script_dir):
    """
    最新のログファイル（rsi_swing_*.log）からエントリー・SL・TP情報を取得
    フォールバック: trader_*.log も確認

    Returns:
        {
            'entry_price': float or None,
            'in_position': bool,
            'position_side': 'long' | 'short' | None,
            'sl_price': float or None,
            'tp_price': float or None,
        }
    """
    # 新しいログファイル（優先）
    log_files_new = sorted(
        glob.glob(str(script_dir / "rsi_swing_*.log")),
        reverse=True
    )

    # 古いログファイル（フォールバック）
    log_files_old = sorted(
        glob.glob(str(script_dir / "trader_*.log")),
        reverse=True
    )

    log_files = log_files_new + log_files_old

    if not log_files:
        logger.warning("No log files found (rsi_swing_*.log or trader_*.log)")
        return {
            'entry_price': None,
            'in_position': False,
            'position_side': None,
            'sl_price': None,
            'tp_price': None,
        }

    latest_log = log_files[0]
    logger.info(f"Analyzing log: {latest_log}")

    with open(latest_log, 'r', encoding='utf-8') as f:
        content = f.read()

    # ═══ LONG/SHORT エントリーパターン ═══
    # 例: OPEN LONG @ 42500.00 | SL=41300.00 TP=44900.00 qty_est=0.001234
    long_entry_pattern = r"OPEN LONG @ ([\d.]+) \| SL=([\d.]+) TP=([\d.]+)"
    short_entry_pattern = r"OPEN SHORT @ ([\d.]+) \| SL=([\d.]+) TP=([\d.]+)"

    # ═══ ポジション状態パターン ═══
    # 例: In position (long). SL=41300.00 TP=44900.00 | Entry=42500.00
    long_position_pattern = r"In position \(long\)\. SL=([\d.]+) TP=([\d.]+) \| Entry=([\d.]+)"
    short_position_pattern = r"In position \(short\)\. SL=([\d.]+) TP=([\d.]+) \| Entry=([\d.]+)"

    # ═══ クローズパターン ═══
    # 例: CLOSE LONG @ 44900.00 (entry=42500.00)
    close_long_pattern = r"CLOSE LONG @ ([\d.]+)"
    close_short_pattern = r"CLOSE SHORT @ ([\d.]+)"

    entry_price = None
    sl_price = None
    tp_price = None
    position_side = None
    in_position = False

    # === LONG エントリーを検索 ===
    long_entry_matches = list(re.finditer(long_entry_pattern, content))
    if long_entry_matches:
        last_long_entry = long_entry_matches[-1]
        entry_price = float(last_long_entry.group(1))
        sl_price = float(last_long_entry.group(2))
        tp_price = float(last_long_entry.group(3))
        position_side = "long"
        in_position = True
        logger.info(f"Latest LONG entry: price=${entry_price}, SL=${sl_price}, TP=${tp_price}")

        # その後のクローズを確認
        close_long_matches = list(re.finditer(close_long_pattern, content))
        if close_long_matches:
            last_close = close_long_matches[-1]
            if last_close.start() > last_long_entry.start():
                in_position = False
                logger.info("LONG position closed")

    # === SHORT エントリーを検索 ===
    short_entry_matches = list(re.finditer(short_entry_pattern, content))
    if short_entry_matches:
        last_short_entry = short_entry_matches[-1]

        # LONG と SHORT を比較、より新しい方を採用
        if not long_entry_matches or last_short_entry.start() > long_entry_matches[-1].start():
            entry_price = float(last_short_entry.group(1))
            sl_price = float(last_short_entry.group(2))
            tp_price = float(last_short_entry.group(3))
            position_side = "short"
            in_position = True
            logger.info(f"Latest SHORT entry: price=${entry_price}, SL=${sl_price}, TP=${tp_price}")

            # その後のクローズを確認
            close_short_matches = list(re.finditer(close_short_pattern, content))
            if close_short_matches:
                last_close = close_short_matches[-1]
                if last_close.start() > last_short_entry.start():
                    in_position = False
                    logger.info("SHORT position closed")

    # === ポジション状態から最新のSL/TP/Entryを取得 ===
    # より新しい"In position"ログがあればそちらを優先
    long_position_matches = list(re.finditer(long_position_pattern, content))
    short_position_matches = list(re.finditer(short_position_pattern, content))

    if long_position_matches:
        last_long_pos = long_position_matches[-1]
        sl_price = float(last_long_pos.group(1))
        tp_price = float(last_long_pos.group(2))
        entry_price = float(last_long_pos.group(3))
        position_side = "long"
        in_position = True

    if short_position_matches:
        last_short_pos = short_position_matches[-1]

        # より新しい方を採用
        if not long_position_matches or last_short_pos.start() > long_position_matches[-1].start():
            sl_price = float(last_short_pos.group(1))
            tp_price = float(last_short_pos.group(2))
            entry_price = float(last_short_pos.group(3))
            position_side = "short"
            in_position = True

    return {
        'entry_price': entry_price,
        'in_position': in_position,
        'position_side': position_side,
        'sl_price': sl_price,
        'tp_price': tp_price,
    }

# ═══════════════════════════════════════════════════════════════════════════
# Hyperliquid API：ローソク足取得
# ═══════════════════════════════════════════════════════════════════════════

def get_candles(symbol, interval, limit=100, mainnet=True):
    """
    Hyperliquid API からローソク足を取得

    Args:
        symbol: "BTC"
        interval: "1h", "4h" など
        limit: 本数（デフォルト100）
        mainnet: True=mainnet, False=testnet

    Returns:
        list of {'t': timestamp, 'o': open, 'h': high, 'l': low, 'c': close, 'v': volume}
    """
    base_url = "https://api.hyperliquid.xyz/info" if mainnet else "https://api.hyperliquid-testnet.xyz/info"

    # タイムフレームをミリ秒に変換
    interval_map = {
        '1m': 60_000,
        '5m': 5 * 60_000,
        '15m': 15 * 60_000,
        '30m': 30 * 60_000,
        '1h': 60 * 60_000,
        '4h': 4 * 60 * 60_000,
        '1d': 24 * 60 * 60_000,
    }

    interval_ms = interval_map.get(interval, 60 * 60_000)
    now = int(datetime.utcnow().timestamp() * 1000)
    start_time = now - (limit * interval_ms)

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": now
        }
    }

    logger.info(f"Fetching {limit} {interval} candles for {symbol}...")

    try:
        response = requests.post(base_url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            logger.info(f"Fetched {len(data)} candles")
            return data
        else:
            logger.error(f"Unexpected response format: {data}")
            return []

    except Exception as e:
        logger.error(f"Error fetching candles: {e}")
        return []

# ═══════════════════════════════════════════════════════════════════════════
# インジケーター計算
# ═══════════════════════════════════════════════════════════════════════════

def calculate_rsi(closes, period=14):
    """
    RSI を計算（SMA ベース）
    """
    closes_series = pd.Series(closes)
    delta = closes_series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    return rsi.values

def calculate_ema(closes, period=50):
    """
    EMA を計算（Wilder式、ewm adjust=False）
    """
    return pd.Series(closes).ewm(span=period, adjust=False).mean().values

def calculate_atr(highs, lows, closes, period=14):
    """
    ATR を計算（Wilder式）
    """
    h, l, c = pd.Series(highs), pd.Series(lows), pd.Series(closes)
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean().values

# ═══════════════════════════════════════════════════════════════════════════
# チャート生成
# ═══════════════════════════════════════════════════════════════════════════

def find_next_signal_level(df, rsi_oversold=30, rsi_overbought=70, lookback=20):
    """
    次のRSIシグナル発動が来そうな価格レベルを推定

    現在のRSI値を見て、次のシグナル（30 or 70 クロス）が来そうな
    価格レベルを直近のスイング高値・安値から推定する

    Returns:
        (signal_price, signal_direction)
        - signal_price: シグナル発動時の想定価格（直近のスイング）
        - signal_direction: 'long' または 'short'
    """
    if len(df) < 2:
        return None, None

    current_rsi = df['rsi'].iloc[-1]
    recent_df = df.tail(lookback).reset_index(drop=True)

    signal_price = None
    signal_direction = None

    # RSI のトレンド判定：前のローソク足との比較
    rsi_is_falling = current_rsi < df['rsi'].iloc[-2]
    rsi_is_rising = current_rsi > df['rsi'].iloc[-2]

    # LONG 可能性：RSI が下降中（30 方向）
    if (current_rsi <= rsi_overbought and rsi_is_falling) or (current_rsi < 50):
        # 次は LONG シグナル（RSI 30クロス）の可能性
        # 直近のスイング安値（ロー）を想定エントリーレベルとする
        signal_price = recent_df['low'].min()
        signal_direction = 'long'

    # SHORT 可能性：RSI が上昇中（70 方向）
    elif (current_rsi >= rsi_oversold and rsi_is_rising) or (current_rsi > 50):
        # 次は SHORT シグナル（RSI 70クロス）の可能性
        # 直近のスイング高値（ハイ）を想定エントリーレベルとする
        signal_price = recent_df['high'].max()
        signal_direction = 'short'


    return signal_price, signal_direction

def create_chart(candles, config, entry_info, script_dir):
    """
    Plotly でチャートを生成（RSI Swing v6対応）
    """
    if not candles:
        logger.error("No candle data available")
        return None

    # データを pandas DataFrame に変換
    df = pd.DataFrame(candles)
    df['t'] = pd.to_datetime(df['t'].astype(int), unit='ms')
    df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})

    # 数値列を float に変換
    df['open'] = pd.to_numeric(df['open'], errors='coerce')
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

    # インジケーター計算
    rsi_values = calculate_rsi(df['close'].values, period=14)
    ema_values = calculate_ema(df['close'].values, period=50)
    atr_values = calculate_atr(df['high'].values, df['low'].values, df['close'].values, period=14)

    df['rsi'] = rsi_values
    df['ema50'] = ema_values
    df['atr'] = atr_values

    current_price = df['close'].iloc[-1] if not df.empty else None
    current_rsi = df['rsi'].iloc[-1] if not df['rsi'].empty else None
    current_atr = df['atr'].iloc[-1] if not df['atr'].empty else None

    # エントリー情報（ログから取得）
    entry_price = entry_info.get('entry_price')
    in_position = entry_info.get('in_position')
    position_side = entry_info.get('position_side')
    sl_price = entry_info.get('sl_price')
    tp_price = entry_info.get('tp_price')

    # ログからSL/TPが取得できない場合、ATRベースで計算
    if entry_price and not sl_price:
        sl_atr = config.get('sl_atr', 1.5)
        tp_atr = config.get('tp_atr', 3.0)
        sl_dist = current_atr * sl_atr if current_atr else 0
        tp_dist = current_atr * tp_atr if current_atr else 0

        if position_side == 'long':
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        elif position_side == 'short':
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist

    # === チャート生成 ===
    timeframe = config.get('timeframe', '4h').upper()
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.12,
        subplot_titles=(f"BTC/USDT {timeframe}", "RSI (14) | ATR (14)")
    )

    # ローソク足
    fig.add_trace(
        go.Candlestick(
            x=df['t'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='BTC/USDT',
            hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>O:%{open:.2f}<br>H:%{high:.2f}<br>L:%{low:.2f}<br>C:%{close:.2f}'
        ),
        row=1, col=1
    )

    # === EMA(50) ===
    fig.add_trace(
        go.Scatter(
            x=df['t'],
            y=df['ema50'],
            mode='lines',
            name='EMA(50)',
            line=dict(color='orange', width=1.5),
            hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>EMA50: %{y:.2f}'
        ),
        row=1, col=1
    )

    # === エントリー価格ライン（緑） ===
    if entry_price:
        fig.add_hline(
            y=entry_price,
            line_color="green",
            line_width=2,
            line_dash="solid",
            annotation_text=f" ENT ${entry_price:,.2f}",
            annotation_position="right",
            row=1, col=1
        )

    # === TP ライン（青 破線） ===
    if tp_price:
        tp_atr_mult = config.get('tp_atr', 3.0)
        fig.add_hline(
            y=tp_price,
            line_color="blue",
            line_width=1.5,
            line_dash="dash",
            annotation_text=f" TP ${tp_price:,.2f} ({tp_atr_mult}×ATR)",
            annotation_position="right",
            row=1, col=1
        )

    # === SL ライン（赤 破線） ===
    if sl_price:
        sl_atr_mult = config.get('sl_atr', 1.5)
        fig.add_hline(
            y=sl_price,
            line_color="red",
            line_width=1.5,
            line_dash="dash",
            annotation_text=f" SL ${sl_price:,.2f} ({sl_atr_mult}×ATR)",
            annotation_position="right",
            row=1, col=1
        )

    # === RSI ===
    fig.add_trace(
        go.Scatter(
            x=df['t'],
            y=df['rsi'],
            mode='lines',
            name='RSI(14)',
            line=dict(color='purple', width=2),
            hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>RSI: %{y:.2f}'
        ),
        row=2, col=1
    )

    # === RSI 30 ライン（グリーン） ===
    fig.add_hline(
        y=30,
        line_color="green",
        line_width=1,
        line_dash="dash",
        annotation_text=" 30",
        annotation_position="left",
        row=2, col=1
    )

    # === RSI 70 ライン（レッド） ===
    fig.add_hline(
        y=70,
        line_color="red",
        line_width=1,
        line_dash="dash",
        annotation_text=" 70",
        annotation_position="left",
        row=2, col=1
    )

    # === RSI 背景色（オーバーソールド） ===
    fig.add_hrect(
        y0=0, y1=30,
        fillcolor="green",
        opacity=0.1,
        layer="below",
        row=2, col=1
    )

    # === RSI 背景色（オーバーボート） ===
    fig.add_hrect(
        y0=70, y1=100,
        fillcolor="red",
        opacity=0.1,
        layer="below",
        row=2, col=1
    )

    # === R:R比の計算と表示 ===
    rr_ratio = None
    if entry_price and sl_price and tp_price:
        if position_side == 'long':
            risk = entry_price - sl_price
            reward = tp_price - entry_price
        else:  # short
            risk = sl_price - entry_price
            reward = entry_price - tp_price

        if risk > 0:
            rr_ratio = reward / risk

    # === 過去のシグナルレベルを検出 ===
    rsi_oversold = config.get('rsi_oversold', 30)
    rsi_overbought = config.get('rsi_overbought', 70)

    signal_price, signal_direction = find_next_signal_level(df, rsi_oversold, rsi_overbought, lookback=20)

    # === 想定エントリー表示（フラット時のみ） ===
    sim_entry = None
    sim_sl = None
    sim_tp = None
    sim_rr_ratio = None

    if not in_position and signal_price is not None and signal_direction is not None and current_atr is not None:
        # 想定エントリー = 過去のシグナルレベル
        sim_entry = signal_price

        # SL/TP計算
        sl_atr = config.get('sl_atr', 1.5)
        tp_atr = config.get('tp_atr', 3.0)
        sl_dist = current_atr * sl_atr
        tp_dist = current_atr * tp_atr

        if signal_direction == 'long':
            sim_sl = sim_entry - sl_dist
            sim_tp = sim_entry + tp_dist
        else:  # short
            sim_sl = sim_entry + sl_dist
            sim_tp = sim_entry - tp_dist

        # R:R比計算
        if signal_direction == 'long':
            risk = sim_entry - sim_sl
            reward = sim_tp - sim_entry
        else:
            risk = sim_sl - sim_entry
            reward = sim_entry - sim_tp

        if risk > 0:
            sim_rr_ratio = reward / risk

        # === 現在時刻の縦線（白 点線） ===
        latest_time = df['t'].iloc[-1]
        fig.add_vline(
            x=latest_time,
            line_color="white",
            line_width=1,
            line_dash="dot",
            row=1, col=1
        )

        # === 想定ENT（白 実線） ===
        fig.add_hline(
            y=sim_entry,
            line_color="white",
            line_width=2,
            line_dash="solid",
            annotation_text=f" SIGNAL @ ${sim_entry:,.2f}",
            annotation_position="right",
            row=1, col=1
        )

        # === 想定TP（シアン 点線） ===
        fig.add_hline(
            y=sim_tp,
            line_color="cyan",
            line_width=1.5,
            line_dash="dot",
            annotation_text=f" TP ${sim_tp:,.2f}",
            annotation_position="right",
            row=1, col=1
        )

        # === 想定SL（サーモン 点線） ===
        fig.add_hline(
            y=sim_sl,
            line_color="salmon",
            line_width=1.5,
            line_dash="dot",
            annotation_text=f" SL ${sim_sl:,.2f}",
            annotation_position="right",
            row=1, col=1
        )

    # === レイアウト ===
    position_str = "HOLDING" if in_position else "FLAT"
    title_text = f"BTC/USDT {timeframe} | RSI: {current_rsi:.2f} | Price: ${current_price:,.2f} | {position_str}"

    if entry_price:
        title_text += f" | Entry: ${entry_price:,.2f}"

    if rr_ratio:
        title_text += f" | R:R: 1:{rr_ratio:.2f}"

    # 想定エントリー情報を追加（フラット時）
    if sim_entry and signal_direction:
        sim_dir_text = "想定LONG" if signal_direction == 'long' else "想定SHORT"
        title_text += f" | {sim_dir_text}: SIGNAL @ ${sim_entry:,.2f} / SL ${sim_sl:,.2f} / TP ${sim_tp:,.2f}"
        if sim_rr_ratio:
            title_text += f" | R:R 1:{sim_rr_ratio:.2f}"

    fig.update_layout(
        title=title_text,
        template="plotly_dark",
        height=800,
        hovermode='x unified',
        xaxis_rangeslider_visible=False,
    )

    # Y 軸設定
    fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
    fig.update_yaxes(title_text="RSI / ATR", row=2, col=1, range=[0, 100])

    logger.info(f"Chart created: {current_rsi:.2f} RSI, ${current_price:,.2f} Price, Position: {position_str}")
    if rr_ratio:
        logger.info(f"R:R Ratio: 1:{rr_ratio:.2f}")
    if sim_entry and signal_direction:
        logger.info(f"Next signal estimate: {signal_direction.upper()} @ ${sim_entry:,.2f}, SL=${sim_sl:,.2f}, TP=${sim_tp:,.2f}, R:R=1:{sim_rr_ratio:.2f}" if sim_rr_ratio else f"Next signal estimate: {signal_direction.upper()} @ ${sim_entry:,.2f}")

    return fig

# ═══════════════════════════════════════════════════════════════════════════
# メイン
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """メイン処理"""
    script_dir = Path(__file__).parent

    logger.info("=" * 70)
    logger.info(" BTC/USDT Trading Chart Generator - RSI Swing v6")
    logger.info("=" * 70)

    # 設定読み込み
    config = load_config()
    symbol = config.get('symbol', 'BTC')
    timeframe = config.get('timeframe', '4h')
    environment = config.get('environment', 'mainnet')
    mainnet = (environment == 'mainnet')

    # ログからエントリー情報取得
    logger.info("Fetching entry information from logs...")
    entry_info = get_entry_price_from_log(script_dir)
    logger.info(f"Entry info: {entry_info}")

    # Hyperliquid API からローソク足取得
    logger.info(f"Fetching {symbol} {timeframe} candles from Hyperliquid...")
    candles = get_candles(symbol, timeframe, limit=100, mainnet=mainnet)

    if not candles:
        logger.error("Failed to fetch candles")
        print("[ERROR] チャート生成に失敗しました")
        sys.exit(1)

    # チャート生成
    logger.info("Generating chart...")
    fig = create_chart(candles, config, entry_info, script_dir)

    if not fig:
        logger.error("Failed to create chart")
        print("[ERROR] チャート作成に失敗しました")
        sys.exit(1)

    # HTML 保存
    output_path = script_dir / "trade_chart.html"
    logger.info(f"Saving chart to {output_path}...")
    fig.write_html(str(output_path))

    logger.info(f"Chart saved successfully")
    print(f"[OK] チャート生成完了: {output_path}")

    # ブラウザで開く
    logger.info("Opening browser...")
    webbrowser.open(f"file:///{output_path}")

    print("[OK] ブラウザで開きました")

if __name__ == "__main__":
    main()
