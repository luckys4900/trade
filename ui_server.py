#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Grid Trading Bot - Streamlit UI
リアルタイム取引情報表示 UI
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import Dict, Optional
import traceback

from state_manager import StateManager
from chart_builder import ChartBuilder
from ui_config import (
    UPDATE_INTERVAL, RSI_PERIOD, ATR_PERIOD,
    READY_THRESHOLD, WARN_THRESHOLD,
    COLOR_READY, COLOR_WARN, COLOR_FAR,
    COLOR_BUY_LEVEL, COLOR_SELL_LEVEL, COLOR_CURRENT_PRICE
)

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================================================
# Step 1: Streamlit ページ設定
# ==============================================================================

st.set_page_config(
    page_title="GridBot Realtime UI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ==============================================================================
# Step 2: CSS スタイル定義
# ==============================================================================

st.markdown("""
<style>
    /* メトリックボックススタイル */
    .metric-box {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 20px;
        border-radius: 8px;
        border-left: 4px solid #2196F3;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    .metric-box.ready {
        border-left-color: #5cb85c;
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
    }

    .metric-box.warn {
        border-left-color: #f0ad4e;
        background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
    }

    .metric-box.critical {
        border-left-color: #d9534f;
        background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
    }

    /* パネルセクション */
    .panel-section {
        background: white;
        padding: 16px;
        border-radius: 6px;
        margin: 10px 0;
        border: 1px solid #e0e0e0;
    }

    .panel-title {
        font-size: 16px;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 12px;
        border-bottom: 2px solid #2196F3;
        padding-bottom: 8px;
    }

    .gauge-container {
        width: 100%;
        height: 30px;
        background: #ecf0f1;
        border-radius: 4px;
        overflow: hidden;
        margin: 8px 0;
    }

    .gauge-fill {
        height: 100%;
        background: linear-gradient(90deg, #5cb85c 0%, #f0ad4e 50%, #d9534f 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 12px;
        font-weight: bold;
    }

    .indicator-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin: 8px 0;
    }

    .indicator-item {
        background: #f5f5f5;
        padding: 8px;
        border-radius: 4px;
        text-align: center;
        border-left: 3px solid #2196F3;
    }

    .indicator-item.up {
        border-left-color: #5cb85c;
    }

    .indicator-item.down {
        border-left-color: #d9534f;
    }

    .indicator-label {
        font-size: 11px;
        color: #666;
        text-transform: uppercase;
    }

    .indicator-value {
        font-size: 14px;
        font-weight: bold;
        color: #2c3e50;
        margin-top: 4px;
    }

    .grid-state-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
        margin-top: 10px;
    }

    .grid-state-table th {
        background: #2196F3;
        color: white;
        padding: 8px;
        text-align: left;
        border: 1px solid #ddd;
    }

    .grid-state-table td {
        padding: 8px;
        border: 1px solid #ddd;
        background: white;
    }

    .grid-state-table tr:nth-child(even) td {
        background: #f5f5f5;
    }

    .grid-state-table .buy {
        color: #4a90e2;
        font-weight: bold;
    }

    .grid-state-table .sell {
        color: #e94b3c;
        font-weight: bold;
    }

    .grid-state-table .filled {
        color: #2c3e50;
        font-weight: bold;
    }

    /* ヘッダースタイル */
    .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
        padding: 16px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 8px;
        color: white;
    }

    .header h1 {
        margin: 0;
        font-size: 28px;
    }

    .header-time {
        font-size: 12px;
        opacity: 0.9;
    }

    /* エラー・警告スタイル */
    .error-box {
        background: #ffebee;
        border-left: 4px solid #d9534f;
        padding: 12px;
        border-radius: 4px;
        color: #c62828;
    }

    .warning-box {
        background: #fff3e0;
        border-left: 4px solid #f0ad4e;
        padding: 12px;
        border-radius: 4px;
        color: #e65100;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# Step 3: StateManager インスタンスのキャッシング
# ==============================================================================

@st.cache_resource
def get_state_manager() -> StateManager:
    """StateManager をキャッシュして保持"""
    logger.info("初期化: StateManager")
    state_manager = StateManager()
    return state_manager


# ==============================================================================
# Step 4: データ更新関数
# ==============================================================================

def update_data(state_manager: StateManager) -> Dict:
    """
    StateManager からデータ取得

    Returns:
        Dict: 更新されたデータ
    """
    try:
        logger.info("データ更新中...")
        data = state_manager.update()
        logger.info(f"データ更新完了")
        return data
    except Exception as e:
        logger.error(f"データ更新エラー: {e}")
        logger.error(traceback.format_exc())
        return {
            "current_price": None,
            "ohlcv": None,
            "grid_state": {},
            "indicators": {}
        }


def calculate_readiness_gauge(current_price: float, buy_levels: list, sell_levels: list) -> tuple:
    """
    準備度ゲージ計算
    - 最も近い買いレベルと売りレベルまでの距離から、準備度を計算

    Returns:
        tuple: (readiness_pct, status, color)
    """
    if not buy_levels or not sell_levels or current_price is None:
        return 0, "FAR", COLOR_FAR

    # 最も近い買いレベル（価格より下）
    closest_buy = max([b for b in buy_levels if b < current_price], default=None)
    # 最も近い売りレベル（価格より上）
    closest_sell = min([s for s in sell_levels if s > current_price], default=None)

    if closest_buy is None or closest_sell is None:
        return 0, "FAR", COLOR_FAR

    # 価格幅
    price_range = closest_sell - closest_buy
    if price_range <= 0:
        return 0, "FAR", COLOR_FAR

    # 現在価格までの距離（買いレベルから）
    distance_from_buy = current_price - closest_buy
    readiness_pct = (distance_from_buy / price_range) * 100

    # ステータス判定
    if readiness_pct <= READY_THRESHOLD:
        status = "READY"
        color = COLOR_READY
    elif readiness_pct <= WARN_THRESHOLD:
        status = "WARN"
        color = COLOR_WARN
    else:
        status = "FAR"
        color = COLOR_FAR

    return readiness_pct, status, color


# ==============================================================================
# Step 5: メインレイアウト（2 列）構築
# ==============================================================================

def main():
    """メインアプリケーション"""

    # StateManager 取得
    state_manager = get_state_manager()

    # ヘッダー
    st.markdown(f"""
    <div class="header">
        <div>
            <h1>📊 GridBot Realtime UI</h1>
            <p style="margin: 4px 0; font-size: 14px;">リアルタイム取引情報ダッシュボード</p>
        </div>
        <div class="header-time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
    """, unsafe_allow_html=True)

    # データ更新
    data = update_data(state_manager)

    # エラーハンドリング
    if data.get("status") == "error":
        st.error(f"❌ データ取得エラー: {data.get('message', '不明なエラー')}")
        st.stop()

    current_price = data.get("current_price")
    ohlcv_data = data.get("ohlcv")
    grid_state = data.get("grid_state", {})
    indicators = data.get("indicators", {})

    if current_price is None or ohlcv_data is None:
        st.warning("⚠️ データが利用できません。Hyperliquid API から取得できませんでした。")
        st.info("API接続を確認してください。")
        st.stop()

    # 2 列レイアウト
    col_left, col_right = st.columns([2, 1], gap="medium")

    # ==============================================================================
    # Step 6: 左列（チャート表示）
    # ==============================================================================
    with col_left:
        st.markdown("<div class='panel-title'>📈 BTC/USD チャート</div>", unsafe_allow_html=True)

        try:
            # ChartBuilder でチャート HTML 生成
            chart_builder = ChartBuilder(width_percent=100)

            # グリッドレベル取得
            buy_levels = grid_state.get("buy_levels", [])
            sell_levels = grid_state.get("sell_levels", [])
            filled_levels = grid_state.get("filled_levels", set())

            chart_html = chart_builder.build_chart_html(
                ohlcv_df=ohlcv_data,
                current_price=current_price,
                buy_levels=buy_levels,
                sell_levels=sell_levels,
                filled_levels=filled_levels
            )

            # Lightweight Charts を表示
            st.components.v1.html(chart_html, height=550, scrolling=False)

        except Exception as e:
            st.error(f"❌ チャート生成エラー: {e}")
            logger.error(f"チャート生成エラー: {traceback.format_exc()}")

    # ==============================================================================
    # Step 7: 右列（パネル情報）
    # ==============================================================================
    with col_right:
        st.markdown("<div class='panel-title'>📊 トレード情報</div>", unsafe_allow_html=True)

        # --- Section 1: 現在価格 ---
        st.markdown("<div class='panel-section'>", unsafe_allow_html=True)
        st.metric(
            label="現在価格 (BTC/USD)",
            value=f"${current_price:,.2f}",
            delta=None
        )
        st.markdown("</div>", unsafe_allow_html=True)

        # --- Section 2: TP・SL レベル ---
        buy_levels = grid_state.get("buy_levels", [])
        sell_levels = grid_state.get("sell_levels", [])

        st.markdown("<div class='panel-section'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-title'>💰 TP・SL レベル</div>", unsafe_allow_html=True)

        col_tp, col_sl = st.columns(2)
        with col_tp:
            if sell_levels:
                st.metric(
                    label="売り (TP)",
                    value=f"${sell_levels[0]:,.0f}" if sell_levels else "N/A"
                )
        with col_sl:
            if buy_levels:
                st.metric(
                    label="買い (SL)",
                    value=f"${buy_levels[-1]:,.0f}" if buy_levels else "N/A"
                )

        st.markdown("</div>", unsafe_allow_html=True)

        # --- Section 3: R/R 比 ---
        st.markdown("<div class='panel-section'>", unsafe_allow_html=True)
        if buy_levels and sell_levels and current_price:
            closest_buy = max([b for b in buy_levels if b < current_price], default=buy_levels[-1])
            closest_sell = min([s for s in sell_levels if s > current_price], default=sell_levels[0])

            if closest_sell and closest_buy:
                risk = current_price - closest_buy
                reward = closest_sell - current_price
                rr_ratio = reward / risk if risk > 0 else 0

                st.metric(
                    label="Risk/Reward 比",
                    value=f"{rr_ratio:.2f}:1"
                )
        st.markdown("</div>", unsafe_allow_html=True)

        # --- Section 4: 準備度ゲージ ---
        st.markdown("<div class='panel-section'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-title'>🎯 準備度</div>", unsafe_allow_html=True)

        readiness_pct, status, color = calculate_readiness_gauge(current_price, buy_levels, sell_levels)

        # ゲージ表示
        gauge_fill_width = max(0, min(100, readiness_pct))
        st.markdown(f"""
        <div class="gauge-container">
            <div class="gauge-fill" style="width: {gauge_fill_width}%; background: {color};">
                {readiness_pct:.1f}%
            </div>
        </div>
        <p style="text-align: center; font-size: 12px; color: {color}; font-weight: bold;">
            ステータス: {status}
        </p>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # --- Section 5: インジケーター ---
        st.markdown("<div class='panel-section'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-title'>📈 インジケーター</div>", unsafe_allow_html=True)

        rsi = indicators.get("rsi", None)
        atr = indicators.get("atr", None)

        col_ind1, col_ind2 = st.columns(2)

        with col_ind1:
            if rsi is not None:
                rsi_status = "up" if rsi >= 50 else "down"
                st.markdown(f"""
                <div class="indicator-item {rsi_status}">
                    <div class="indicator-label">RSI ({RSI_PERIOD})</div>
                    <div class="indicator-value">{rsi:.1f}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("RSI: N/A")

        with col_ind2:
            if atr is not None:
                st.markdown(f"""
                <div class="indicator-item">
                    <div class="indicator-label">ATR ({ATR_PERIOD})</div>
                    <div class="indicator-value">${atr:.0f}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("ATR: N/A")

        st.markdown("</div>", unsafe_allow_html=True)

        # --- Section 6: グリッド状態 ---
        st.markdown("<div class='panel-section'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-title'>⚙️ グリッド状態</div>", unsafe_allow_html=True)

        grid_info = grid_state.get("info", {})

        col_grid1, col_grid2 = st.columns(2)
        with col_grid1:
            st.metric(
                label="買いレベル数",
                value=len(buy_levels) if buy_levels else 0
            )
        with col_grid2:
            st.metric(
                label="売りレベル数",
                value=len(sell_levels) if sell_levels else 0
            )

        # グリッドレベル詳細テーブル
        if buy_levels or sell_levels:
            st.markdown("<br>", unsafe_allow_html=True)
            st.write("**買いレベル (SL)**")
            if buy_levels:
                for i, level in enumerate(sorted(buy_levels)):
                    is_filled = level in grid_state.get("filled_levels", set())
                    status_icon = "✅" if is_filled else "⏳"
                    st.text(f"  {status_icon} Lv{i+1}: ${level:,.2f}")
            else:
                st.text("  (なし)")

            st.write("**売りレベル (TP)**")
            if sell_levels:
                for i, level in enumerate(sorted(sell_levels)):
                    is_filled = level in grid_state.get("filled_levels", set())
                    status_icon = "✅" if is_filled else "⏳"
                    st.text(f"  {status_icon} Lv{i+1}: ${level:,.2f}")
            else:
                st.text("  (なし)")

        st.markdown("</div>", unsafe_allow_html=True)

    # ==============================================================================
    # Step 8: 自動更新ロジック
    # ==============================================================================

    # Streamlit キャッシング + time.sleep で定期更新
    st.markdown(f"""
    <div style="text-align: center; color: #999; font-size: 11px; margin-top: 30px;">
        <p>最終更新: {datetime.now().strftime('%H:%M:%S')} | 自動更新間隔: {UPDATE_INTERVAL}秒</p>
    </div>
    """, unsafe_allow_html=True)

    # リアルタイム更新用プレースホルダ
    placeholder = st.empty()

    # 更新トリガー
    if "last_update_time" not in st.session_state:
        st.session_state.last_update_time = datetime.now()

    # UPDATE_INTERVAL 秒ごとに再実行
    time.sleep(UPDATE_INTERVAL)
    st.rerun()


if __name__ == "__main__":
    main()
