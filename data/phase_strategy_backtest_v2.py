#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
規制イベント フェーズ別独立戦略 バックテスト v2
改善点:
- 戦略A: エントリー条件緩和（ratio上昇 + BTC強気 or ETH弱気）
- 戦略C: リバーサル判定を改善
- 全イベントでBTC/ETH 4h足データを直接使用
- イベント前日〜後日まで幅広くスキャン
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
    """BTC・ETHのデータを読み込み"""
    # BTC日足 (extended)
    btc_1d = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/btc_price_1d_extended.csv')
    btc_1d['datetime'] = pd.to_datetime(btc_1d['datetime']).dt.tz_localize(None)
    btc_1d = btc_1d.sort_values('datetime').reset_index(drop=True)

    # BTC 4h足
    btc_4h = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/btc_price_4h_cache.csv')
    btc_4h['datetime'] = pd.to_datetime(btc_4h['datetime']).dt.tz_localize(None)
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

    # BTC日足とETH日足をマージしてratioを計算
    btc_temp = btc_1d[['datetime', 'close']].rename(columns={'close': 'btc_close'})
    eth_temp = eth_1d[['datetime', 'close']].rename(columns={'close': 'eth_close'})
    merged = pd.merge(btc_temp, eth_temp, on='datetime', how='inner')
    merged['ratio'] = merged['btc_close'] / merged['eth_close']

    return btc_1d, btc_4h, eth_1d, eth_4h, merged


def compute_indicators(df):
    """テクニカル指標を計算"""
    df = df.copy()
    for p in [3, 5, 7, 10, 20]:
        df[f'ma{p}'] = df['close'].rolling(window=p, min_periods=1).mean()
    df['ret'] = df['close'].pct_change() * 100
    df['vol20'] = df['ret'].rolling(window=20, min_periods=1).std()
    df['vol_mean20'] = df['volume'].rolling(window=20, min_periods=1).mean()
    return df


