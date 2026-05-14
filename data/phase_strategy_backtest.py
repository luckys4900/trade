#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
規制イベント フェーズ別独立戦略 バックテスト
Strategy A~F を8イベントでテストし、ポートフォリオ最適化まで実施
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# DATA LOADING & PREPARATION
# ============================================================

def load_data():
    """BTC・ETHの日足・4h足データを読み込み"""
    # BTC日足
    btc_1d = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/btc_price_1d_extended.csv')
    btc_1d['datetime'] = pd.to_datetime(btc_1d['datetime'])
    btc_1d = btc_1d.sort_values('datetime').reset_index(drop=True)

    # BTC 4h足
    btc_4h = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/btc_price_4h_cache.csv')
    btc_4h['datetime'] = pd.to_datetime(btc_4h['datetime'])
    btc_4h = btc_4h.sort_values('datetime').reset_index(drop=True)

    # ETH 4h足
    eth_4h = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/ETH_USDT_4h_730d.csv')
    eth_4h['datetime'] = pd.to_datetime(eth_4h['datetime'])
    eth_4h = eth_4h.sort_values('datetime').reset_index(drop=True)

    # ETH日足 (4hから集約)
    eth_4h['date'] = eth_4h['datetime'].dt.date
    eth_1d = eth_4h.groupby('date').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).reset_index()
    eth_1d['datetime'] = pd.to_datetime(eth_1d['date'])
    eth_1d = eth_1d[['datetime', 'open', 'high', 'low', 'close', 'volume']]

    return btc_1d, btc_4h, eth_1d, eth_4h


def compute_indicators(df):
    """テクニカル指標を計算"""
    df = df.copy()
    for p in [3, 5, 7, 10, 20]:
        df[f'ma{p}'] = df['close'].rolling(window=p, min_periods=1).mean()
    df['ret'] = df['close'].pct_change() * 100
    df['vol20'] = df['ret'].rolling(window=20, min_periods=1).std()
    df['vol_mean20'] = df['volume'].rolling(window=20, min_periods=1).mean()
    return df


def compute_ratio(btc_1d, eth_1d):
    """BTC/ETH ratioを計算 (日足ベース)"""
    btc = btc_1d[['datetime', 'close']].rename(columns={'close': 'btc_close'})
    eth = eth_1d[['datetime', 'close']].rename(columns={'close': 'eth_close'})
    # タイムゾーンを統一してからマージ
    btc['datetime'] = pd.to_datetime(btc['datetime']).dt.tz_localize(None)
    eth['datetime'] = pd.to_datetime(eth['datetime']).dt.tz_localize(None)
    merged = pd.merge(btc, eth, on='datetime', how='inner')
    merged['ratio'] = merged['btc_close'] / merged['eth_close']
    return merged


# ============================================================
# EVENT DEFINITIONS (8 events)
# ============================================================

EVENTS = [
    {
        'name': 'FIT21 House Pass',
        'date': '2024-05-22',
        'type': 'positive',
        'description': '下院で暗号資産フレンドリー法案可決'
    },
    {
        'name': 'Trump Wins Election',
        'date': '2024-11-05',
        'type': 'positive',
        'description': '親暗号資産のトランプ大統領当選'
    },
    {
        'name': 'Gary Gensler Resignation',
        'date': '2025-01-09',
        'type': 'positive',
        'description': 'SEC議長ギンスラー辞任発表'
    },
    {
        'name': 'GENIUS Act Senate Pass',
        'date': '2025-06-17',
        'type': 'positive',
        'description': 'ステーブルコイン法案上院通過'
    },
    {
        'name': 'CLARITY Act House Pass',
        'date': '2025-07-17',
        'type': 'positive',
        'description': 'デジタル資産市場明確化法案下院通過'
    },
    {
        'name': 'Bitcoin ETF Approval (Sell News)',
        'date': '2024-01-10',
        'type': 'mixed',
        'description': 'Bitcoin ETF承認 (売り材料化)'
    },
    {
        'name': 'Ethereum ETF Approval',
        'date': '2024-05-23',
        'type': 'mixed',
        'description': 'イーサリアムETF承認'
    },
    {
        'name': 'Stablecoin Bill Stalled',
        'date': '2025-01-14',
        'type': 'negative',
        'description': 'ステーブルコイン法案棚上げ'
    },
]

SLIPPAGE_PCT = 0.15  # round-trip


