#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detailed Crypto Regulatory Events Analysis with Extended Event List
"""

import pandas as pd
import json
from datetime import datetime, timedelta
import numpy as np

# Define regulatory events covering periods where we have BOTH BTC and ETH data
REGULATORY_EVENTS = [
    # 2024-2025 Events (Good ETH data coverage)
    {
        'name': 'FIT21 House Pass',
        'date': '2024-05-22',
        'type': 'A',
        'description': 'House passes crypto-friendly regulatory bill',
        'note': 'Expected: BTC/ETH upside'
    },
    {
        'name': 'Trump Wins Election',
        'date': '2024-11-05',
        'type': 'A',
        'description': 'Pro-crypto Trump wins US presidential election',
        'note': 'Positive crypto sentiment expected'
    },
    {
        'name': 'Gary Gensler Resigns',
        'date': '2025-01-09',
        'type': 'A',
        'description': 'SEC Chair resigns, replaced by pro-crypto Paul Atkins nominee',
        'note': 'Major crypto positive catalyst'
    },
    {
        'name': 'Trump Bitcoin Reserve Announcement',
        'date': '2025-01-20',
        'type': 'A',
        'description': 'Trump inaugural - crypto friendly policies expected',
        'note': 'Positive regulatory environment shift'
    },
    {
        'name': 'Stablecoin Bill Discussion',
        'date': '2024-03-15',
        'type': 'C',
        'description': 'Congress discusses stablecoin regulation framework',
        'note': 'Uncertain regulatory path'
    },
    {
        'name': 'ETF Spot Bitcoin Approval',
        'date': '2024-01-11',
        'type': 'A',
        'description': 'SEC approves spot Bitcoin ETF',
        'note': 'Institutional adoption boost'
    },
    {
        'name': 'ETF Spot Ethereum Approval',
        'date': '2024-05-23',
        'type': 'A',
        'description': 'SEC approves spot Ethereum ETF',
        'note': 'Major institutional catalyst for ETH'
    }
]

def load_price_data(symbol='BTC'):
    """Load price data for symbol"""
    if symbol == 'BTC':
        df = pd.read_csv('/Users/user/Desktop/trade/data/btc_price_1d_extended.csv')
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
    elif symbol == 'ETH':
        df = pd.read_csv('/Users/user/Desktop/trade/data/ETH_USDT_4h_730d.csv')
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
        # Aggregate 4h to 1d
        df['date'] = df['datetime'].dt.date
        daily = df.groupby('date').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()
        daily['datetime'] = pd.to_datetime(daily['date'])
        df = daily[['datetime', 'open', 'high', 'low', 'close', 'volume']].sort_values('datetime')

    return df

def analyze_event_detailed(df, event, symbol='BTC'):
    """Detailed analysis with extra metrics"""
    event_date = pd.to_datetime(event['date'])

    # Find closest date in dataset
    df['date_diff'] = (df['datetime'].dt.date - event_date.date()).apply(lambda x: abs(x.days))
    closest_idx = df['date_diff'].idxmin()
    actual_event_date = df.loc[closest_idx, 'datetime']

    # Check if event is in dataset
    if df.loc[closest_idx, 'date_diff'] > 5:
        return None

    # Define periods
    period_30d_before = actual_event_date - timedelta(days=30)
    period_7d_after = actual_event_date + timedelta(days=7)
    period_30d_after = actual_event_date + timedelta(days=30)
    period_60d_before = actual_event_date - timedelta(days=60)

    before_30d = df[(df['datetime'] >= period_30d_before) & (df['datetime'] < actual_event_date)]
    before_60d = df[(df['datetime'] >= period_60d_before) & (df['datetime'] < actual_event_date)]
    event_day = df[df['datetime'].dt.date == actual_event_date.date()]
    after_7d = df[(df['datetime'] > actual_event_date) & (df['datetime'] <= period_7d_after)]
    after_30d = df[(df['datetime'] > actual_event_date) & (df['datetime'] <= period_30d_after)]

    if len(before_30d) == 0 or len(event_day) == 0:
        return None

    # 30d before metrics
    before_open = before_30d.iloc[0]['open']
    before_close = before_30d.iloc[-1]['close']
    before_high = before_30d['high'].max()
    before_low = before_30d['low'].min()
    before_return = ((before_close - before_open) / before_open) * 100
    before_volatility = before_30d['close'].pct_change().std() * 100
    before_avg_volume = before_30d['volume'].mean()

    # Event day
    event_open = event_day.iloc[0]['open']
    event_close = event_day.iloc[0]['close']
    event_high = event_day.iloc[0]['high']
    event_low = event_day.iloc[0]['low']
    event_return = ((event_close - event_open) / event_open) * 100
    event_range_pct = ((event_high - event_low) / event_open) * 100
    event_volume = event_day.iloc[0]['volume']

    # 7d after
    after_7d_return = 0
    after_7d_volatility = 0
    after_7d_volume = 0
    if len(after_7d) > 1:
        after_7d_return = ((after_7d.iloc[-1]['close'] - event_close) / event_close) * 100
        after_7d_volatility = after_7d['close'].pct_change().std() * 100
        after_7d_volume = after_7d['volume'].mean()

    # 30d after
    after_30d_return = 0
    after_30d_volatility = 0
    if len(after_30d) > 1:
        after_30d_return = ((after_30d.iloc[-1]['close'] - event_close) / event_close) * 100
        after_30d_volatility = after_30d['close'].pct_change().std() * 100

    # Price action pattern (up/down/consolidation)
    if abs(event_return) < 0.5:
        pattern = 'CONSOLIDATION'
    elif event_return > 0:
        pattern = 'UP'
    else:
        pattern = 'DOWN'

    if len(after_7d) > 1:
        if after_7d_return > 2:
            after_pattern = 'RECOVERY'
        elif after_7d_return < -2:
            after_pattern = 'CONTINUED_DOWN'
        else:
            after_pattern = 'CONSOLIDATION'
    else:
        after_pattern = 'UNKNOWN'

    return {
        'event': event['name'],
        'actual_date': actual_event_date.date(),
        'type': event['type'],
        'description': event['description'],
        # 30d before
        'before_30d_return': before_return,
        'before_30d_volatility': before_volatility,
        'before_30d_volume_avg': before_avg_volume,
        # Event day
        'event_return': event_return,
        'event_range_pct': event_range_pct,
        'event_volume': event_volume,
        'event_pattern': pattern,
        # 7d after
        'after_7d_return': after_7d_return,
        'after_7d_volatility': after_7d_volatility,
        'after_7d_pattern': after_pattern,
        # 30d after
        'after_30d_return': after_30d_return,
        'after_30d_volatility': after_30d_volatility,
    }

def main():
    print("\n" + "=" * 100)
    print(" " * 30 + "CRYPTO REGULATORY EVENTS DETAILED ANALYSIS")
    print("=" * 100)

    btc_df = load_price_data('BTC')
    eth_df = load_price_data('ETH')

    print(f"\n[✓] Loaded data:")
    print(f"    BTC: {len(btc_df)} days ({btc_df['datetime'].min().date()} to {btc_df['datetime'].max().date()})")
    print(f"    ETH: {len(eth_df)} days ({eth_df['datetime'].min().date()} to {eth_df['datetime'].max().date()})")

    # Filter events to only those in ETH data range
    eth_min = eth_df['datetime'].min().date()
    eth_max = eth_df['datetime'].max().date()
    valid_events = [e for e in REGULATORY_EVENTS if eth_min <= pd.to_datetime(e['date']).date() <= eth_max]

    print(f"\n[*] Analyzing {len(valid_events)} events in common data range:")
    print()

    results = {'A': [], 'B': [], 'C': []}

    for event in valid_events:
        print(f"  [{event['type']}] {event['name']:40s} ({event['date']})")

        btc_result = analyze_event_detailed(btc_df, event, 'BTC')
        eth_result = analyze_event_detailed(eth_df, event, 'ETH')

        if btc_result and eth_result:
            combined = {
                'event': event['name'],
                'date': event['date'],
                'type': event['type'],
                'btc': btc_result,
                'eth': eth_result,
                'eth_btc_relative_performance': {
                    'event_day': eth_result['event_return'] - btc_result['event_return'],
                    'after_7d': eth_result['after_7d_return'] - btc_result['after_7d_return'],
                    'after_30d': eth_result['after_30d_return'] - btc_result['after_30d_return']
                }
            }
            results[event['type']].append(combined)

            print(f"        Status: ✓ FOUND")
            print(f"        BTC:  Before:{btc_result['before_30d_return']:+6.2f}%  Day:{btc_result['event_return']:+6.2f}%  +7d:{btc_result['after_7d_return']:+6.2f}%  +30d:{btc_result['after_30d_return']:+6.2f}%")
            print(f"        ETH:  Before:{eth_result['before_30d_return']:+6.2f}%  Day:{eth_result['event_return']:+6.2f}%  +7d:{eth_result['after_7d_return']:+6.2f}%  +30d:{eth_result['after_30d_return']:+6.2f}%")
            print(f"        ETH-BTC: Day:{combined['eth_btc_relative_performance']['event_day']:+6.2f}%  +7d:{combined['eth_btc_relative_performance']['after_7d']:+6.2f}%  +30d:{combined['eth_btc_relative_performance']['after_30d']:+6.2f}%")
        else:
            print(f"        Status: ✗ INSUFFICIENT DATA")
        print()

    # Summary statistics
    print("\n" + "=" * 100)
    print(" " * 35 + "SUMMARY BY REGULATORY TYPE")
    print("=" * 100)

    for type_label, type_name in [('A', '📈 POSITIVE/CLARITY (Type A)'), ('B', '📉 NEGATIVE/RESTRICTIVE (Type B)'), ('C', '❓ UNCERTAIN (Type C)')]:
        events = results[type_label]

        if not events:
            print(f"\n[{type_label}] {type_name}")
            print("-" * 100)
            print("  No events in data range\n")
            continue

        print(f"\n[{type_label}] {type_name}")
        print("-" * 100)
        print(f"  Sample Size: {len(events)} events\n")

        # BTC statistics
        btc_before = [e['btc']['before_30d_return'] for e in events]
        btc_event = [e['btc']['event_return'] for e in events]
        btc_after7 = [e['btc']['after_7d_return'] for e in events]
        btc_after30 = [e['btc']['after_30d_return'] for e in events]

        # ETH statistics
        eth_before = [e['eth']['before_30d_return'] for e in events]
        eth_event = [e['eth']['event_return'] for e in events]
        eth_after7 = [e['eth']['after_7d_return'] for e in events]
        eth_after30 = [e['eth']['after_30d_return'] for e in events]

        eth_btc_day = [e['eth_btc_relative_performance']['event_day'] for e in events]
        eth_btc_7d = [e['eth_btc_relative_performance']['after_7d'] for e in events]
        eth_btc_30d = [e['eth_btc_relative_performance']['after_30d'] for e in events]

        print(f"  BTC PERFORMANCE:")
        print(f"    30d before:  {np.mean(btc_before):+7.2f}% (σ={np.std(btc_before):5.2f}%)")
        print(f"    Event day:   {np.mean(btc_event):+7.2f}% (σ={np.std(btc_event):5.2f}%) | Range:{np.mean([e['btc']['event_range_pct'] for e in events]):5.2f}%")
        print(f"    7d after:    {np.mean(btc_after7):+7.2f}% (σ={np.std(btc_after7):5.2f}%)")
        print(f"    30d after:   {np.mean(btc_after30):+7.2f}% (σ={np.std(btc_after30):5.2f}%)")

        print(f"\n  ETH PERFORMANCE:")
        print(f"    30d before:  {np.mean(eth_before):+7.2f}% (σ={np.std(eth_before):5.2f}%)")
        print(f"    Event day:   {np.mean(eth_event):+7.2f}% (σ={np.std(eth_event):5.2f}%) | Range:{np.mean([e['eth']['event_range_pct'] for e in events]):5.2f}%")
        print(f"    7d after:    {np.mean(eth_after7):+7.2f}% (σ={np.std(eth_after7):5.2f}%)")
        print(f"    30d after:   {np.mean(eth_after30):+7.2f}% (σ={np.std(eth_after30):5.2f}%)")

        print(f"\n  ETH vs BTC RELATIVE PERFORMANCE (ETH - BTC):")
        print(f"    Event day:   {np.mean(eth_btc_day):+7.2f}% (ETH {'outperforms' if np.mean(eth_btc_day) > 0 else 'underperforms'} BTC)")
        print(f"    7d after:    {np.mean(eth_btc_7d):+7.2f}%")
        print(f"    30d after:   {np.mean(eth_btc_30d):+7.2f}%")

        print(f"\n  VOLATILITY (STD of daily returns):")
        print(f"    BTC before: {np.mean([e['btc']['before_30d_volatility'] for e in events]):5.2f}% | after 7d: {np.mean([e['btc']['after_7d_volatility'] for e in events]):5.2f}%")
        print(f"    ETH before: {np.mean([e['eth']['before_30d_volatility'] for e in events]):5.2f}% | after 7d: {np.mean([e['eth']['after_7d_volatility'] for e in events]):5.2f}%")

        print(f"\n  INDIVIDUAL EVENTS:")
        for event in events:
            print(f"\n    {event['event']} ({event['date']})")
            print(f"      BTC: {event['btc']['before_30d_return']:+6.2f}% → {event['btc']['event_return']:+6.2f}% ({event['btc']['event_pattern']:12s}) → +7d:{event['btc']['after_7d_return']:+6.2f}% → +30d:{event['btc']['after_30d_return']:+6.2f}%")
            print(f"      ETH: {event['eth']['before_30d_return']:+6.2f}% → {event['eth']['event_return']:+6.2f}% ({event['eth']['event_pattern']:12s}) → +7d:{event['eth']['after_7d_return']:+6.2f}% → +30d:{event['eth']['after_30d_return']:+6.2f}%")
            print(f"      Relative: Day {event['eth_btc_relative_performance']['event_day']:+6.2f}% | +7d {event['eth_btc_relative_performance']['after_7d']:+6.2f}% | +30d {event['eth_btc_relative_performance']['after_30d']:+6.2f}%")

    # Save detailed results
    with open('/Users/user/Desktop/trade/data/regulatory_events_detailed.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 100)
    print("[✓] Analysis saved to: regulatory_events_detailed.json")
    print("=" * 100 + "\n")

if __name__ == '__main__':
    main()
