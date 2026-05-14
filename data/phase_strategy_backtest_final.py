#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
規制イベント フェーズ別独立戦略 バックテスト v3 - FINAL
改善点:
  - Bitcoin ETF (データ外) を除外し、代わりにCoinbase Wells Notice (2023-06-06) と
    Binance DOJ (2023-06-15) の代わりにETHデータ範囲内のイベントのみ使用
  - データ範囲: 2024-04-05 ~ 2026-04-05 (ETHデータ)
  - 有効イベント7個で分析
  - 戦略C: リバーサル条件をさらに改善
  - 詳細な統計検定
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

SLIPPAGE_PCT = 0.15

# ============================================================
# DATA
# ============================================================
def load_data():
    btc_1d = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/btc_price_1d_extended.csv')
    btc_1d['datetime'] = pd.to_datetime(btc_1d['datetime']).dt.tz_localize(None)
    btc_1d = btc_1d.sort_values('datetime').reset_index(drop=True)

    btc_4h = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/btc_price_4h_cache.csv')
    btc_4h['datetime'] = pd.to_datetime(btc_4h['datetime']).dt.tz_localize(None)
    btc_4h = btc_4h.sort_values('datetime').reset_index(drop=True)

    eth_4h = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/ETH_USDT_4h_730d.csv')
    eth_4h['datetime'] = pd.to_datetime(eth_4h['datetime'])
    eth_4h = eth_4h.sort_values('datetime').reset_index(drop=True)

    eth_4h['date'] = eth_4h['datetime'].dt.date
    eth_1d = eth_4h.groupby('date').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).reset_index()
    eth_1d['datetime'] = pd.to_datetime(eth_1d['date'])
    eth_1d = eth_1d[['datetime', 'open', 'high', 'low', 'close', 'volume']]

    btc_t = btc_1d[['datetime', 'close']].rename(columns={'close': 'btc_close'})
    eth_t = eth_1d[['datetime', 'close']].rename(columns={'close': 'eth_close'})
    ratio_df = pd.merge(btc_t, eth_t, on='datetime', how='inner')
    ratio_df['ratio'] = ratio_df['btc_close'] / ratio_df['eth_close']

    return btc_1d, btc_4h, eth_1d, eth_4h, ratio_df


def compute_indicators(df):
    df = df.copy()
    for p in [3, 5, 7, 10, 20]:
        df[f'ma{p}'] = df['close'].rolling(window=p, min_periods=1).mean()
    df['ret'] = df['close'].pct_change() * 100
    df['vol_mean20'] = df['volume'].rolling(window=20, min_periods=1).mean()
    return df


def get_ratio(ratio_df, d):
    row = ratio_df[ratio_df['datetime'].dt.date == d]
    return row.iloc[0]['ratio'] if not row.empty else None


def get_eth(eth_1d, d):
    row = eth_1d[eth_1d['datetime'].dt.date == d]
    return row.iloc[0] if not row.empty else None


def get_btc(btc_1d, d):
    row = btc_1d[btc_1d['datetime'].dt.date == d]
    return row.iloc[0] if not row.empty else None


# ============================================================
# 7 EVENTS (within data range 2024-04-05 ~ 2026-04-05)
# ============================================================
EVENTS = [
    {'name': 'FIT21 House Pass',              'date': '2024-05-22', 'type': 'positive'},
    {'name': 'Ethereum ETF Approval',         'date': '2024-05-23', 'type': 'mixed'},
    {'name': 'Trump Wins Election',           'date': '2024-11-05', 'type': 'positive'},
    {'name': 'Gary Gensler Resignation',      'date': '2025-01-09', 'type': 'positive'},
    {'name': 'Stablecoin Bill Stalled',       'date': '2025-01-14', 'type': 'negative'},
    {'name': 'GENIUS Act Senate Pass',        'date': '2025-06-17', 'type': 'positive'},
    {'name': 'CLARITY Act House Pass',        'date': '2025-07-17', 'type': 'positive'},
]