# ============================================================
# STRATEGY A: Pre-event Drift
# ============================================================
def strategy_a_pre_drift(btc_1d, eth_1d, ratio_df, event_date_str):
    """
    エントリー: イベント5〜3日前
    エグジット: イベント前日または当日始値
    条件: ratio上昇トレンド + ETH弱気 + BTC強気
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    # ratioのMA等を計算
    ratio_df = ratio_df.copy()
    ratio_df['ma5'] = ratio_df['ratio'].rolling(5, min_periods=1).mean()

    btc = compute_indicators(btc_1d)
    eth = compute_indicators(eth_1d)

    for offset in [5, 4, 3]:  # イベント前5,4,3日目にエントリー候補
        entry_date = event_date - timedelta(days=offset)
        entry_row_ratio = ratio_df[ratio_df['datetime'].dt.date == entry_date]
        if entry_row_ratio.empty:
            continue

        entry_idx = ratio_df[ratio_df['datetime'].dt.date == entry_date].index[0]

        # ratio上昇トレンド: 直近5日間でratio[i] > ratio[i-1]が3日以上
        if entry_idx < 5:
            continue
        recent_ratio = ratio_df['ratio'].iloc[entry_idx-4:entry_idx+1].values
        up_days = sum(1 for i in range(1, len(recent_ratio)) if recent_ratio[i] > recent_ratio[i-1])
        if up_days < 3:
            continue

        # ETH弱気: close < MA5
        eth_entry = eth[eth['datetime'].dt.date == entry_date]
        if eth_entry.empty:
            continue
        eth_row = eth_entry.iloc[0]
        if not (eth_row['close'] < eth_row['ma5']):
            continue

        # BTC強気: close > MA5
        btc_entry = btc[btc['datetime'].dt.date == entry_date]
        if btc_entry.empty:
            continue
        btc_row = btc_entry.iloc[0]
        if not (btc_row['close'] > btc_row['ma5']):
            continue

        # エントリー確定 - ratioのロング (= BTC強い / ETH弱い)
        entry_ratio = entry_row_ratio.iloc[0]['ratio']

        # エグジット: イベント前日または当日
        for exit_offset in [1, 0]:
            exit_date = event_date - timedelta(days=exit_offset)
            exit_row = ratio_df[ratio_df['datetime'].dt.date == exit_date]
            if not exit_row.empty:
                exit_ratio = exit_row.iloc[0]['ratio']
                pnl = ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
                results.append({
                    'entry_date': str(entry_date),
                    'exit_date': str(exit_date),
                    'entry_ratio': round(entry_ratio, 6),
                    'exit_ratio': round(exit_ratio, 6),
                    'pnl_pct': round(pnl, 3),
                    'hold_days': offset - exit_offset,
                    'direction': 'LONG ratio (BTC strong / ETH weak)'
                })
                break  # 最初に見つかったエグジット日を使用

    return results


# ============================================================
# STRATEGY B: Event Day Momentum
# ============================================================
def strategy_b_event_momentum(btc_4h, eth_4h, ratio_df, event_date_str):
    """
    エントリー: イベント当日の最初の4h足でratioが前日終値比+0.3%以上動いた方向
    エグジット: 当日終値または翌日始値
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    # 前日終値のratio
    prev_date = event_date - timedelta(days=1)
    prev_ratio_row = ratio_df[ratio_df['datetime'].dt.date == prev_date]
    if prev_ratio_row.empty:
        return []
    prev_ratio = prev_ratio_row.iloc[0]['ratio']

    # 当日の4h足データ
    event_btc_4h = btc_4h[btc_4h['datetime'].dt.date == event_date].copy()
    event_eth_4h = eth_4h[eth_4h['datetime'].dt.date == event_date].copy()

    if event_btc_4h.empty or event_eth_4h.empty:
        return []

    # 最初の4h足でratioを計算
    first_btc = event_btc_4h.iloc[0]
    first_eth = event_eth_4h.iloc[0]
    if first_eth['close'] == 0:
        return []

    first_ratio = first_btc['close'] / first_eth['close']
    ratio_change = ((first_ratio / prev_ratio) - 1) * 100

    if abs(ratio_change) < 0.3:
        return []  # 方向性不十分

    direction = 1 if ratio_change > 0 else -1  # 1=LONG ratio, -1=SHORT ratio

    # 当日終値でエグジット
    last_btc = event_btc_4h.iloc[-1]
    last_eth = event_eth_4h.iloc[-1]
    exit_ratio = last_btc['close'] / last_eth['close']

    pnl = direction * ((exit_ratio / first_ratio) - 1) * 100 - SLIPPAGE_PCT

    results.append({
        'entry_time': str(first_btc['datetime']),
        'exit_time': str(last_btc['datetime']),
        'entry_ratio': round(first_ratio, 6),
        'exit_ratio': round(exit_ratio, 6),
        'initial_move_pct': round(ratio_change, 3),
        'direction': 'LONG ratio' if direction == 1 else 'SHORT ratio',
        'pnl_pct': round(pnl, 3),
        'hold_hours': 20,  # ~5本の4h足
    })

    # 翌日始値エグジット
    next_date = event_date + timedelta(days=1)
    next_btc_4h = btc_4h[btc_4h['datetime'].dt.date == next_date]
    next_eth_4h = eth_4h[eth_4h['datetime'].dt.date == next_date]
    if not next_btc_4h.empty and not next_eth_4h.empty:
        next_first_btc = next_btc_4h.iloc[0]
        next_first_eth = next_eth_4h.iloc[0]
        next_ratio = next_first_btc['close'] / next_first_eth['close']
        pnl_next = direction * ((next_ratio / first_ratio) - 1) * 100 - SLIPPAGE_PCT
        results.append({
            'entry_time': str(first_btc['datetime']),
            'exit_time': str(next_first_btc['datetime']),
            'entry_ratio': round(first_ratio, 6),
            'exit_ratio': round(next_ratio, 6),
            'initial_move_pct': round(ratio_change, 3),
            'direction': 'LONG ratio' if direction == 1 else 'SHORT ratio',
            'pnl_pct': round(pnl_next, 3),
            'hold_hours': 24,
        })

    return results