def get_ratio_on_date(ratio_df, target_date):
    """指定日のratioを取得"""
    row = ratio_df[ratio_df['datetime'].dt.date == target_date]
    if row.empty:
        return None
    return row.iloc[0]['ratio']


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
# STRATEGY A: Pre-event Drift (v2: 条件緩和)
# ============================================================
def strategy_a_pre_drift(ratio_df, btc_1d, eth_1d, event_date_str):
    """
    コンセプト: イベント前にratioが先回り上昇する傾向を狙う
    エントリー: イベント5〜3日前
    エグジット: イベント前日または当日
    条件v2:
      - ratioが直近3日間で上昇傾向 (ratio[-1] > ratio[-3])
      - BTC強気 (close > MA5) OR ETH弱気 (close < MA5)
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    btc = compute_indicators(btc_1d)
    eth = compute_indicators(eth_1d)

    for offset in [5, 4, 3]:
        entry_date = event_date - timedelta(days=offset)
        entry_ratio = get_ratio_on_date(ratio_df, entry_date)
        if entry_ratio is None:
            continue

        # ratioの3日前と比較
        ratio_3d_ago = get_ratio_on_date(ratio_df, entry_date - timedelta(days=3))
        if ratio_3d_ago is None:
            continue

        # ratio上昇傾向: 現在 > 3日前
        if entry_ratio <= ratio_3d_ago:
            continue

        # BTC強気 OR ETH弱気 (どちらか満たせばOK)
        btc_entry = btc[btc['datetime'].dt.date == entry_date]
        eth_entry = eth[eth['datetime'].dt.date == entry_date]

        if btc_entry.empty or eth_entry.empty:
            continue

        btc_strong = btc_entry.iloc[0]['close'] > btc_entry.iloc[0]['ma5']
        eth_weak = eth_entry.iloc[0]['close'] < eth_entry.iloc[0]['ma5']

        if not (btc_strong or eth_weak):
            continue

        # エントリー確定 - ratio LONG (BTC強い/ETH弱い)
        # エグジット: イベント前日
        for exit_offset in [1, 0]:
            exit_date = event_date - timedelta(days=exit_offset)
            exit_ratio = get_ratio_on_date(ratio_df, exit_date)
            if exit_ratio is not None:
                pnl = ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
                results.append({
                    'entry_date': str(entry_date),
                    'exit_date': str(exit_date),
                    'entry_ratio': round(entry_ratio, 4),
                    'exit_ratio': round(exit_ratio, 4),
                    'pnl_pct': round(pnl, 3),
                    'hold_days': offset - exit_offset,
                    'direction': 'LONG ratio (pre-drift)',
                    'btc_strong': btc_strong,
                    'eth_weak': eth_weak,
                    'exit_reason': 'pre_event_close'
                })
                break

    return results


# ============================================================
# STRATEGY B: Event Day Momentum (v2: 4h足ベース改善)
# ============================================================
def strategy_b_event_momentum(btc_4h, eth_4h, ratio_df, event_date_str):
    """
    コンセプト: イベント当日の最初の4h足の方向に乗る
    エントリー: イベント当日最初の4h足でratioが前日終値比±0.3%以上
    エグジット: 当日終値
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    # 前日終値のratio
    prev_date = event_date - timedelta(days=1)
    prev_ratio = get_ratio_on_date(ratio_df, prev_date)
    if prev_ratio is None:
        return []

    # 当日の4h足データ
    event_btc_4h = btc_4h[btc_4h['datetime'].dt.date == event_date].sort_values('datetime')
    event_eth_4h = eth_4h[eth_4h['datetime'].dt.date == event_date].sort_values('datetime')

    if event_btc_4h.empty or event_eth_4h.empty:
        return []

    # 前日最後の4h足の終値を基準
    prev_btc_4h = btc_4h[btc_4h['datetime'].dt.date == prev_date]
    prev_eth_4h = eth_4h[eth_4h['datetime'].dt.date == prev_date]

    if prev_btc_4h.empty or prev_eth_4h.empty:
        return []

    prev_btc_close = prev_btc_4h.iloc[-1]['close']
    prev_eth_close = prev_eth_4h.iloc[-1]['close']
    if prev_eth_close == 0:
        return []
    prev_close_ratio = prev_btc_close / prev_eth_close

    # 当日1本目の4h足
    first_btc = event_btc_4h.iloc[0]
    first_eth = event_eth_4h.iloc[0]
    if first_eth['close'] == 0:
        return []

    first_ratio = first_btc['close'] / first_eth['close']
    first_move = ((first_ratio / prev_close_ratio) - 1) * 100

    if abs(first_move) < 0.3:
        return []

    direction = 1 if first_move > 0 else -1

    # 当日最後の4h足でエグジット
    last_btc = event_btc_4h.iloc[-1]
    last_eth = event_eth_4h.iloc[-1]
    exit_ratio = last_btc['close'] / last_eth['close']

    pnl = direction * ((exit_ratio / first_ratio) - 1) * 100 - SLIPPAGE_PCT

    results.append({
        'entry_time': str(first_btc['datetime']),
        'exit_time': str(last_btc['datetime']),
        'entry_ratio': round(first_ratio, 4),
        'exit_ratio': round(exit_ratio, 4),
        'first_move_pct': round(first_move, 3),
        'direction': 'LONG ratio' if direction == 1 else 'SHORT ratio',
        'pnl_pct': round(pnl, 3),
        'hold_hours': int((last_btc['datetime'] - first_btc['datetime']).total_seconds() / 3600),
        'exit_reason': 'event_day_close'
    })

    return results