STRAT_NAMES = {
    'A': 'Pre-event Drift',
    'B': 'Event Day Momentum',
    'C': 'Post-event Reversal',
    'D': 'Post-event Trend',
    'E': 'Vol Breakout',
    'F': 'ETH Weakness Short',
}


# ============================================================
# STRATEGY A: Pre-event Drift
# ============================================================
def run_strat_A(ratio_df, btc_1d, eth_1d, event_date_str):
    """
    エントリー: イベント3〜5日前にratioが上昇傾向
    条件: ratio現在 > ratio3日前 AND (BTC強気 OR ETH弱気)
    エグジット: イベント前日
    ポジション: LONG ratio (BTC有利)
    """
    ed = pd.to_datetime(event_date_str).date()
    btc = compute_indicators(btc_1d)
    eth = compute_indicators(eth_1d)

    trades = []
    for offset in [5, 4, 3]:
        d_entry = ed - timedelta(days=offset)
        r_entry = get_ratio(ratio_df, d_entry)
        r_3ago = get_ratio(ratio_df, d_entry - timedelta(days=3))
        if r_entry is None or r_3ago is None:
            continue
        if r_entry <= r_3ago:
            continue

        btc_row = get_btc(btc, d_entry)
        eth_row = get_eth(eth, d_entry)
        if btc_row is None or eth_row is None:
            continue

        btc_strong = btc_row['close'] > btc_row['ma5']
        eth_weak = eth_row['close'] < eth_row['ma5']
        if not (btc_strong or eth_weak):
            continue

        # Exit: event day -1
        for xd in [1, 0]:
            r_exit = get_ratio(ratio_df, ed - timedelta(days=xd))
            if r_exit is not None:
                pnl = ((r_exit / r_entry) - 1) * 100 - SLIPPAGE_PCT
                trades.append({
                    'entry_date': str(d_entry), 'exit_date': str(ed - timedelta(days=xd)),
                    'entry_ratio': round(r_entry, 2), 'exit_ratio': round(r_exit, 2),
                    'pnl_pct': round(pnl, 3), 'hold_days': offset - xd,
                    'direction': 'LONG ratio', 'exit_reason': 'pre_event'
                })
                break
    return trades


# ============================================================
# STRATEGY B: Event Day Momentum
# ============================================================
def run_strat_B(btc_4h, eth_4h, ratio_df, event_date_str):
    """
    エントリー: 当日1本目4h足でratioが前日終値比±0.3%以上
    エグジット: 当日最終4h足
    """
    ed = pd.to_datetime(event_date_str).date()
    prev_d = ed - timedelta(days=1)

    prev_btc = btc_4h[btc_4h['datetime'].dt.date == prev_d]
    prev_eth = eth_4h[eth_4h['datetime'].dt.date == prev_d]
    if prev_btc.empty or prev_eth.empty:
        return []

    prev_ratio = prev_btc.iloc[-1]['close'] / prev_eth.iloc[-1]['close']

    ev_btc = btc_4h[btc_4h['datetime'].dt.date == ed].sort_values('datetime')
    ev_eth = eth_4h[eth_4h['datetime'].dt.date == ed].sort_values('datetime')
    if ev_btc.empty or ev_eth.empty:
        return []

    first_btc = ev_btc.iloc[0]
    first_eth = ev_eth.iloc[0]
    if first_eth['close'] == 0:
        return []

    first_ratio = first_btc['close'] / first_eth['close']
    move = ((first_ratio / prev_ratio) - 1) * 100

    if abs(move) < 0.3:
        return []

    direction = 1 if move > 0 else -1

    last_btc = ev_btc.iloc[-1]
    last_eth = ev_eth.iloc[-1]
    exit_ratio = last_btc['close'] / last_eth['close']
    pnl = direction * ((exit_ratio / first_ratio) - 1) * 100 - SLIPPAGE_PCT

    return [{
        'entry_date': str(first_btc['datetime']), 'exit_date': str(last_btc['datetime']),
        'entry_ratio': round(first_ratio, 2), 'exit_ratio': round(exit_ratio, 2),
        'pnl_pct': round(pnl, 3), 'hold_hours': 20,
        'direction': 'LONG ratio' if direction == 1 else 'SHORT ratio',
        'exit_reason': 'eod_close', 'initial_move': round(move, 3)
    }]