# ============================================================
# STRATEGY C: Post-event Reversal
# ============================================================
def strategy_c_post_reversal(btc_1d, eth_1d, ratio_df, event_date_str):
    """
    エントリー: イベント後2日目にratioがイベント当日値から逆方向に動いた場合
    エグジット: 5-10日後 または ratioがイベント当日値に戻った場合
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    # イベント当日のratio
    event_ratio_row = ratio_df[ratio_df['datetime'].dt.date == event_date]
    if event_ratio_row.empty:
        return []
    event_ratio = event_ratio_row.iloc[0]['ratio']

    # イベント翌日のratio (イベント当日からの方向)
    day1_date = event_date + timedelta(days=1)
    day1_row = ratio_df[ratio_df['datetime'].dt.date == day1_date]
    if day1_row.empty:
        return []
    day1_ratio = day1_row.iloc[0]['ratio']
    event_direction = 1 if day1_ratio > event_ratio else -1  # 当日の方向

    # 2日目に逆方向に動いたかチェック
    day2_date = event_date + timedelta(days=2)
    day2_row = ratio_df[ratio_df['datetime'].dt.date == day2_date]
    if day2_row.empty:
        return []
    day2_ratio = day2_row.iloc[0]['ratio']

    # 2日目がイベント値から逆方向に動いた → リバーサル期待
    reversal_direction = -event_direction  # 当日と逆
    if event_direction == 1 and day2_ratio >= event_ratio:
        return []  # 逆方向に動いていない
    if event_direction == -1 and day2_ratio <= event_ratio:
        return []

    entry_ratio = day2_ratio

    # エグジット: 5〜10日後にratioがイベント値に戻るかチェック
    for exit_day in range(3, 11):  # 3日後〜10日後
        exit_date = event_date + timedelta(days=exit_day)
        exit_row = ratio_df[ratio_df['datetime'].dt.date == exit_date]
        if exit_row.empty:
            continue
        exit_ratio = exit_row.iloc[0]['ratio']
        pnl = reversal_direction * ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
        hold_days = exit_day - 2

        # イベント当日値に戻ったらエグジット
        reverted = False
        if event_direction == 1 and exit_ratio >= event_ratio:
            reverted = True
        if event_direction == -1 and exit_ratio <= event_ratio:
            reverted = True

        results.append({
            'entry_date': str(day2_date),
            'exit_date': str(exit_date),
            'entry_ratio': round(entry_ratio, 6),
            'exit_ratio': round(exit_ratio, 6),
            'event_ratio': round(event_ratio, 6),
            'direction': 'LONG ratio (reversal)' if reversal_direction == 1 else 'SHORT ratio (reversal)',
            'pnl_pct': round(pnl, 3),
            'hold_days': hold_days,
            'reverted_to_event': reverted,
            'exit_reason': 'reversion' if reverted else f'day_{exit_day}'
        })
        if reverted:
            break  # 最初のリバーサルで確定

    # リバーサルが起きなかった場合の最終結果
    if results and not results[-1]['reverted_to_event']:
        pass  # 最後の結果をそのまま使用
    elif not results:
        # データがない場合は10日後まで強制エグジット
        for exit_day in [5, 7, 10]:
            exit_date = event_date + timedelta(days=exit_day)
            exit_row = ratio_df[ratio_df['datetime'].dt.date == exit_date]
            if not exit_row.empty:
                exit_ratio = exit_row.iloc[0]['ratio']
                pnl = reversal_direction * ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
                results.append({
                    'entry_date': str(day2_date),
                    'exit_date': str(exit_date),
                    'entry_ratio': round(entry_ratio, 6),
                    'exit_ratio': round(exit_ratio, 6),
                    'event_ratio': round(event_ratio, 6),
                    'direction': 'LONG ratio (reversal)' if reversal_direction == 1 else 'SHORT ratio (reversal)',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': exit_day - 2,
                    'reverted_to_event': False,
                    'exit_reason': f'forced_day_{exit_day}'
                })
                break

    return results


# ============================================================
# STRATEGY D: Post-event Trend Following
# ============================================================
def strategy_d_post_trend(btc_1d, eth_1d, ratio_df, event_date_str):
    """
    エントリー: イベント当日終値の方向 (ratio上昇=ロング, 下落=ショート)
    エグジット: 5日後 または SL -1.5%
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    # 前日終値
    prev_date = event_date - timedelta(days=1)
    prev_ratio_row = ratio_df[ratio_df['datetime'].dt.date == prev_date]
    event_ratio_row = ratio_df[ratio_df['datetime'].dt.date == event_date]
    if prev_ratio_row.empty or event_ratio_row.empty:
        return []

    prev_ratio = prev_ratio_row.iloc[0]['ratio']
    event_ratio = event_ratio_row.iloc[0]['ratio']
    event_change = ((event_ratio / prev_ratio) - 1) * 100

    # 当日の方向
    direction = 1 if event_change > 0 else -1
    entry_ratio = event_ratio

    # 5日後までチェック (SL -1.5%)
    sl_triggered = False
    for day in range(1, 6):
        check_date = event_date + timedelta(days=day)
        check_row = ratio_df[ratio_df['datetime'].dt.date == check_date]
        if check_row.empty:
            continue
        check_ratio = check_row.iloc[0]['ratio']
        current_pnl = direction * ((check_ratio / entry_ratio) - 1) * 100

        if current_pnl <= -1.5:
            # SL triggered
            pnl = current_pnl - SLIPPAGE_PCT
            results.append({
                'entry_date': str(event_date),
                'exit_date': str(check_date),
                'entry_ratio': round(entry_ratio, 6),
                'exit_ratio': round(check_ratio, 6),
                'direction': 'LONG ratio' if direction == 1 else 'SHORT ratio',
                'pnl_pct': round(pnl, 3),
                'hold_days': day,
                'exit_reason': 'stop_loss'
            })
            sl_triggered = True
            break

    if not sl_triggered:
        # 5日後にエグジット
        for exit_day in [5, 4, 3, 2, 1]:
            exit_date = event_date + timedelta(days=exit_day)
            exit_row = ratio_df[ratio_df['datetime'].dt.date == exit_date]
            if not exit_row.empty:
                exit_ratio = exit_row.iloc[0]['ratio']
                pnl = direction * ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
                results.append({
                    'entry_date': str(event_date),
                    'exit_date': str(exit_date),
                    'entry_ratio': round(entry_ratio, 6),
                    'exit_ratio': round(exit_ratio, 6),
                    'direction': 'LONG ratio' if direction == 1 else 'SHORT ratio',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': exit_day,
                    'exit_reason': 'time_exit'
                })
                break

    return results


