#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crypto Regulatory Events Impact Analysis

Analyze BTC/ETH price movement before/after major crypto regulation events
"""

import pandas as pd
import json
from datetime import datetime, timedelta
import numpy as np

# Define major regulatory events
REGULATORY_EVENTS = [
    {
        'name': 'FIT21 House Pass',
        'date': '2024-05-22',
        'type': 'A',  # Positive
        'description': 'Financial Innovation and Technology 2021 Act passed House',
        'note': 'Crypto-friendly, provides regulatory clarity'
    },
    {
        'name': 'Gary Gensler Resignation Announcement',
        'date': '2025-01-09',
        'type': 'A',  # Positive for crypto
        'description': 'SEC Chair Gary Gensler announced resignation',
        'note': 'Seen as positive by crypto community (pro-regulation stance)'
    },
    {
        'name': 'MiCA Enforcement',
        'date': '2023-12-31',
        'type': 'B',  # Regulation-Heavy
        'description': 'EU Markets in Crypto Assets Regulation goes live',
        'note': 'Strict regulatory framework for EU crypto operations'
    },
    {
        'name': 'China Mining Ban',
        'date': '2021-06-18',
        'type': 'B',  # Negative
        'description': 'China bans crypto mining nationwide',
        'note': 'Major supply shock, negative sentiment'
    },
    {
        'name': 'CBDCs Timeline',
        'date': '2022-03-14',
        'type': 'C',  # Uncertain
        'description': 'Federal Reserve releases CBDC policy paper',
        'note': 'Regulatory uncertainty about digital currencies'
    }
]

def load_price_data(symbol='BTC'):
    """Load price data for symbol"""
    if symbol == 'BTC':
        df = pd.read_csv('/Users/user/Desktop/trade/data/btc_price_1d_extended.csv')
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
    elif symbol == 'ETH':
        # Load 4h data and aggregate to daily
        df = pd.read_csv('/Users/user/Desktop/trade/data/ETH_USDT_4h_730d.csv')
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
        # Aggregate 4h to 1d (take last 4h close of each day)
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

def analyze_event(df, event, symbol='BTC'):
    """Analyze price movement around a specific event"""
    event_date = pd.to_datetime(event['date'])

    # Find the closest date in data
    df['date_diff'] = (df['datetime'].dt.date - event_date.date()).apply(lambda x: abs(x.days))
    closest_idx = df['date_diff'].idxmin()
    actual_event_date = df.loc[closest_idx, 'datetime']

    # Event not in dataset
    if df.loc[closest_idx, 'date_diff'] > 5:
        return None

    # Define periods
    period_30d_before = actual_event_date - timedelta(days=30)
    period_7d_after = actual_event_date + timedelta(days=7)
    period_30d_after = actual_event_date + timedelta(days=30)

    # Extract data for each period
    before_30d = df[(df['datetime'] >= period_30d_before) & (df['datetime'] < actual_event_date)]
    event_day = df[df['datetime'].dt.date == actual_event_date.date()]
    after_7d = df[(df['datetime'] > actual_event_date) & (df['datetime'] <= period_7d_after)]
    after_30d = df[(df['datetime'] > actual_event_date) & (df['datetime'] <= period_30d_after)]

    if len(before_30d) == 0 or len(event_day) == 0:
        return None

    # Calculate metrics for 30d before
    before_open = before_30d.iloc[0]['open']
    before_close = before_30d.iloc[-1]['close']
    before_return = ((before_close - before_open) / before_open) * 100
    before_volatility = before_30d['close'].pct_change().std() * 100

    # Event day metrics
    event_open = event_day.iloc[0]['open']
    event_close = event_day.iloc[0]['close']
    event_high = event_day.iloc[0]['high']
    event_low = event_day.iloc[0]['low']
    event_return = ((event_close - event_open) / event_open) * 100
    event_range = event_high - event_low

    # 7d after
    after_7d_return = 0
    if len(after_7d) > 0:
        after_7d_return = ((after_7d.iloc[-1]['close'] - event_close) / event_close) * 100

    # 30d after
    after_30d_return = 0
    if len(after_30d) > 0:
        after_30d_return = ((after_30d.iloc[-1]['close'] - event_close) / event_close) * 100

    return {
        'event': event['name'],
        'actual_date': actual_event_date.date(),
        'type': event['type'],
        'before_30d_return': before_return,
        'before_30d_volatility': before_volatility,
        'event_day_return': event_return,
        'event_day_range': event_range,
        'after_7d_return': after_7d_return,
        'after_30d_return': after_30d_return,
    }

def main():
    print("=" * 80)
    print("CRYPTO REGULATORY EVENTS IMPACT ANALYSIS")
    print("=" * 80)
    print()

    # Load data
    print("[*] Loading BTC price data...")
    btc_df = load_price_data('BTC')
    print(f"    BTC: {len(btc_df)} days ({btc_df['datetime'].min().date()} to {btc_df['datetime'].max().date()})")

    print("[*] Loading ETH price data...")
    eth_df = load_price_data('ETH')
    print(f"    ETH: {len(eth_df)} days ({eth_df['datetime'].min().date()} to {eth_df['datetime'].max().date()})")
    print()

    # Analyze each event
    results = {
        'A': [],  # Positive
        'B': [],  # Negative
        'C': []   # Uncertain
    }

    for event in REGULATORY_EVENTS:
        print(f"[*] Analyzing: {event['name']} ({event['date']})")
        print(f"    Type: {event['type']} | {event['description']}")

        btc_result = analyze_event(btc_df, event, 'BTC')
        eth_result = analyze_event(eth_df, event, 'ETH')

        if btc_result and eth_result:
            # Combine results
            combined = {
                'event': event['name'],
                'date': event['date'],
                'type': event['type'],
                'btc': btc_result,
                'eth': eth_result,
                'eth_btc_relative_perf': eth_result['event_day_return'] - btc_result['event_day_return']
            }
            results[event['type']].append(combined)

            print(f"    ✓ Data found")
            print(f"      BTC 30d before: {btc_result['before_30d_return']:+.2f}% | Event day: {btc_result['event_day_return']:+.2f}% | 7d after: {btc_result['after_7d_return']:+.2f}% | 30d after: {btc_result['after_30d_return']:+.2f}%")
            print(f"      ETH 30d before: {eth_result['before_30d_return']:+.2f}% | Event day: {eth_result['event_day_return']:+.2f}% | 7d after: {eth_result['after_7d_return']:+.2f}% | 30d after: {eth_result['after_30d_return']:+.2f}%")
        else:
            print(f"    ✗ Insufficient data")
        print()

    # Generate summary statistics
    print("=" * 80)
    print("SUMMARY BY REGULATORY TYPE")
    print("=" * 80)
    print()

    for type_label, type_name in [('A', 'POSITIVE (Type A)'), ('B', 'NEGATIVE (Type B)'), ('C', 'UNCERTAIN (Type C)')]:
        events = results[type_label]
        if not events:
            print(f"[{type_label}] {type_name}: No data")
            continue

        print(f"[{type_label}] {type_name}: {len(events)} events")
        print("-" * 80)

        # Calculate averages
        btc_before_avg = np.mean([e['btc']['before_30d_return'] for e in events])
        btc_event_avg = np.mean([e['btc']['event_day_return'] for e in events])
        btc_after7_avg = np.mean([e['btc']['after_7d_return'] for e in events])
        btc_after30_avg = np.mean([e['btc']['after_30d_return'] for e in events])

        eth_before_avg = np.mean([e['eth']['before_30d_return'] for e in events])
        eth_event_avg = np.mean([e['eth']['event_day_return'] for e in events])
        eth_after7_avg = np.mean([e['eth']['after_7d_return'] for e in events])
        eth_after30_avg = np.mean([e['eth']['after_30d_return'] for e in events])

        eth_btc_relative = np.mean([e['eth_btc_relative_perf'] for e in events])

        print(f"  BTC Average Returns:")
        print(f"    30d before:  {btc_before_avg:+7.2f}%")
        print(f"    Event day:   {btc_event_avg:+7.2f}%")
        print(f"    7d after:    {btc_after7_avg:+7.2f}%")
        print(f"    30d after:   {btc_after30_avg:+7.2f}%")
        print()

        print(f"  ETH Average Returns:")
        print(f"    30d before:  {eth_before_avg:+7.2f}%")
        print(f"    Event day:   {eth_event_avg:+7.2f}%")
        print(f"    7d after:    {eth_after7_avg:+7.2f}%")
        print(f"    30d after:   {eth_after30_avg:+7.2f}%")
        print()

        print(f"  ETH/BTC Relative Performance (ETH return - BTC return):")
        print(f"    Event day: {eth_btc_relative:+7.2f}%")
        print()

        # Print individual events
        for event in events:
            print(f"    {event['event']} ({event['date']})")
            print(f"      BTC: {event['btc']['before_30d_return']:+6.2f}% → {event['btc']['event_day_return']:+6.2f}% → {event['btc']['after_7d_return']:+6.2f}% (7d) → {event['btc']['after_30d_return']:+6.2f}% (30d)")
            print(f"      ETH: {event['eth']['before_30d_return']:+6.2f}% → {event['eth']['event_day_return']:+6.2f}% → {event['eth']['after_7d_return']:+6.2f}% (7d) → {event['eth']['after_30d_return']:+6.2f}% (30d)")

        print()

    # Output structured data
    with open('/Users/user/Desktop/trade/data/regulatory_events_analysis.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print("=" * 80)
    print("[✓] Analysis complete. Results saved to regulatory_events_analysis.json")
    print("=" * 80)

if __name__ == '__main__':
    main()