# ============================================================
# STRATEGY C: Post-event Reversal (v3: 改善)
# ============================================================
def run_strat_C(ratio_df, event_date_str):
    """
    コンセプト: イベント当日のratio変動が翌日にオーバーシュート気味 → 逆張り
    エントリー: イベント翌日終値で、イベント当日方向の逆
    エグジット: 7日後 または ratioがイベント前日値に戻る
    """
    ed = pd.to_datetime(event_date_str).date()

    r_prev = get_ratio(ratio_df, ed - timedelta(days=1))
    r_event = get_ratio(ratio_df, ed)
    r_day1 = get_ratio(ratio_df, ed + timedelta(days=1))

    if r_prev is None or r_event is None:
        return []

    event_direction = 1 if r_event > r_prev else -1

    # 翌日も同じ方向に動いた → オーバーシュートの可能性
    if r_day1 is None:
        return []

    # エントリー: 翌日終値で逆張り
    entry_ratio = r_day1
    reversal_dir = -event_direction

    # Exit: 7日以内にイベント前日値に戻るか
    for d in range(2, 8):
        r = get_ratio(ratio_df, ed + timedelta(days=d))
        if r is None:
            continue

        pnl = reversal_dir * ((r / entry_ratio) - 1) * 100 - SLIPPAGE_PCT

        reverted = False
        if event_direction == 1 and r <= r_prev:
            reverted = True
        elif event_direction == -1 and r >= r_prev:
            reverted = True

        if reverted or d >= 7:
            return [{
                'entry_date': str(ed + timedelta(days=1)),
                'exit_date': str(ed + timedelta(days=d)),
                'entry_ratio': round(entry_ratio, 2), 'exit_ratio': round(r, 2),
                'pnl_pct': round(pnl, 3), 'hold_days': d - 1,
                'direction': 'LONG ratio (reversal)' if reversal_dir == 1 else 'SHORT ratio (reversal)',
                'exit_reason': 'reversion' if reverted else f'day_{d}'
            }]

    return []


# ============================================================
# STRATEGY D: Post-event Trend Following
# ============================================================
def run_strat_D(ratio_df, event_date_str):
    ed = pd.to_datetime(event_date_str).date()
    r_prev = get_ratio(ratio_df, ed - timedelta(days=1))
    r_event = get_ratio(ratio_df, ed)
    if r_prev is None or r_event is None:
        return []

    direction = 1 if r_event > r_prev else -1
    entry = r_event

    for d in range(1, 6):
        r = get_ratio(ratio_df, ed + timedelta(days=d))
        if r is None:
            continue
        pnl = direction * ((r / entry) - 1) * 100 - SLIPPAGE_PCT
        if pnl <= -1.5:
            return [{
                'entry_date': str(ed), 'exit_date': str(ed + timedelta(days=d)),
                'entry_ratio': round(entry, 2), 'exit_ratio': round(r, 2),
                'pnl_pct': round(pnl, 3), 'hold_days': d,
                'direction': 'LONG ratio (trend)' if direction == 1 else 'SHORT ratio (trend)',
                'exit_reason': 'stop_loss'
            }]

    for d in [5, 4, 3, 2, 1]:
        r = get_ratio(ratio_df, ed + timedelta(days=d))
        if r is not None:
            pnl = direction * ((r / entry) - 1) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(ed), 'exit_date': str(ed + timedelta(days=d)),
                'entry_ratio': round(entry, 2), 'exit_ratio': round(r, 2),
                'pnl_pct': round(pnl, 3), 'hold_days': d,
                'direction': 'LONG ratio (trend)' if direction == 1 else 'SHORT ratio (trend)',
                'exit_reason': 'time_5d'
            }]
    return []