# ============================================================
# STRATEGY E: Vol Breakout
# ============================================================
def strategy_e_vol_breakout(btc_1d, eth_1d, ratio_df, event_date_str):
    """
    エントリー: イベント当日にratioがイベント前5日のrangeを突破した方向
    エグジット: TP = rangeの1.5倍、SL = rangeの0.5倍、max hold 5日
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    # 前日終値
    prev_date = event_date - timedelta(days=1)
    prev_ratio_row = ratio_df[ratio_df['datetime'].dt.date == prev_date]
    if prev_ratio_row.empty:
        return []
    prev_ratio = prev_ratio_row.iloc[0]['ratio']

    # 前日ratio
    event_ratio_row = ratio_df[ratio_df['datetime'].dt.date == event_date]
    if event_ratio_row.empty:
        return []
    event_ratio = event_ratio_row.iloc[0]['ratio']

    # 前5日のrangeを計算
    range_ratios = []
    for d in range(1, 6):
        past_date = event_date - timedelta(days=d)
        past_row = ratio_df[ratio_df['datetime'].dt.date == past_date]
        if not past_row.empty:
            range_ratios.append(past_row.iloc[0]['ratio'])

    if len(range_ratios) < 3:
        return []

    range_high = max(range_ratios)
    range_low = min(range_ratios)
    range_size = range_high - range_low

    if range_size == 0:
        return []

    # ブレイクアウト判定
    if event_ratio > range_high:
        direction = 1  # LONG ratio
    elif event_ratio < range_low:
        direction = -1  # SHORT ratio
    else:
        return []  # ブレイクアウトなし

    entry_ratio = event_ratio
    tp_distance = range_size * 1.5
    sl_distance = range_size * 0.5

    # TP/SLチェック (最大5日)
    for day in range(1, 6):
        check_date = event_date + timedelta(days=day)
        check_row = ratio_df[ratio_df['datetime'].dt.date == check_date]
        if check_row.empty:
            continue
        check_ratio = check_row.iloc[0]['ratio']

        # ポジションのP&L (ratioの変動×方向)
        pnl_raw = direction * (check_ratio - entry_ratio)

        if pnl_raw >= tp_distance:
            pnl = (pnl_raw / entry_ratio) * 100 - SLIPPAGE_PCT
            results.append({
                'entry_date': str(event_date),
                'exit_date': str(check_date),
                'entry_ratio': round(entry_ratio, 6),
                'exit_ratio': round(check_ratio, 6),
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'pnl_pct': round(pnl, 3),
                'hold_days': day,
                'exit_reason': 'take_profit'
            })
            break
        elif pnl_raw <= -sl_distance:
            pnl = (pnl_raw / entry_ratio) * 100 - SLIPPAGE_PCT
            results.append({
                'entry_date': str(event_date),
                'exit_date': str(check_date),
                'entry_ratio': round(entry_ratio, 6),
                'exit_ratio': round(check_ratio, 6),
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'pnl_pct': round(pnl, 3),
                'hold_days': day,
                'exit_reason': 'stop_loss'
            })
            break
    else:
        # max hold到達
        for exit_day in [5, 4, 3, 2, 1]:
            exit_date = event_date + timedelta(days=exit_day)
            exit_row = ratio_df[ratio_df['datetime'].dt.date == exit_date]
            if not exit_row.empty:
                exit_ratio = exit_row.iloc[0]['ratio']
                pnl = direction * ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
                results.append({
                    'entry_date': str(event_date),
                    'exit_date': str(exit_date),
                    'entry_ratio': round(entry_ratio, 6),
                    'exit_ratio': round(exit_ratio, 6),
                    'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': exit_day,
                    'exit_reason': 'max_hold'
                })
                break

    return results


# ============================================================
# STRATEGY F: ETH-specific Weakness
# ============================================================
def strategy_f_eth_weakness(btc_1d, eth_1d, ratio_df, event_date_str):
    """
    エントリー: ETH close < ETH MA5 AND ETH volume > 20d平均 x 1.5
    エグジット: ETHがMA5に戻る、または -3% SL、max hold 10日
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    eth = compute_indicators(eth_1d)

    # イベント日前後でETHショートの機会を探す (-2日〜+3日)
    for offset in range(-2, 4):
        check_date = event_date + timedelta(days=offset)
        eth_row_df = eth[eth['datetime'].dt.date == check_date]
        if eth_row_df.empty:
            continue

        eth_row = eth_row_df.iloc[0]

        # ETH close < MA5
        if pd.isna(eth_row.get('ma5')) or eth_row['close'] >= eth_row['ma5']:
            continue

        # ETH volume > 20d平均 x 1.5
        if pd.isna(eth_row.get('vol_mean20')) or eth_row['volume'] <= eth_row['vol_mean20'] * 1.5:
            continue

        entry_price = eth_row['close']
        ma5_target = eth_row['ma5']

        # エグジット: MA5に戻る または -3% SL
        for exit_day in range(1, 11):
            exit_date = check_date + timedelta(days=exit_day)
            exit_row_df = eth[eth['datetime'].dt.date == exit_date]
            if exit_row_df.empty:
                continue

            exit_row = exit_row_df.iloc[0]
            exit_price = exit_row['close']
            pnl = ((entry_price - exit_price) / entry_price) * 100 - SLIPPAGE_PCT  # ショート

            # MA5に戻った
            if exit_price >= exit_row['ma5']:
                results.append({
                    'entry_date': str(check_date),
                    'exit_date': str(exit_date),
                    'entry_eth_price': round(entry_price, 2),
                    'exit_eth_price': round(exit_price, 2),
                    'direction': 'SHORT ETH',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': exit_day,
                    'exit_reason': 'ma5_reversion'
                })
                break

            # -3% SL
            if pnl <= -3.0:
                results.append({
                    'entry_date': str(check_date),
                    'exit_date': str(exit_date),
                    'entry_eth_price': round(entry_price, 2),
                    'exit_eth_price': round(exit_price, 2),
                    'direction': 'SHORT ETH',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': exit_day,
                    'exit_reason': 'stop_loss'
                })
                break
        else:
            # max hold 10日
            for fd in [10, 9, 8, 7, 6]:
                final_date = check_date + timedelta(days=fd)
                final_row_df = eth[eth['datetime'].dt.date == final_date]
                if not final_row_df.empty:
                    final_price = final_row_df.iloc[0]['close']
                    pnl = ((entry_price - final_price) / entry_price) * 100 - SLIPPAGE_PCT
                    results.append({
                        'entry_date': str(check_date),
                        'exit_date': str(final_date),
                        'entry_eth_price': round(entry_price, 2),
                        'exit_eth_price': round(final_price, 2),
                        'direction': 'SHORT ETH',
                        'pnl_pct': round(pnl, 3),
                        'hold_days': fd,
                        'exit_reason': 'max_hold'
                    })
                    break

        if results:
            break  # 最初のエントリーのみ記録

    return results