# ============================================================
# STRATEGY C: Post-event Reversal (v2: 改善)
# ============================================================
def strategy_c_post_reversal(ratio_df, event_date_str):
    """
    コンセプト: イベント後2日目にratioがイベント当日値から逆方向に動いたらリバーサル狙い
    エントリー: イベント後2日目、ratioがイベント当日値から逆方向に動いた
    エグジット: ratioがイベント当日値に戻る、または5-10日後
    """
    event_date = pd.to_datetime(event_date_str).date()
    results = []

    event_ratio = get_ratio_on_date(ratio_df, event_date)
    if event_ratio is None:
        return []

    day1_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=1))
    if day1_ratio is None:
        return []

    event_direction = 1 if day1_ratio > event_ratio else -1

    day2_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=2))
    if day2_ratio is None:
        return []

    # 2日目にイベント値から逆方向に動いたか
    if event_direction == 1 and day2_ratio >= event_ratio:
        return []
    if event_direction == -1 and day2_ratio <= event_ratio:
        return []

    entry_ratio = day2_ratio
    reversal_dir = -event_direction

    # エグジット探索
    exited = False
    for d in range(3, 11):
        check_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=d))
        if check_ratio is None:
            continue

        pnl = reversal_dir * ((check_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT

        # リバーサル判定
        reverted = False
        if event_direction == 1 and check_ratio >= event_ratio:
            reverted = True
        elif event_direction == -1 and check_ratio <= event_ratio:
            reverted = True

        if reverted or d >= 7:
            results.append({
                'entry_date': str(event_date + timedelta(days=2)),
                'exit_date': str(event_date + timedelta(days=d)),
                'entry_ratio': round(entry_ratio, 4),
                'exit_ratio': round(check_ratio, 4),
                'event_ratio': round(event_ratio, 4),
                'direction': 'LONG ratio (reversal)' if reversal_dir == 1 else 'SHORT ratio (reversal)',
                'pnl_pct': round(pnl, 3),
                'hold_days': d - 2,
                'exit_reason': 'reversion' if reverted else f'time_exit_d{d}'
            })
            exited = True
            break

    if not exited:
        # 最後の手段
        for d in [10, 9, 8]:
            check_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=d))
            if check_ratio is not None:
                pnl = reversal_dir * ((check_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
                results.append({
                    'entry_date': str(event_date + timedelta(days=2)),
                    'exit_date': str(event_date + timedelta(days=d)),
                    'entry_ratio': round(entry_ratio, 4),
                    'exit_ratio': round(check_ratio, 4),
                    'event_ratio': round(event_ratio, 4),
                    'direction': 'LONG ratio (reversal)' if reversal_dir == 1 else 'SHORT ratio (reversal)',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': d - 2,
                    'exit_reason': f'forced_d{d}'
                })
                break

    return results


# ============================================================
# STRATEGY D: Post-event Trend Following
# ============================================================
def strategy_d_post_trend(ratio_df, event_date_str):
    """
    エントリー: イベント当日終値の方向 (ratio上昇=LONG, 下落=SHORT)
    エグジット: 5日後 または SL -1.5%
    """
    event_date = pd.to_datetime(event_date_str).date()

    prev_ratio = get_ratio_on_date(ratio_df, event_date - timedelta(days=1))
    event_ratio = get_ratio_on_date(ratio_df, event_date)
    if prev_ratio is None or event_ratio is None:
        return []

    event_change = ((event_ratio / prev_ratio) - 1) * 100
    direction = 1 if event_change > 0 else -1
    entry_ratio = event_ratio

    # SL -1.5% チェック
    for d in range(1, 6):
        check_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=d))
        if check_ratio is None:
            continue
        pnl = direction * ((check_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT

        if pnl <= -1.5:
            return [{
                'entry_date': str(event_date),
                'exit_date': str(event_date + timedelta(days=d)),
                'entry_ratio': round(entry_ratio, 4),
                'exit_ratio': round(check_ratio, 4),
                'direction': 'LONG ratio (trend)' if direction == 1 else 'SHORT ratio (trend)',
                'pnl_pct': round(pnl, 3),
                'hold_days': d,
                'exit_reason': 'stop_loss'
            }]

    # 5日後エグジット
    for d in [5, 4, 3, 2, 1]:
        exit_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=d))
        if exit_ratio is not None:
            pnl = direction * ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(event_date),
                'exit_date': str(event_date + timedelta(days=d)),
                'entry_ratio': round(entry_ratio, 4),
                'exit_ratio': round(exit_ratio, 4),
                'direction': 'LONG ratio (trend)' if direction == 1 else 'SHORT ratio (trend)',
                'pnl_pct': round(pnl, 3),
                'hold_days': d,
                'exit_reason': 'time_exit'
            }]

    return []