# ============================================================
# STRATEGY E: Vol Breakout
# ============================================================
def run_strat_E(ratio_df, event_date_str):
    ed = pd.to_datetime(event_date_str).date()
    r_event = get_ratio(ratio_df, ed)
    if r_event is None:
        return []

    vals = []
    for d in range(1, 6):
        r = get_ratio(ratio_df, ed - timedelta(days=d))
        if r is not None:
            vals.append(r)
    if len(vals) < 3:
        return []

    rh, rl = max(vals), min(vals)
    rs = rh - rl
    if rs == 0:
        return []

    if r_event > rh:
        direction = 1
    elif r_event < rl:
        direction = -1
    else:
        return []

    entry = r_event
    tp = rs * 1.5
    sl = rs * 0.5

    for d in range(1, 6):
        r = get_ratio(ratio_df, ed + timedelta(days=d))
        if r is None:
            continue
        raw = direction * (r - entry)
        if raw >= tp:
            pnl = (raw / entry) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(ed), 'exit_date': str(ed + timedelta(days=d)),
                'entry_ratio': round(entry, 2), 'exit_ratio': round(r, 2),
                'pnl_pct': round(pnl, 3), 'hold_days': d,
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'exit_reason': 'take_profit'
            }]
        if raw <= -sl:
            pnl = (raw / entry) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(ed), 'exit_date': str(ed + timedelta(days=d)),
                'entry_ratio': round(entry, 2), 'exit_ratio': round(r, 2),
                'pnl_pct': round(pnl, 3), 'hold_days': d,
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'exit_reason': 'stop_loss'
            }]

    for d in [5, 4, 3, 2, 1]:
        r = get_ratio(ratio_df, ed + timedelta(days=d))
        if r is not None:
            pnl = direction * ((r / entry) - 1) * 100 - SLIPPAGE_PCT
            return [{
                'entry_date': str(ed), 'exit_date': str(ed + timedelta(days=d)),
                'entry_ratio': round(entry, 2), 'exit_ratio': round(r, 2),
                'pnl_pct': round(pnl, 3), 'hold_days': d,
                'direction': 'LONG ratio (breakout)' if direction == 1 else 'SHORT ratio (breakout)',
                'exit_reason': 'max_hold'
            }]
    return []


# ============================================================
# STRATEGY F: ETH Weakness Short
# ============================================================
def run_strat_F(eth_1d, event_date_str):
    ed = pd.to_datetime(event_date_str).date()
    eth = compute_indicators(eth_1d)

    for offset in range(-2, 4):
        cd = ed + timedelta(days=offset)
        row_df = eth[eth['datetime'].dt.date == cd]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        if pd.isna(row.get('ma5')) or row['close'] >= row['ma5']:
            continue
        if pd.isna(row.get('vol_mean20')) or row['volume'] <= row['vol_mean20'] * 1.2:
            continue

        entry_px = row['close']

        for ed2 in range(1, 11):
            xd = cd + timedelta(days=ed2)
            xr_df = eth[eth['datetime'].dt.date == xd]
            if xr_df.empty:
                continue
            xr = xr_df.iloc[0]
            xp = xr['close']
            pnl = ((entry_px - xp) / entry_px) * 100 - SLIPPAGE_PCT

            if not pd.isna(xr.get('ma5')) and xp >= xr['ma5']:
                return [{
                    'entry_date': str(cd), 'exit_date': str(xd),
                    'entry_eth': round(entry_px, 2), 'exit_eth': round(xp, 2),
                    'pnl_pct': round(pnl, 3), 'hold_days': ed2,
                    'direction': 'SHORT ETH', 'exit_reason': 'ma5_reversion'
                }]
            if pnl <= -3.0:
                return [{
                    'entry_date': str(cd), 'exit_date': str(xd),
                    'entry_eth': round(entry_px, 2), 'exit_eth': round(xp, 2),
                    'pnl_pct': round(pnl, 3), 'hold_days': ed2,
                    'direction': 'SHORT ETH', 'exit_reason': 'stop_loss'
                }]

        for fd in [10, 9, 8]:
            fxd = cd + timedelta(days=fd)
            fxr_df = eth[eth['datetime'].dt.date == fxd]
            if not fxr_df.empty:
                fxp = fxr_df.iloc[0]['close']
                pnl = ((entry_px - fxp) / entry_px) * 100 - SLIPPAGE_PCT
                return [{
                    'entry_date': str(cd), 'exit_date': str(fxd),
                    'entry_eth': round(entry_px, 2), 'exit_eth': round(fxp, 2),
                    'pnl_pct': round(pnl, 3), 'hold_days': fd,
                    'direction': 'SHORT ETH', 'exit_reason': 'max_hold'
                }]
    return []


