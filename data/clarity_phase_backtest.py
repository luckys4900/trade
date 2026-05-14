#!/usr/bin/env python3
"""
Clarity Act Phase Strategy - Backtest Verification
Runs all 3 phases against historical events to verify EV claims.
Uses local CSV data directly (no API calls needed).
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from scipy import stats

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

EVENTS = [
    ('FIT21 House Pass', '2024-05-22'),
    ('ETH ETF Approval', '2024-05-23'),
    ('SAB121 Override', '2024-05-09'),
    ('Trump Wins', '2024-11-06'),
    ('Gensler Resigns', '2024-11-21'),
    ('Gensler Steps Down', '2025-01-20'),
    ('Trump Crypto EO', '2025-03-07'),
    ('SAB121 Repealed', '2025-04-01'),
]

COST = 0.17  # round-trip %


def load_local_data():
    """Load BTC daily + ETH 4h -> aggregate to daily, compute ratio"""
    # BTC daily
    btc_path = os.path.join(DATA_DIR, 'btc_price_1d_cache.csv')
    btc = pd.read_csv(btc_path)
    btc['datetime'] = pd.to_datetime(btc['datetime'])
    btc = btc.sort_values('datetime').reset_index(drop=True)
    btc['date'] = btc['datetime'].dt.date

    # ETH 4h -> aggregate to daily
    eth_path = os.path.join(DATA_DIR, 'ETH_USDT_4h_730d.csv')
    eth_raw = pd.read_csv(eth_path)
    eth_raw['datetime'] = pd.to_datetime(eth_raw['datetime'])
    eth_raw['date'] = eth_raw['datetime'].dt.date
    eth = eth_raw.groupby('date').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum'
    }).reset_index()
    eth['date'] = pd.to_datetime(eth['date']).dt.date

    # Merge on date
    merged = btc.merge(eth, on='date', suffixes=('_btc', '_eth'))
    merged = merged.sort_values('date').reset_index(drop=True)

    # Calculate ratio
    merged['ratio'] = merged['close_btc'] / merged['close_eth']

    # Ratio MAs
    for w in [5, 10, 14, 20]:
        merged[f'ratio_ma{w}'] = merged['ratio'].rolling(w, min_periods=1).mean()

    # Ratio RSI
    delta = merged['ratio'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14, min_periods=7).mean()
    avg_loss = loss.rolling(14, min_periods=7).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    merged['ratio_rsi'] = 100 - (100 / (1 + rs))

    # Percentile
    merged['ratio_pct'] = merged['ratio'].rolling(252, min_periods=60).rank(pct=True)

    # ETH weakness
    merged['btc_ret5'] = merged['close_btc'].pct_change(5)
    merged['eth_ret5'] = merged['close_eth'].pct_change(5)
    merged['eth_weak'] = merged['eth_ret5'] < merged['btc_ret5']

    # Pre-3d trend
    merged['ratio_up_3d'] = (merged['ratio'].diff(1) > 0).rolling(3, min_periods=2).sum() >= 2

    return merged


def backtest_phase1(df, event_date_str):
    """Phase 1: Pre-1d ETH Lead - SHORT ratio at D-2, exit at D-1"""
    event_date = pd.to_datetime(event_date_str).date()
    df_sorted = df.sort_values('date').reset_index(drop=True)

    pre_2 = event_date - timedelta(days=2)
    pre_1 = event_date - timedelta(days=1)

    # Find closest trading days
    row_entry = df_sorted[df_sorted['date'] == pre_2]
    if len(row_entry) == 0:
        candidates = df_sorted[(df_sorted['date'] >= pre_2 - timedelta(days=2)) &
                               (df_sorted['date'] <= pre_2)]
        if len(candidates) == 0:
            return None
        row_entry = candidates.iloc[[-1]]

    row_exit = df_sorted[df_sorted['date'] == pre_1]
    if len(row_exit) == 0:
        candidates = df_sorted[(df_sorted['date'] >= pre_1 - timedelta(days=1)) &
                               (df_sorted['date'] <= pre_1 + timedelta(days=1))]
        if len(candidates) == 0:
            return None
        row_exit = candidates.iloc[[-1]]

    entry_ratio = row_entry['ratio'].values[0]
    exit_ratio = row_exit['ratio'].values[0]
    entry_date = row_entry['date'].values[0]
    exit_date = row_exit['date'].values[0]

    # SHORT ratio = profit when ratio drops
    pnl = ((entry_ratio - exit_ratio) / entry_ratio) * 100 - COST

    return {
        'phase': 1, 'name': 'Pre-1d ETH Lead',
        'entry_date': str(entry_date), 'exit_date': str(exit_date),
        'entry_ratio': round(entry_ratio, 4), 'exit_ratio': round(exit_ratio, 4),
        'pnl': round(pnl, 3), 'direction': 'SHORT_RATIO',
    }


def backtest_phase2(df, event_date_str):
    """Phase 2: Vol Breakout - enter on event day if ratio breaks 5d range"""
    event_date = pd.to_datetime(event_date_str).date()
    df_sorted = df.sort_values('date').reset_index(drop=True)

    event_idx = df_sorted[df_sorted['date'] == event_date].index
    if len(event_idx) == 0:
        return None
    event_idx = event_idx[0]

    if event_idx < 6:
        return None

    # 5-day range before event
    range_5d = df_sorted.loc[event_idx - 5:event_idx - 1, 'ratio']
    range_high = range_5d.max()
    range_low = range_5d.min()
    range_width = range_high - range_low

    if range_width <= 0:
        return None

    event_ratio = df_sorted.loc[event_idx, 'ratio']

    if event_ratio > range_high:
        direction = 'LONG_RATIO'
        sl_ratio = event_ratio - range_width * 0.5
        tp_ratio = event_ratio + range_width * 1.5
    elif event_ratio < range_low:
        direction = 'SHORT_RATIO'
        sl_ratio = event_ratio + range_width * 0.5
        tp_ratio = event_ratio - range_width * 1.5
    else:
        return None  # No breakout

    # Check exits over next 5 days
    for d in range(1, 6):
        if event_idx + d >= len(df_sorted):
            break
        r = df_sorted.loc[event_idx + d, 'ratio']

        if direction == 'LONG_RATIO':
            if r <= sl_ratio:
                pnl = ((r - event_ratio) / event_ratio) * 100 - COST
                return {'phase': 2, 'name': 'Vol Breakout', 'direction': direction,
                        'entry_date': str(event_date), 'exit_date': str(df_sorted.loc[event_idx + d, 'date']),
                        'entry_ratio': round(event_ratio, 4), 'exit_ratio': round(r, 4),
                        'pnl': round(pnl, 3), 'exit_reason': 'SL', 'days': d}
            if r >= tp_ratio:
                pnl = ((r - event_ratio) / event_ratio) * 100 - COST
                return {'phase': 2, 'name': 'Vol Breakout', 'direction': direction,
                        'entry_date': str(event_date), 'exit_date': str(df_sorted.loc[event_idx + d, 'date']),
                        'entry_ratio': round(event_ratio, 4), 'exit_ratio': round(r, 4),
                        'pnl': round(pnl, 3), 'exit_reason': 'TP', 'days': d}
        else:
            if r >= sl_ratio:
                pnl = ((event_ratio - r) / event_ratio) * 100 - COST
                return {'phase': 2, 'name': 'Vol Breakout', 'direction': direction,
                        'entry_date': str(event_date), 'exit_date': str(df_sorted.loc[event_idx + d, 'date']),
                        'entry_ratio': round(event_ratio, 4), 'exit_ratio': round(r, 4),
                        'pnl': round(pnl, 3), 'exit_reason': 'SL', 'days': d}
            if r <= tp_ratio:
                pnl = ((event_ratio - r) / event_ratio) * 100 - COST
                return {'phase': 2, 'name': 'Vol Breakout', 'direction': direction,
                        'entry_date': str(event_date), 'exit_date': str(df_sorted.loc[event_idx + d, 'date']),
                        'entry_ratio': round(event_ratio, 4), 'exit_ratio': round(r, 4),
                        'pnl': round(pnl, 3), 'exit_reason': 'TP', 'days': d}

    # Max hold exit
    d = min(5, len(df_sorted) - event_idx - 1)
    if d == 0:
        return None
    r = df_sorted.loc[event_idx + d, 'ratio']
    if direction == 'LONG_RATIO':
        pnl = ((r - event_ratio) / event_ratio) * 100 - COST
    else:
        pnl = ((event_ratio - r) / event_ratio) * 100 - COST

    return {'phase': 2, 'name': 'Vol Breakout', 'direction': direction,
            'entry_date': str(event_date), 'exit_date': str(df_sorted.loc[event_idx + d, 'date']),
            'entry_ratio': round(event_ratio, 4), 'exit_ratio': round(r, 4),
            'pnl': round(pnl, 3), 'exit_reason': 'MAX_HOLD', 'days': d}


def backtest_phase3(df, event_date_str):
    """Phase 3: Post-10d BTC Lead - LONG ratio at D+5, exit at D+20"""
    event_date = pd.to_datetime(event_date_str).date()
    df_sorted = df.sort_values('date').reset_index(drop=True)

    entry_target = event_date + timedelta(days=5)
    exit_target = event_date + timedelta(days=20)

    # Find closest trading days
    entry_candidates = df_sorted[(df_sorted['date'] >= entry_target) &
                                  (df_sorted['date'] <= entry_target + timedelta(days=3))]
    exit_candidates = df_sorted[(df_sorted['date'] >= exit_target) &
                                 (df_sorted['date'] <= exit_target + timedelta(days=3))]

    if len(entry_candidates) == 0 or len(exit_candidates) == 0:
        return None

    row_entry = entry_candidates.iloc[[0]]
    row_exit = exit_candidates.iloc[[0]]

    entry_ratio = row_entry['ratio'].values[0]
    exit_ratio = row_exit['ratio'].values[0]
    entry_date = row_entry['date'].values[0]
    exit_date = row_exit['date'].values[0]

    # LONG ratio
    pnl = ((exit_ratio - entry_ratio) / entry_ratio) * 100 - COST

    # Check percentile filter at entry
    entry_idx = row_entry.index[0]
    if entry_idx >= 60:
        pct = df_sorted.loc[:entry_idx, 'ratio'].rank(pct=True).iloc[-1]
        filtered = pct >= 0.90
    else:
        pct = 0.5
        filtered = False

    return {
        'phase': 3, 'name': 'Post-10d BTC Lead',
        'entry_date': str(entry_date), 'exit_date': str(exit_date),
        'entry_ratio': round(entry_ratio, 4), 'exit_ratio': round(exit_ratio, 4),
        'pnl': round(pnl, 3), 'direction': 'LONG_RATIO',
        'pctile': round(pct, 3), 'filter_pass': filtered,
    }


def calc_metrics(trades):
    if not trades:
        return None
    pnls = [t['pnl'] for t in trades]
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / n if n > 0 else 0
    ev = np.mean(pnls)
    pf = sum(wins) / abs(sum(losses)) if sum(losses) != 0 else (1 if sum(wins) > 0 else 0)
    t_stat, p_val = stats.ttest_1samp(pnls, 0) if n >= 2 else (0, 1)
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0

    # Bootstrap CI
    if n >= 5:
        rng = np.random.RandomState(42)
        boot_evs = [np.mean(rng.choice(pnls, size=n, replace=True)) for _ in range(2000)]
        ci_lo = np.percentile(boot_evs, 2.5)
        ci_hi = np.percentile(boot_evs, 97.5)
    else:
        ci_lo, ci_hi = ev - np.std(pnls), ev + np.std(pnls)

    return {
        'n': n, 'wr': round(wr, 3), 'ev': round(ev, 3),
        'pf': round(pf, 3), 'sharpe': round(sharpe, 3),
        'total_pnl': round(sum(pnls), 3),
        't_stat': round(t_stat, 3), 'p_val': round(p_val, 4),
        'ci_lo': round(ci_lo, 3), 'ci_hi': round(ci_hi, 3),
    }


def main():
    print("Loading local data...")
    df = load_local_data()
    print(f"Data range: {df['date'].min()} ~ {df['date'].max()} ({len(df)} days)")

    print("=" * 90)
    print("CLARITY ACT PHASE STRATEGY - BACKTEST VERIFICATION")
    print(f"Data: {df['date'].min()} ~ {df['date'].max()} ({len(df)} trading days)")
    print(f"Cost: {COST}% round-trip")
    print(f"Events: {len(EVENTS)}")
    print("=" * 90)

    all_results = {1: [], 2: [], 3: []}

    for event_name, event_date in EVENTS:
        print(f"\n--- {event_name} ({event_date}) ---")

        p1 = backtest_phase1(df, event_date)
        p2 = backtest_phase2(df, event_date)
        p3 = backtest_phase3(df, event_date)

        for phase_num, phase_result in [(1, p1), (2, p2), (3, p3)]:
            if phase_result:
                all_results[phase_num].append(phase_result)
                extra = ""
                if 'exit_reason' in phase_result:
                    extra = f" Exit={phase_result['exit_reason']}"
                if 'pctile' in phase_result:
                    extra += f" Pctile={phase_result['pctile']:.3f}"
                print(f"  Phase {phase_num}: {phase_result['name']:20s} "
                      f"PnL={phase_result['pnl']:+6.3f}% "
                      f"Dir={phase_result['direction']:12s} "
                      f"Entry={phase_result['entry_ratio']:.4f} "
                      f"Exit={phase_result['exit_ratio']:.4f}{extra}")
            else:
                print(f"  Phase {phase_num}: NO TRADE")

    # Summary
    print("\n" + "=" * 90)
    print("PHASE SUMMARY")
    print("=" * 90)
    fmt = "{:<12} {:>4} {:>7} {:>8} {:>7} {:>8} {:>8} {:>10} {:>8}"
    print(fmt.format("Phase", "N", "WR", "EV", "PF", "Sharpe", "p-val", "95% CI", "Total"))
    print("-" * 90)

    for phase_num in [1, 2, 3]:
        trades = all_results[phase_num]
        m = calc_metrics(trades)
        if m:
            sig = "*" if m['p_val'] < 0.05 else " "
            print(f"Phase {phase_num}   {m['n']:>4} {m['wr']:>6.1%} {m['ev']:>+7.3f}% "
                  f"{m['pf']:>6.2f} {m['sharpe']:>+7.2f} {m['p_val']:>7.4f}{sig} "
                  f"[{m['ci_lo']:+.3f},{m['ci_hi']:+.3f}] "
                  f"{m['total_pnl']:>+7.3f}%")

    # Combined portfolio
    all_trades = all_results[1] + all_results[2] + all_results[3]
    m_all = calc_metrics(all_trades)
    if m_all:
        print(f"\n{'PORTFOLIO':>12} {m_all['n']:>4} {m_all['wr']:>6.1%} {m_all['ev']:>+7.3f}% "
              f"{m_all['pf']:>6.2f} {m_all['sharpe']:>+7.2f} {m_all['p_val']:>7.4f} "
              f"[{m_all['ci_lo']:+.3f},{m_all['ci_hi']:+.3f}] "
              f"{m_all['total_pnl']:>+7.3f}%")

    # Phase 3 with percentile filter
    p3_filtered = [t for t in all_results[3] if t.get('filter_pass', False)]
    if p3_filtered:
        m_p3f = calc_metrics(p3_filtered)
        if m_p3f:
            print(f"\n{'Ph3(Filt)':>12} {m_p3f['n']:>4} {m_p3f['wr']:>6.1%} {m_p3f['ev']:>+7.3f}% "
                  f"{m_p3f['pf']:>6.2f} {m_p3f['sharpe']:>+7.2f} {m_p3f['p_val']:>7.4f} "
                  f"[{m_p3f['ci_lo']:+.3f},{m_p3f['ci_hi']:+.3f}] "
                  f"{m_p3f['total_pnl']:>+7.3f}%")

    # Save
    output = {
        'events': {name: date for name, date in EVENTS},
        'phases': {str(k): v for k, v in all_results.items()},
        'summary': {str(k): calc_metrics(v) for k, v in all_results.items()},
        'portfolio': m_all,
        'phase3_filtered': calc_metrics(p3_filtered) if p3_filtered else None,
    }
    path = os.path.join(DATA_DIR, 'clarity_phase_backtest_results.json')
    with open(path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {path}")


if __name__ == '__main__':
    main()