# ============================================================
# METRICS CALCULATION
# ============================================================
def calc_metrics(pnl_list, strategy_name):
    """戦略メトリクスを計算"""
    if not pnl_list:
        return {
            'strategy': strategy_name,
            'N': 0,
            'WR': 0,
            'EV': 0,
            'PF': 0,
            'Sharpe': 0,
            'p_value': 1.0,
            'avg_pnl': 0,
            'max_win': 0,
            'max_loss': 0,
            'verdict': 'NO TRADES'
        }

    pnls = np.array(pnl_list)
    n = len(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    wr = len(wins) / n * 100 if n > 0 else 0
    ev = np.mean(pnls) if n > 0 else 0
    gross_profit = np.sum(wins) if len(wins) > 0 else 0
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0.001
    pf = gross_profit / gross_loss
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 and n > 1 else 0

    # t検定 (p値)
    if n > 1:
        t_stat, p_value = stats.ttest_1samp(pnls, 0)
    else:
        t_stat = pnls[0] / 1.0 if n == 1 else 0
        p_value = 1.0

    # Verdict
    if n < 3:
        verdict = 'INSUFFICIENT DATA'
    elif p_value < 0.05 and ev > 0:
        verdict = 'SIGNIFICANT +EV'
    elif p_value < 0.10 and ev > 0:
        verdict = 'MARGINAL +EV'
    elif ev > 0:
        verdict = 'POSITIVE BUT NOT SIGNIFICANT'
    else:
        verdict = 'NEGATIVE EV'

    return {
        'strategy': strategy_name,
        'N': n,
        'WR': round(wr, 1),
        'EV': round(ev, 3),
        'PF': round(pf, 3),
        'Sharpe': round(sharpe, 2),
        'p_value': round(p_value, 4),
        'avg_pnl': round(ev, 3),
        'max_win': round(max(pnls), 3) if len(pnls) > 0 else 0,
        'max_loss': round(min(pnls), 3) if len(pnls) > 0 else 0,
        'verdict': verdict
    }


# ============================================================
# PORTFOLIO OPTIMIZATION
# ============================================================
def optimize_portfolio(all_strategy_results):
    """複数戦略を組み合わせた場合のポートフォリオEVを計算"""
    # 各戦略のEVを重みとして最適ポートフォリオを構築
    strategies = {}
    for strat_name, trades in all_strategy_results.items():
        if trades:
            pnls = [t['pnl_pct'] for t in trades]
            metrics = calc_metrics(pnls, strat_name)
            if metrics['EV'] > 0:
                strategies[strat_name] = {
                    'ev': metrics['EV'],
                    'wr': metrics['WR'],
                    'n': metrics['N'],
                    'std': np.std(pnls) if len(pnls) > 1 else 1.0,
                    'trades': trades
                }

    if not strategies:
        return {'portfolio_ev': 0, 'best_combo': 'NONE', 'details': {}}

    # 全ての+EV戦略を等ウェイトで組み合わせ
    total_ev = sum(s['ev'] for s in strategies.values())
    n_strats = len(strategies)
    equal_weight_ev = total_ev / n_strats if n_strats > 0 else 0

    # EV/リスク比でウェイト付け
    risk_adj_weights = {}
    total_risk_adj = 0
    for name, s in strategies.items():
        if s['std'] > 0:
            ra = s['ev'] / s['std']
        else:
            ra = s['ev']
        risk_adj_weights[name] = ra
        total_risk_adj += ra

    weighted_ev = 0
    details = {}
    for name, s in strategies.items():
        w = risk_adj_weights[name] / total_risk_adj if total_risk_adj > 0 else 0
        contrib = w * s['ev']
        weighted_ev += contrib
        details[name] = {
            'weight': round(w, 3),
            'ev_contribution': round(contrib, 3),
            'standalone_ev': round(s['ev'], 3)
        }

    # ベスト単体戦略
    best_single = max(strategies.items(), key=lambda x: x[1]['ev']) if strategies else ('NONE', {})

    return {
        'equal_weight_portfolio_ev': round(equal_weight_ev, 3),
        'risk_adjusted_portfolio_ev': round(weighted_ev, 3),
        'n_profitable_strategies': n_strats,
        'best_single_strategy': best_single[0],
        'best_single_ev': round(best_single[1]['ev'], 3) if best_single[1] else 0,
        'details': details,
        'all_strategies': {k: {'ev': round(v['ev'], 3), 'wr': round(v['wr'], 1), 'n': v['n']}
                          for k, v in strategies.items()}
    }


# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    print("=" * 80)
    print("規制イベント フェーズ別独立戦略 バックテスト")
    print("=" * 80)

    # データ読み込み
    print("\n[1] データ読み込み...")
    btc_1d, btc_4h, eth_1d, eth_4h = load_data()

    print(f"  BTC日足: {btc_1d['datetime'].min().date()} ~ {btc_1d['datetime'].max().date()} ({len(btc_1d)}件)")
    print(f"  BTC 4h足: {btc_4h['datetime'].min().date()} ~ {btc_4h['datetime'].max().date()} ({len(btc_4h)}件)")
    print(f"  ETH日足: {eth_1d['datetime'].min().date()} ~ {eth_1d['datetime'].max().date()} ({len(eth_1d)}件)")
    print(f"  ETH 4h足: {eth_4h['datetime'].min().date()} ~ {eth_4h['datetime'].max().date()} ({len(eth_4h)}件)")

    # Ratio計算
    ratio_df = compute_ratio(btc_1d, eth_1d)
    print(f"  BTC/ETH ratio: {len(ratio_df)}日分")

    # ============================================================
    # BACKTEST ALL STRATEGIES
    # ============================================================
    all_results = {
        'A': [],
        'B': [],
        'C': [],
        'D': [],
        'E': [],
        'F': []
    }

    event_trades = {e['name']: {} for e in EVENTS}

    print("\n[2] バックテスト実行...")
    print("-" * 80)

    for event in EVENTS:
        print(f"\n  ■ {event['name']} ({event['date']}) - {event['type']}")
        event_date = event['date']

        # Strategy A
        try:
            trades_a = strategy_a_pre_drift(btc_1d, eth_1d, ratio_df, event_date)
            if trades_a:
                best_a = max(trades_a, key=lambda x: abs(x['pnl_pct']))
                all_results['A'].append(best_a)
                event_trades[event['name']]['A'] = best_a
                print(f"    A: P&L={best_a['pnl_pct']:+.3f}% ({best_a['direction']})")
            else:
                event_trades[event['name']]['A'] = None
                print(f"    A: エントリー条件なし")
        except Exception as ex:
            event_trades[event['name']]['A'] = None
            print(f"    A: エラー - {ex}")

        # Strategy B
        try:
            trades_b = strategy_b_event_momentum(btc_4h, eth_4h, ratio_df, event_date)
            if trades_b:
                best_b = trades_b[0]  # 当日終値エグジットを優先
                all_results['B'].append(best_b)
                event_trades[event['name']]['B'] = best_b
                print(f"    B: P&L={best_b['pnl_pct']:+.3f}% (initial={best_b['initial_move_pct']:+.3f}%)")
            else:
                event_trades[event['name']]['B'] = None
                print(f"    B: エントリー条件なし")
        except Exception as ex:
            event_trades[event['name']]['B'] = None
            print(f"    B: エラー - {ex}")

        # Strategy C
        try:
            trades_c = strategy_c_post_reversal(btc_1d, eth_1d, ratio_df, event_date)
            if trades_c:
                best_c = trades_c[-1]  # 最終結果
                all_results['C'].append(best_c)
                event_trades[event['name']]['C'] = best_c
                print(f"    C: P&L={best_c['pnl_pct']:+.3f}% ({best_c['exit_reason']})")
            else:
                event_trades[event['name']]['C'] = None
                print(f"    C: エントリー条件なし")
        except Exception as ex:
            event_trades[event['name']]['C'] = None
            print(f"    C: エラー - {ex}")

        # Strategy D
        try:
            trades_d = strategy_d_post_trend(btc_1d, eth_1d, ratio_df, event_date)
            if trades_d:
                best_d = trades_d[0]
                all_results['D'].append(best_d)
                event_trades[event['name']]['D'] = best_d
                print(f"    D: P&L={best_d['pnl_pct']:+.3f}% ({best_d['exit_reason']})")
            else:
                event_trades[event['name']]['D'] = None
                print(f"    D: エントリー条件なし")
        except Exception as ex:
            event_trades[event['name']]['D'] = None
            print(f"    D: エラー - {ex}")

        # Strategy E
        try:
            trades_e = strategy_e_vol_breakout(btc_1d, eth_1d, ratio_df, event_date)
            if trades_e:
                best_e = trades_e[0]
                all_results['E'].append(best_e)
                event_trades[event['name']]['E'] = best_e
                print(f"    E: P&L={best_e['pnl_pct']:+.3f}% ({best_e['exit_reason']})")
            else:
                event_trades[event['name']]['E'] = None
                print(f"    E: エントリー条件なし")
        except Exception as ex:
            event_trades[event['name']]['E'] = None
            print(f"    E: エラー - {ex}")

        # Strategy F
        try:
            trades_f = strategy_f_eth_weakness(btc_1d, eth_1d, ratio_df, event_date)
            if trades_f:
                best_f = trades_f[0]
                all_results['F'].append(best_f)
                event_trades[event['name']]['F'] = best_f
                print(f"    F: P&L={best_f['pnl_pct']:+.3f}% ({best_f['exit_reason']})")
            else:
                event_trades[event['name']]['F'] = None
                print(f"    F: エントリー条件なし")
        except Exception as ex:
            event_trades[event['name']]['F'] = None
            print(f"    F: エラー - {ex}")

    # ============================================================
    # RESULTS SUMMARY
    # ============================================================
    print("\n" + "=" * 80)
    print("[3] 戦略別サマリー")
    print("=" * 80)

    strategy_names = {
        'A': 'Pre-event Drift (事前ポジショニング)',
        'B': 'Event Day Momentum (当日モメンタム)',
        'C': 'Post-event Reversal (事後リバーサル)',
        'D': 'Post-event Trend Following (事後トレンド)',
        'E': 'Vol Breakout (ボラティリティブレイクアウト)',
        'F': 'ETH-specific Weakness (ETH単体弱気狙い)'
    }

    all_metrics = {}
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        pnls = [t['pnl_pct'] for t in all_results[key]]
        metrics = calc_metrics(pnls, strategy_names[key])
        all_metrics[key] = metrics

        print(f"\n  戦略{key}: {strategy_names[key]}")
        print(f"    N={metrics['N']}  WR={metrics['WR']:.1f}%  EV={metrics['EV']:+.3f}%  "
              f"PF={metrics['PF']:.3f}  Sharpe={metrics['Sharpe']:.2f}  p={metrics['p_value']:.4f}")
        print(f"    最大勝ち={metrics['max_win']:+.3f}%  最大負け={metrics['max_loss']:+.3f}%")
        print(f"    判定: {metrics['verdict']}")

        # トレード明細
        if all_results[key]:
            print(f"    --- トレード明細 ---")
            for t in all_results[key]:
                entry_d = t.get('entry_date', t.get('entry_time', '?'))
                exit_d = t.get('exit_date', t.get('exit_time', '?'))
                print(f"      {entry_d} → {exit_d}  P&L={t['pnl_pct']:+.3f}%  {t.get('direction', '')}  "
                      f"理由={t.get('exit_reason', '-')}")

    # ============================================================
    # COMPARISON TABLE
    # ============================================================
    print("\n" + "=" * 80)
    print("[4] 戦略比較テーブル")
    print("=" * 80)
    print(f"  {'戦略':<45} {'N':>3} {'WR%':>6} {'EV%':>7} {'PF':>6} {'Sharpe':>7} {'p値':>7} {'判定'}")
    print("  " + "-" * 95)
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        m = all_metrics[key]
        short_name = strategy_names[key].split('(')[0].strip()
        print(f"  {short_name:<45} {m['N']:>3} {m['WR']:>6.1f} {m['EV']:>+7.3f} {m['PF']:>6.3f} "
              f"{m['Sharpe']:>7.2f} {m['p_value']:>7.4f} {m['verdict']}")

    # ============================================================
    # EVENT x STRATEGY MATRIX
    # ============================================================
    print("\n" + "=" * 80)
    print("[5] イベント×戦略 マトリクス (P&L%)")
    print("=" * 80)

    # テーブルヘッダー
    header = f"  {'イベント':<35}"
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        header += f" {key:>7}"
    print(header)
    print("  " + "-" * 77)

    for event in EVENTS:
        row = f"  {event['name'][:35]:<35}"
        for key in ['A', 'B', 'C', 'D', 'E', 'F']:
            trade = event_trades[event['name']].get(key)
            if trade:
                row += f" {trade['pnl_pct']:>+7.3f}"
            else:
                row += f" {'---':>7}"
        print(row)

    # ============================================================
    # PORTFOLIO OPTIMIZATION
    # ============================================================
    print("\n" + "=" * 80)
    print("[6] ポートフォリオ最適化")
    print("=" * 80)

    portfolio = optimize_portfolio(all_results)

    print(f"\n  +EV戦略数: {portfolio['n_profitable_strategies']}")
    print(f"  ベスト単体戦略: {portfolio['best_single_strategy']} (EV={portfolio['best_single_ev']:+.3f}%)")
    print(f"  等ウェイト・ポートフォリオEV: {portfolio['equal_weight_portfolio_ev']:+.3f}%")
    print(f"  リスク調整ウェイト・ポートフォリオEV: {portfolio['risk_adjusted_portfolio_ev']:+.3f}%")

    if portfolio.get('details'):
        print(f"\n  リスク調整ウェイト内訳:")
        for name, detail in portfolio['details'].items():
            print(f"    {name}: ウェイト={detail['weight']:.3f}  EV寄与={detail['ev_contribution']:+.3f}%  "
                  f"単体EV={detail['standalone_ev']:+.3f}%")

    # ============================================================
    # RECOMMENDED COMBINATION
    # ============================================================
    print("\n" + "=" * 80)
    print("[7] 推奨戦略コンビネーション")
    print("=" * 80)

    # +EV戦略を特定
    profitable = {k: v for k, v in all_metrics.items() if v['EV'] > 0 and v['N'] >= 2}
    if profitable:
        print(f"\n  +EV戦略 (N>=2):")
        for k, v in sorted(profitable.items(), key=lambda x: x[1]['EV'], reverse=True):
            print(f"    戦略{k}: EV={v['EV']:+.3f}%  WR={v['WR']:.1f}%  N={v['N']}  p={v['p_value']:.4f}")

        # コンビネーション案
        print(f"\n  推奨コンビネーション:")
        sig_strats = {k: v for k, v in profitable.items() if v['p_value'] < 0.15}
        if sig_strats:
            combo_ev = np.mean([v['EV'] for v in sig_strats.values()])
            print(f"    案1 [有意戦略のみ p<0.15]: {', '.join(sig_strats.keys())}")
            print(f"        期待EV = {combo_ev:+.3f}% / イベント")
        else:
            combo_ev = np.mean([v['EV'] for v in profitable.values()])
            print(f"    案1 [全+EV戦略]: {', '.join(profitable.keys())}")
            print(f"        期待EV = {combo_ev:+.3f}% / イベント")

        # イベントタイプ別
        print(f"\n  イベントタイプ別の最適戦略:")
        positive_events = [e for e in EVENTS if e['type'] == 'positive']
        negative_events = [e for e in EVENTS if e['type'] in ('negative', 'mixed')]

        for ev_type, ev_list in [('ポジティブ', positive_events), ('ネガティブ/混合', negative_events)]:
            print(f"\n    {ev_type}イベント ({len(ev_list)}件):")
            for key in ['A', 'B', 'C', 'D', 'E', 'F']:
                type_pnls = []
                for e in ev_list:
                    trade = event_trades[e['name']].get(key)
                    if trade:
                        type_pnls.append(trade['pnl_pct'])
                if type_pnls:
                    avg = np.mean(type_pnls)
                    wr = sum(1 for p in type_pnls if p > 0) / len(type_pnls) * 100
                    print(f"      戦略{key}: N={len(type_pnls)}  AVG P&L={avg:+.3f}%  WR={wr:.0f}%")
    else:
        print("  +EV戦略が見つかりませんでした")

    # ============================================================
    # SAVE RESULTS
    # ============================================================
    output = {
        'analysis_date': str(datetime.now()),
        'events_tested': len(EVENTS),
        'slippage_pct': SLIPPAGE_PCT,
        'strategy_metrics': all_metrics,
        'portfolio': {k: v for k, v in portfolio.items() if k != 'details'} if 'details' not in str(portfolio) else portfolio,
        'event_trades': {
            e['name']: {
                k: v for k, v in event_trades[e['name']].items() if v is not None
            } for e in EVENTS
        }
    }

    output_path = 'C:/Users/user/Desktop/cursor/trade/data/phase_strategy_results.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[8] 結果保存: {output_path}")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == '__main__':
    main()