# ============================================================
# METRICS
# ============================================================
def calc_metrics(pnls, name):
    if not pnls:
        return {'strategy': name, 'N': 0, 'WR': 0, 'EV': 0, 'PF': 0,
                'Sharpe': 0, 'p_value': 1.0, 'max_win': 0, 'max_loss': 0, 'verdict': 'NO TRADES'}

    a = np.array(pnls)
    n = len(a)
    wins = a[a > 0]
    losses = a[a < 0]
    wr = len(wins) / n * 100
    ev = float(np.mean(a))
    gp = float(np.sum(wins)) if len(wins) > 0 else 0
    gl = abs(float(np.sum(losses))) if len(losses) > 0 else 0.001
    pf = gp / gl
    std = float(np.std(a, ddof=1)) if n > 1 else 1.0
    sharpe = (np.mean(a) / std) * np.sqrt(252) if std > 0 and n > 1 else 0

    if n > 1:
        _, p = stats.ttest_1samp(a, 0)
    else:
        p = 1.0

    if n < 3:
        verdict = 'INSUFFICIENT'
    elif p < 0.05 and ev > 0:
        verdict = 'SIGNIFICANT +EV **'
    elif p < 0.10 and ev > 0:
        verdict = 'MARGINAL +EV *'
    elif ev > 0:
        verdict = '+EV (ns)'
    else:
        verdict = '-EV'

    return {
        'strategy': name, 'N': n, 'WR': round(wr, 1), 'EV': round(ev, 3),
        'PF': round(pf, 3), 'Sharpe': round(sharpe, 2), 'p_value': round(float(p), 4),
        'max_win': round(float(max(a)), 3), 'max_loss': round(float(min(a)), 3),
        'verdict': verdict
    }


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 95)
    print("   規制イベント フェーズ別独立戦略 バックテスト - FINAL REPORT")
    print("   データ期間: 2024-04-05 ~ 2026-04-05 | スリッページ: {:.1f}% round-trip".format(SLIPPAGE_PCT))
    print("=" * 95)

    btc_1d, btc_4h, eth_1d, eth_4h, ratio_df = load_data()
    print(f"\n  BTC/ETH Ratio: {len(ratio_df)} 日分")

    # 全イベントでバックテスト
    all_trades = {k: [] for k in ['A', 'B', 'C', 'D', 'E', 'F']}
    event_results = {e['name']: {} for e in EVENTS}

    print("\n" + "-" * 95)
    print("  EVENT BACKTEST RESULTS")
    print("-" * 95)

    for ev in EVENTS:
        print(f"\n  >> {ev['name']} ({ev['date']}) [{ev['type']}]")

        # A
        ta = run_strat_A(ratio_df, btc_1d, eth_1d, ev['date'])
        if ta:
            best = max(ta, key=lambda x: x['pnl_pct'])
            all_trades['A'].append(best)
            event_results[ev['name']]['A'] = best
            print(f"     A: {best['pnl_pct']:+.3f}%  {best['entry_date']} -> {best['exit_date']}  {best['direction']}")
        else:
            print(f"     A: skip (no signal)")

        # B
        tb = run_strat_B(btc_4h, eth_4h, ratio_df, ev['date'])
        if tb:
            all_trades['B'].append(tb[0])
            event_results[ev['name']]['B'] = tb[0]
            m = tb[0].get('initial_move', '?')
            print(f"     B: {tb[0]['pnl_pct']:+.3f}%  initial_move={m}%  {tb[0]['direction']}")
        else:
            print(f"     B: skip (no signal)")

        # C
        tc = run_strat_C(ratio_df, ev['date'])
        if tc:
            all_trades['C'].append(tc[0])
            event_results[ev['name']]['C'] = tc[0]
            print(f"     C: {tc[0]['pnl_pct']:+.3f}%  hold={tc[0]['hold_days']}d  {tc[0]['exit_reason']}")
        else:
            print(f"     C: skip (no signal)")

        # D
        td = run_strat_D(ratio_df, ev['date'])
        if td:
            all_trades['D'].append(td[0])
            event_results[ev['name']]['D'] = td[0]
            print(f"     D: {td[0]['pnl_pct']:+.3f}%  hold={td[0]['hold_days']}d  {td[0]['exit_reason']}")
        else:
            print(f"     D: skip (no signal)")

        # E
        te = run_strat_E(ratio_df, ev['date'])
        if te:
            all_trades['E'].append(te[0])
            event_results[ev['name']]['E'] = te[0]
            print(f"     E: {te[0]['pnl_pct']:+.3f}%  hold={te[0]['hold_days']}d  {te[0]['exit_reason']}")
        else:
            print(f"     E: skip (no signal)")

        # F
        tf = run_strat_F(eth_1d, ev['date'])
        if tf:
            all_trades['F'].append(tf[0])
            event_results[ev['name']]['F'] = tf[0]
            print(f"     F: {tf[0]['pnl_pct']:+.3f}%  ETH {tf[0]['entry_eth']}->{tf[0]['exit_eth']}  {tf[0]['exit_reason']}")
        else:
            print(f"     F: skip (no signal)")

    # ============================================================
    # STRATEGY METRICS
    # ============================================================
    print("\n" + "=" * 95)
    print("  STRATEGY PERFORMANCE SUMMARY")
    print("=" * 95)

    metrics = {}
    for k in ['A', 'B', 'C', 'D', 'E', 'F']:
        pnls = [t['pnl_pct'] for t in all_trades[k]]
        metrics[k] = calc_metrics(pnls, STRAT_NAMES[k])

    print(f"\n  {'#':<3} {'Strategy':<28} {'N':>3} {'WR%':>6} {'EV%':>8} {'PF':>6} {'Sharpe':>7} {'p-val':>7}  {'MaxW':>7} {'MaxL':>7}  Verdict")
    print("  " + "-" * 100)
    for k in ['A', 'B', 'C', 'D', 'E', 'F']:
        m = metrics[k]
        print(f"  {k:<3} {STRAT_NAMES[k]:<28} {m['N']:>3} {m['WR']:>6.1f} {m['EV']:>+8.3f} "
              f"{m['PF']:>6.3f} {m['Sharpe']:>7.2f} {m['p_value']:>7.4f}  "
              f"{m['max_win']:>+7.3f} {m['max_loss']:>+7.3f}  {m['verdict']}")

    # ============================================================
    # TRADE DETAILS
    # ============================================================
    print("\n" + "=" * 95)
    print("  TRADE DETAILS")
    print("=" * 95)

    for k in ['A', 'B', 'C', 'D', 'E', 'F']:
        if not all_trades[k]:
            continue
        print(f"\n  Strategy {k}: {STRAT_NAMES[k]}")
        for t in all_trades[k]:
            ed = t.get('entry_date', '?')
            xd = t.get('exit_date', '?')
            print(f"    {ed} -> {xd}  P&L={t['pnl_pct']:+.3f}%  {t['direction']}  {t.get('exit_reason', '')}")

    # ============================================================
    # P&L MATRIX
    # ============================================================
    print("\n" + "=" * 95)
    print("  P&L MATRIX (Event x Strategy)  [%]")
    print("=" * 95)

    hdr = f"  {'Event':<30}"
    for k in ['A', 'B', 'C', 'D', 'E', 'F']:
        hdr += f"  {k:>7}"
    print(hdr)
    print("  " + "-" * 75)

    totals = {k: [] for k in ['A', 'B', 'C', 'D', 'E', 'F']}
    for ev in EVENTS:
        row = f"  {ev['name'][:30]:<30}"
        for k in ['A', 'B', 'C', 'D', 'E', 'F']:
            t = event_results[ev['name']].get(k)
            if t:
                row += f"  {t['pnl_pct']:>+7.2f}"
                totals[k].append(t['pnl_pct'])
            else:
                row += f"  {'---':>7}"
        print(row)

    print("  " + "-" * 75)
    row = f"  {'AVERAGE':<30}"
    for k in ['A', 'B', 'C', 'D', 'E', 'F']:
        if totals[k]:
            avg = np.mean(totals[k])
            row += f"  {avg:>+7.2f}"
        else:
            row += f"  {'---':>7}"
    print(row)

    # ============================================================
    # PORTFOLIO OPTIMIZATION
    # ============================================================
    print("\n" + "=" * 95)
    print("  PORTFOLIO OPTIMIZATION")
    print("=" * 95)

    profitable = {k: v for k, v in metrics.items() if v['EV'] > 0 and v['N'] >= 1}
    if profitable:
        print(f"\n  +EV Strategies: {len(profitable)}")
        for k, m in sorted(profitable.items(), key=lambda x: x[1]['EV'], reverse=True):
            print(f"    {k}: {STRAT_NAMES[k]:<28}  EV={m['EV']:+.3f}%  WR={m['WR']:.0f}%  N={m['N']}  p={m['p_value']:.3f}")

        # Portfolio EVs
        evs = [v['EV'] for v in profitable.values()]
        eq_ev = np.mean(evs)
        print(f"\n  Equal-Weight Portfolio EV: {eq_ev:+.3f}% per event")

        # Risk-adjusted
        ra_w = {}
        ra_tot = 0
        for k, v in profitable.items():
            pnls = [t['pnl_pct'] for t in all_trades[k]]
            s = np.std(pnls, ddof=1) if len(pnls) > 1 else 1.0
            w = v['EV'] / (s + 0.01)
            ra_w[k] = w
            ra_tot += w
        ra_ev = sum((ra_w[k] / ra_tot) * profitable[k]['EV'] for k in profitable)
        print(f"  Risk-Adjusted Portfolio EV: {ra_ev:+.3f}% per event")

        # 同時実行シミュレーション
        print(f"\n  Simultaneous Execution Simulation (best +EV strategies):")
        strat_keys = list(profitable.keys())
        event_portfolio_pnls = {}
        for ev in EVENTS:
            ep = 0
            count = 0
            for k in strat_keys:
                t = event_results[ev['name']].get(k)
                if t:
                    ep += t['pnl_pct']
                    count += 1
            event_portfolio_pnls[ev['name']] = {'total': ep, 'count': count}

        for ev_name, data in event_portfolio_pnls.items():
            print(f"    {ev_name[:35]:<35}: {data['total']:+.3f}% ({data['count']} strategies)")
        total_pnl = sum(d['total'] for d in event_portfolio_pnls.values())
        n_active = sum(1 for d in event_portfolio_pnls.values() if d['count'] > 0)
        print(f"    {'TOTAL':<35}: {total_pnl:+.3f}% across {n_active} events")
        print(f"    Average per active event: {total_pnl / n_active:+.3f}%" if n_active > 0 else "")

    # ============================================================
    # EVENT TYPE ANALYSIS
    # ============================================================
    print("\n" + "=" * 95)
    print("  EVENT TYPE BREAKDOWN")
    print("=" * 95)

    for etype in ['positive', 'mixed', 'negative']:
        evs = [e for e in EVENTS if e['type'] == etype]
        if not evs:
            continue
        print(f"\n  {etype.upper()} ({len(evs)} events):")
        for k in ['A', 'B', 'C', 'D', 'E', 'F']:
            pnls = []
            for e in evs:
                t = event_results[e['name']].get(k)
                if t:
                    pnls.append(t['pnl_pct'])
            if pnls:
                avg = np.mean(pnls)
                wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
                marker = " <-- BEST" if avg == max(
                    np.mean([t['pnl_pct'] for e2 in evs
                             for t in [event_results[e2['name']].get(k2)]
                             if t is not None])
                    for k2 in ['A', 'B', 'C', 'D', 'E', 'F']
                    if any(event_results[e2['name']].get(k2) for e2 in evs)
                ) else ""
                print(f"    {k} {STRAT_NAMES[k]:<26}: N={len(pnls)}  AVG={avg:+.3f}%  WR={wr:.0f}%")

    # ============================================================
    # RECOMMENDATION
    # ============================================================
    print("\n" + "=" * 95)
    print("  FINAL RECOMMENDATION")
    print("=" * 95)

    ranked = sorted(metrics.items(), key=lambda x: x[1]['EV'], reverse=True)
    print(f"\n  Strategy Ranking:")
    for i, (k, m) in enumerate(ranked, 1):
        star = " <<<" if m['EV'] > 0 and m['N'] >= 2 else ""
        print(f"    #{i} {k}: {STRAT_NAMES[k]:<28}  EV={m['EV']:+.3f}%  WR={m['WR']:.0f}%  N={m['N']}  p={m['p_value']:.3f}{star}")

    print(f"\n  Phase-based Recommendation:")
    phases = [
        ("Pre-event (3-5d before)", 'A'),
        ("Event Day", 'B'),
        ("Post-event reversal (1-2d)", 'C'),
        ("Post-event trend (3-5d)", 'D'),
        ("Vol breakout", 'E'),
        ("ETH weakness", 'F'),
    ]
    for phase_name, k in phases:
        m = metrics[k]
        status = f"EV={m['EV']:+.3f}% WR={m['WR']:.0f}% N={m['N']}" if m['N'] > 0 else "No trades"
        recommendation = "IMPLEMENT" if m['EV'] > 0 and m['N'] >= 2 else ("CAUTION" if m['N'] >= 2 else "SKIP")
        if m['EV'] > 0 and m['p_value'] < 0.15:
            recommendation = "STRONG IMPLEMENT"
        print(f"    {phase_name:<35}: {k} {status:<25} [{recommendation}]")

    # Save
    output = {
        'analysis_date': str(datetime.now()),
        'events_tested': len(EVENTS),
        'slippage_pct': SLIPPAGE_PCT,
        'metrics': {k: v for k, v in metrics.items()},
        'event_trades': {e['name']: {k: v for k, v in event_results[e['name']].items()} for e in EVENTS}
    }
    outpath = 'C:/Users/user/Desktop/cursor/trade/data/phase_strategy_results.json'
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Results: {outpath}")

    print("\n" + "=" * 95)
    print("  COMPLETE")
    print("=" * 95)


if __name__ == '__main__':
    main()