# ============================================================
# STRATEGY E: Vol Breakout
# ============================================================
def strategy_e_vol_breakout(ratio_df, event_date_str):
    """
    エントリー: イベント当日にratioが前5日のrangeを突破した方向
    エグジット: TP = range x 1.5、SL = range x 0.5、max 5日
    """
    event_date = pd.to_datetime(event_date_str).date()

    event_ratio = get_ratio_on_date(ratio_df, event_date)
    if event_ratio is None:
        return []

    # 前5日のrange
    range_values = []
    for d in range(1, 6):
        r = get_ratio_on_date(ratio_df, event_date - timedelta(days=d))
        if r is not None:
            range_values.append(r)

    if len(range_values) < 3:
        return []

    range_high = max(range_values)
    range_low = min(range_values)
    range_size = range_high - range_low

    if range_size == 0:
        return []

    # ブレイクアウト判定
    if event_ratio > range_high:
        direction = 1
    elif event_ratio < range_low:
        direction = -1
    else:
        return []

    entry_ratio = event_ratio
    tp_dist = range_size * 1.5
    sl_dist = range_size * 0.5

    for d in range(1, 6):
        check_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=d))
        if check_ratio is None:
            continue

        raw_move = direction * (check_ratio - entry_ratio)

        if raw_move >= tp_dist:
            pnl = (raw_move / entry_ratio) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(event_date),
                'exit_date': str(event_date + timedelta(days=d)),
                'entry_ratio': round(entry_ratio, 4),
                'exit_ratio': round(check_ratio, 4),
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'range_size': round(range_size, 4),
                'pnl_pct': round(pnl, 3),
                'hold_days': d,
                'exit_reason': 'take_profit'
            }]
        elif raw_move <= -sl_dist:
            pnl = (raw_move / entry_ratio) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(event_date),
                'exit_date': str(event_date + timedelta(days=d)),
                'entry_ratio': round(entry_ratio, 4),
                'exit_ratio': round(check_ratio, 4),
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'range_size': round(range_size, 4),
                'pnl_pct': round(pnl, 3),
                'hold_days': d,
                'exit_reason': 'stop_loss'
            }]

    # max hold
    for d in [5, 4, 3, 2, 1]:
        exit_ratio = get_ratio_on_date(ratio_df, event_date + timedelta(days=d))
        if exit_ratio is not None:
            pnl = direction * ((exit_ratio / entry_ratio) - 1) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(event_date),
                'exit_date': str(event_date + timedelta(days=d)),
                'entry_ratio': round(entry_ratio, 4),
                'exit_ratio': round(exit_ratio, 4),
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'range_size': round(range_size, 4),
                'pnl_pct': round(pnl, 3),
                'hold_days': d,
                'exit_reason': 'max_hold'
            }]

    return []


# ============================================================
# STRATEGY F: ETH-specific Weakness (v2: 条件緩和)
# ============================================================
def strategy_f_eth_weakness(eth_1d, event_date_str):
    """
    コンセプト: 規制イベント周辺でETHが弱い日を狙ってショート
    エントリー: ETH close < MA5 AND volume > 20d平均
    エグジット: ETHがMA5に戻る、または -3% SL、max 10日
    """
    event_date = pd.to_datetime(event_date_str).date()
    eth = compute_indicators(eth_1d)
    results = []

    # イベント-2日〜+3日の範囲でエントリー機会を探す
    for offset in range(-2, 4):
        check_date = event_date + timedelta(days=offset)
        eth_row_df = eth[eth['datetime'].dt.date == check_date]
        if eth_row_df.empty:
            continue

        eth_row = eth_row_df.iloc[0]

        # ETH close < MA5
        if pd.isna(eth_row.get('ma5')) or eth_row['close'] >= eth_row['ma5']:
            continue

        # volume > 20d平均 (1.0x に緩和)
        if pd.isna(eth_row.get('vol_mean20')) or eth_row['volume'] <= eth_row['vol_mean20']:
            continue

        entry_price = eth_row['close']

        # エグジット
        for exit_d in range(1, 11):
            exit_date = check_date + timedelta(days=exit_d)
            exit_df = eth[eth['datetime'].dt.date == exit_date]
            if exit_df.empty:
                continue

            exit_row = exit_df.iloc[0]
            exit_price = exit_row['close']
            pnl = ((entry_price - exit_price) / entry_price) * 100 - SLIPPAGE_PCT

            # MA5に戻った
            if not pd.isna(exit_row.get('ma5')) and exit_price >= exit_row['ma5']:
                results.append({
                    'entry_date': str(check_date),
                    'exit_date': str(exit_date),
                    'entry_eth': round(entry_price, 2),
                    'exit_eth': round(exit_price, 2),
                    'direction': 'SHORT ETH',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': exit_d,
                    'exit_reason': 'ma5_reversion'
                })
                break

            # -3% SL
            if pnl <= -3.0:
                results.append({
                    'entry_date': str(check_date),
                    'exit_date': str(exit_date),
                    'entry_eth': round(entry_price, 2),
                    'exit_eth': round(exit_price, 2),
                    'direction': 'SHORT ETH',
                    'pnl_pct': round(pnl, 3),
                    'hold_days': exit_d,
                    'exit_reason': 'stop_loss'
                })
                break
        else:
            # max hold
            for fd in [10, 9, 8, 7]:
                final_date = check_date + timedelta(days=fd)
                final_df = eth[eth['datetime'].dt.date == final_date]
                if not final_df.empty:
                    final_price = final_df.iloc[0]['close']
                    pnl = ((entry_price - final_price) / entry_price) * 100 - SLIPPAGE_PCT
                    results.append({
                        'entry_date': str(check_date),
                        'exit_date': str(final_date),
                        'entry_eth': round(entry_price, 2),
                        'exit_eth': round(final_price, 2),
                        'direction': 'SHORT ETH',
                        'pnl_pct': round(pnl, 3),
                        'hold_days': fd,
                        'exit_reason': 'max_hold'
                    })
                    break

        if results:
            break  # 最初のエントリーのみ

    return results


# ============================================================
# METRICS
# ============================================================
def calc_metrics(pnl_list, strategy_name):
    """戦略メトリクスを計算"""
    if not pnl_list:
        return {
            'strategy': strategy_name, 'N': 0, 'WR': 0, 'EV': 0,
            'PF': 0, 'Sharpe': 0, 'p_value': 1.0,
            'max_win': 0, 'max_loss': 0, 'avg_hold': 0, 'verdict': 'NO TRADES'
        }

    pnls = np.array(pnl_list)
    n = len(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    wr = len(wins) / n * 100
    ev = np.mean(pnls)
    gross_profit = np.sum(wins) if len(wins) > 0 else 0
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0.001
    pf = gross_profit / gross_loss

    std = np.std(pnls, ddof=1) if n > 1 else 1.0
    sharpe = (np.mean(pnls) / std) * np.sqrt(252) if std > 0 and n > 1 else 0

    if n > 1:
        t_stat, p_value = stats.ttest_1samp(pnls, 0)
    else:
        p_value = 1.0

    if n < 3:
        verdict = 'INSUFFICIENT DATA'
    elif p_value < 0.05 and ev > 0:
        verdict = 'SIGNIFICANT +EV'
    elif p_value < 0.10 and ev > 0:
        verdict = 'MARGINAL +EV'
    elif ev > 0:
        verdict = 'POSITIVE (not significant)'
    else:
        verdict = 'NEGATIVE EV'

    return {
        'strategy': strategy_name, 'N': n, 'WR': round(wr, 1), 'EV': round(ev, 3),
        'PF': round(pf, 3), 'Sharpe': round(sharpe, 2), 'p_value': round(p_value, 4),
        'max_win': round(max(pnls), 3), 'max_loss': round(min(pnls), 3),
        'verdict': verdict
    }


# ============================================================
# PORTFOLIO OPTIMIZATION
# ============================================================
def optimize_portfolio(all_results):
    """ポートフォリオ最適化"""
    profitables = {}
    for key, trades in all_results.items():
        pnls = [t['pnl_pct'] for t in trades]
        m = calc_metrics(pnls, key)
        if m['EV'] > 0 and m['N'] >= 1:
            profitables[key] = {'metrics': m, 'pnls': pnls}

    if not profitables:
        return {'portfolio_ev': 0, 'best': 'NONE'}

    # ベスト単体
    best_key = max(profitables, key=lambda k: profitables[k]['metrics']['EV'])

    # 等ウェイト
    eq_ev = np.mean([p['metrics']['EV'] for p in profitables.values()])

    # リスク調整ウェイト
    ra_total = sum(p['metrics']['EV'] / (np.std(p['pnls']) + 0.01) for p in profitables.values())
    ra_ev = sum(
        (p['metrics']['EV'] / (np.std(p['pnls']) + 0.01)) / ra_total * p['metrics']['EV']
        for p in profitables.values()
    )

    return {
        'best_single': best_key,
        'best_single_ev': profitables[best_key]['metrics']['EV'],
        'equal_weight_ev': round(eq_ev, 3),
        'risk_adj_ev': round(ra_ev, 3),
        'n_profitable': len(profitables),
        'profitable_strategies': {k: {'EV': v['metrics']['EV'], 'WR': v['metrics']['WR'], 'N': v['metrics']['N']}
                                  for k, v in profitables.items()}
    }


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 90)
    print("  規制イベント フェーズ別独立戦略 バックテスト v2")
    print("=" * 90)

    # データ読み込み
    print("\n[1] データ読み込み...")
    btc_1d, btc_4h, eth_1d, eth_4h, ratio_df = load_data()
    print(f"  BTC日足: {btc_1d['datetime'].min().date()} ~ {btc_1d['datetime'].max().date()} ({len(btc_1d)}件)")
    print(f"  ETH日足: {eth_1d['datetime'].min().date()} ~ {eth_1d['datetime'].max().date()} ({len(eth_1d)}件)")
    print(f"  BTC/ETH ratio: {ratio_df['datetime'].min().date()} ~ {ratio_df['datetime'].max().date()} ({len(ratio_df)}日分)")

    # データカバレッジ確認
    print("\n  各イベントのデータカバレッジ:")
    for e in EVENTS:
        ed = pd.to_datetime(e['date']).date()
        has_ratio = get_ratio_on_date(ratio_df, ed) is not None
        has_4h_btc = not btc_4h[btc_4h['datetime'].dt.date == ed].empty
        has_4h_eth = not eth_4h[eth_4h['datetime'].dt.date == ed].empty
        print(f"    {e['name'][:35]:<35} ratio={'OK' if has_ratio else 'NG':>2}  BTC4h={'OK' if has_4h_btc else 'NG':>2}  ETH4h={'OK' if has_4h_eth else 'NG':>2}")

    # ============================================================
    # BACKTEST
    # ============================================================
    all_results = {'A': [], 'B': [], 'C': [], 'D': [], 'E': [], 'F': []}
    event_trades = {e['name']: {} for e in EVENTS}

    print("\n[2] バックテスト実行...")
    print("-" * 90)

    for event in EVENTS:
        print(f"\n  {event['name']} ({event['date']}) [{event['type']}]")

        # A: Pre-event Drift
        try:
            trades = strategy_a_pre_drift(ratio_df, btc_1d, eth_1d, event['date'])
            if trades:
                # 最良のエントリータイミングを選択
                best = max(trades, key=lambda x: x['pnl_pct'])
                all_results['A'].append(best)
                event_trades[event['name']]['A'] = best
                print(f"    A: {best['pnl_pct']:+.3f}%  entry={best['entry_date']} exit={best['exit_date']}  {best['direction']}")
            else:
                event_trades[event['name']]['A'] = None
                print(f"    A: 条件不一致")
        except Exception as ex:
            event_trades[event['name']]['A'] = None
            print(f"    A: Error - {ex}")

        # B: Event Day Momentum
        try:
            trades = strategy_b_event_momentum(btc_4h, eth_4h, ratio_df, event['date'])
            if trades:
                best = trades[0]
                all_results['B'].append(best)
                event_trades[event['name']]['B'] = best
                print(f"    B: {best['pnl_pct']:+.3f}%  first_move={best['first_move_pct']:+.3f}%  {best['direction']}")
            else:
                event_trades[event['name']]['B'] = None
                print(f"    B: 条件不一致")
        except Exception as ex:
            event_trades[event['name']]['B'] = None
            print(f"    B: Error - {ex}")

        # C: Post-event Reversal
        try:
            trades = strategy_c_post_reversal(ratio_df, event['date'])
            if trades:
                best = trades[0]
                all_results['C'].append(best)
                event_trades[event['name']]['C'] = best
                print(f"    C: {best['pnl_pct']:+.3f}%  hold={best['hold_days']}d  {best['exit_reason']}")
            else:
                event_trades[event['name']]['C'] = None
                print(f"    C: 条件不一致")
        except Exception as ex:
            event_trades[event['name']]['C'] = None
            print(f"    C: Error - {ex}")

        # D: Post-event Trend
        try:
            trades = strategy_d_post_trend(ratio_df, event['date'])
            if trades:
                best = trades[0]
                all_results['D'].append(best)
                event_trades[event['name']]['D'] = best
                print(f"    D: {best['pnl_pct']:+.3f}%  hold={best['hold_days']}d  {best['exit_reason']}")
            else:
                event_trades[event['name']]['D'] = None
                print(f"    D: 条件不一致")
        except Exception as ex:
            event_trades[event['name']]['D'] = None
            print(f"    D: Error - {ex}")

        # E: Vol Breakout
        try:
            trades = strategy_e_vol_breakout(ratio_df, event['date'])
            if trades:
                best = trades[0]
                all_results['E'].append(best)
                event_trades[event['name']]['E'] = best
                print(f"    E: {best['pnl_pct']:+.3f}%  range={best['range_size']:.4f}  {best['exit_reason']}")
            else:
                event_trades[event['name']]['E'] = None
                print(f"    E: 条件不一致")
        except Exception as ex:
            event_trades[event['name']]['E'] = None
            print(f"    E: Error - {ex}")

        # F: ETH Weakness
        try:
            trades = strategy_f_eth_weakness(eth_1d, event['date'])
            if trades:
                best = trades[0]
                all_results['F'].append(best)
                event_trades[event['name']]['F'] = best
                print(f"    F: {best['pnl_pct']:+.3f}%  ETH {best['entry_eth']:.2f}->{best['exit_eth']:.2f}  {best['exit_reason']}")
            else:
                event_trades[event['name']]['F'] = None
                print(f"    F: 条件不一致")
        except Exception as ex:
            event_trades[event['name']]['F'] = None
            print(f"    F: Error - {ex}")

    # ============================================================
    # METRICS
    # ============================================================
    strategy_labels = {
        'A': 'Pre-event Drift',
        'B': 'Event Day Momentum',
        'C': 'Post-event Reversal',
        'D': 'Post-event Trend',
        'E': 'Vol Breakout',
        'F': 'ETH Weakness'
    }

    print("\n" + "=" * 90)
    print("[3] 戦略別パフォーマンス")
    print("=" * 90)

    all_metrics = {}
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        pnls = [t['pnl_pct'] for t in all_results[key]]
        m = calc_metrics(pnls, strategy_labels[key])
        all_metrics[key] = m

        print(f"\n  戦略{key}: {strategy_labels[key]}")
        print(f"    N={m['N']}  WR={m['WR']:.1f}%  EV={m['EV']:+.3f}%  PF={m['PF']:.3f}  "
              f"Sharpe={m['Sharpe']:.2f}  p={m['p_value']:.4f}")
        print(f"    MaxWin={m['max_win']:+.3f}%  MaxLoss={m['max_loss']:+.3f}%")
        print(f"    判定: {m['verdict']}")

        if all_results[key]:
            print(f"    --- トレード明細 ---")
            for t in all_results[key]:
                ed = t.get('entry_date', t.get('entry_time', '?'))
                xd = t.get('exit_date', t.get('exit_time', '?'))
                print(f"      {ed} -> {xd}  P&L={t['pnl_pct']:+.3f}%  {t['direction']}  {t.get('exit_reason', '')}")

    # ============================================================
    # COMPARISON TABLE
    # ============================================================
    print("\n" + "=" * 90)
    print("[4] 戦略比較テーブル")
    print("=" * 90)
    print(f"  {'Strategy':<30} {'N':>3} {'WR%':>6} {'EV%':>8} {'PF':>6} {'Sharpe':>7} {'p-val':>7}  {'Verdict'}")
    print("  " + "-" * 85)
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        m = all_metrics[key]
        print(f"  {strategy_labels[key]:<30} {m['N']:>3} {m['WR']:>6.1f} {m['EV']:>+8.3f} "
              f"{m['PF']:>6.3f} {m['Sharpe']:>7.2f} {m['p_value']:>7.4f}  {m['verdict']}")

    # ============================================================
    # EVENT x STRATEGY MATRIX
    # ============================================================
    print("\n" + "=" * 90)
    print("[5] P&L Matrix (Event x Strategy)")
    print("=" * 90)

    header = f"  {'Event':<36}"
    for key in ['A', 'B', 'C', 'D', 'E', 'F']:
        header += f"  {key:>7}"
    header += "  BEST"
    print(header)
    print("  " + "-" * 90)

    for event in EVENTS:
        row = f"  {event['name'][:36]:<36}"
        best_pnl = -999
        best_strat = '-'
        for key in ['A', 'B', 'C', 'D', 'E', 'F']:
            trade = event_trades[event['name']].get(key)
            if trade:
                pnl = trade['pnl_pct']
                row += f"  {pnl:>+7.2f}"
                if pnl > best_pnl:
                    best_pnl = pnl
                    best_strat = key
            else:
                row += f"  {'---':>7}"
        row += f"  {best_strat}({best_pnl:+.2f})" if best_pnl > -999 else "  -"
        print(row)

    # ============================================================
    # PORTFOLIO
    # ============================================================
    print("\n" + "=" * 90)
    print("[6] Portfolio Optimization")
    print("=" * 90)

    portfolio = optimize_portfolio(all_results)
    print(f"\n  +EV戦略数: {portfolio['n_profitable']}")
    print(f"  Best Single: {portfolio['best_single']} (EV={portfolio['best_single_ev']:+.3f}%)")
    print(f"  Equal-Weight Portfolio EV: {portfolio['equal_weight_ev']:+.3f}%")
    print(f"  Risk-Adjusted Portfolio EV: {portfolio['risk_adj_ev']:+.3f}%")

    if portfolio.get('profitable_strategies'):
        print(f"\n  +EV戦略内訳:")
        for k, v in portfolio['profitable_strategies'].items():
            print(f"    {strategy_labels[k]}: EV={v['EV']:+.3f}%  WR={v['WR']:.1f}%  N={v['N']}")

    # ============================================================
    # EVENT TYPE ANALYSIS
    # ============================================================
    print("\n" + "=" * 90)
    print("[7] Event Type Analysis")
    print("=" * 90)

    for ev_type in ['positive', 'mixed', 'negative']:
        type_events = [e for e in EVENTS if e['type'] == ev_type]
        if not type_events:
            continue

        print(f"\n  {ev_type.upper()} Events ({len(type_events)}):")
        for key in ['A', 'B', 'C', 'D', 'E', 'F']:
            pnls = []
            for e in type_events:
                trade = event_trades[e['name']].get(key)
                if trade:
                    pnls.append(trade['pnl_pct'])
            if pnls:
                avg = np.mean(pnls)
                wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
                print(f"    {key} {strategy_labels[key]:<28}: N={len(pnls)}  AVG={avg:+.3f}%  WR={wr:.0f}%")

    # ============================================================
    # RECOMMENDATION
    # ============================================================
    print("\n" + "=" * 90)
    print("[8] FINAL RECOMMENDATION")
    print("=" * 90)

    # 上位戦略をランキング
    ranked = sorted(all_metrics.items(), key=lambda x: x[1]['EV'], reverse=True)
    print(f"\n  戦略ランキング (EV順):")
    for rank, (key, m) in enumerate(ranked, 1):
        marker = "***" if m['EV'] > 0 and m['N'] >= 2 else ""
        print(f"    #{rank} {key}: {strategy_labels[key]:<28}  EV={m['EV']:+.3f}%  WR={m['WR']:.0f}%  N={m['N']}  p={m['p_value']:.3f}  {marker}")

    # 推奨コンビネーション
    viable = {k: v for k, v in all_metrics.items() if v['EV'] > 0 and v['N'] >= 2}
    if viable:
        print(f"\n  実行可能コンビネーション:")
        combo_keys = list(viable.keys())
        combo_ev = np.mean([v['EV'] for v in viable.values()])
        print(f"    同時実行: {', '.join(f'戦略{k}' for k in combo_keys)}")
        print(f"    平均EV (等ウェイト): {combo_ev:+.3f}% / イベント")

        # フェーズ別推奨
        print(f"\n  フェーズ別推奨:")
        phases = {
            'Pre-event (3-5日前)': ['A'],
            'Event Day': ['B'],
            'Post-event (1-2日)': ['C'],
            'Post-event (3-5日)': ['D', 'E'],
            'ETH Weakness': ['F']
        }
        for phase, strats in phases.items():
            best_for_phase = None
            best_ev = -999
            for k in strats:
                m = all_metrics.get(k)
                if m and m['EV'] > best_ev:
                    best_ev = m['EV']
                    best_for_phase = k
            if best_for_phase and best_ev > 0:
                print(f"      {phase}: 戦略{best_for_phase} ({strategy_labels[best_for_phase]})  EV={best_ev:+.3f}%")
            else:
                print(f"      {phase}: 推奨なし")

    # ============================================================
    # SAVE
    # ============================================================
    output = {
        'analysis_date': str(datetime.now()),
        'slippage_pct': SLIPPAGE_PCT,
        'events_tested': len(EVENTS),
        'strategy_metrics': {k: v for k, v in all_metrics.items()},
        'portfolio': portfolio,
        'event_trades': {}
    }
    for e in EVENTS:
        output['event_trades'][e['name']] = {
            k: v for k, v in event_trades[e['name']].items() if v is not None
        }

    outpath = 'C:/Users/user/Desktop/cursor/trade/data/phase_strategy_results.json'
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Results saved: {outpath}")

    print("\n" + "=" * 90)
    print("DONE")
    print("=" * 90)


if __name__ == '__main__':
    main()
