#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC/ETH Ratio Volatility & Volume Analysis around Regulatory Events
規制イベント前後のBTC/ETHレシオ ボラティリティ・ボリュームパターン分析
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = r"C:\Users\user\Desktop\cursor\trade\data"

# ============================================================
# イベント定義（データカバー範囲内のイベントのみ）
# ============================================================
REGULATORY_EVENTS = [
    # SEC系
    {"name": "Bitcoin ETF Approval",           "date": "2024-01-10", "category": "SEC",
     "desc": "SEC approves spot Bitcoin ETFs (sell-the-news)"},
    {"name": "ETH ETF Approval",               "date": "2024-05-23", "category": "SEC",
     "desc": "SEC approves spot Ethereum ETF 19b-4"},
    {"name": "Coinbase SEC Wells Notice",      "date": "2023-06-06", "category": "SEC",
     "desc": "SEC issues Wells Notice to Coinbase"},
    {"name": "Binance DOJ Settlement",         "date": "2023-06-15", "category": "SEC",
     "desc": "DOJ enforcement action against Binance"},
    {"name": "Gary Gensler Resignation",        "date": "2025-01-09", "category": "SEC",
     "desc": "SEC Chair Gensler announces resignation"},
    # 立法系
    {"name": "FIT21 House Pass",               "date": "2024-05-22", "category": "LEGISLATIVE",
     "desc": "House passes crypto regulatory framework bill"},
    {"name": "GENIUS Act Senate Pass",         "date": "2025-06-17", "category": "LEGISLATIVE",
     "desc": "Senate passes stablecoin bill (68-30)"},
    {"name": "CLARITY Act House Pass",         "date": "2025-07-17", "category": "LEGISLATIVE",
     "desc": "House passes market structure bill (294-134)"},
    # 行政系
    {"name": "Trump Wins Election",            "date": "2024-11-05", "category": "EXECUTIVE",
     "desc": "Pro-crypto Trump wins presidential election"},
    {"name": "Trump BTC Reserve Announcement", "date": "2025-01-20", "category": "EXECUTIVE",
     "desc": "Trump inaugural - crypto reserve policies"},
    {"name": "Trump Crypto EO",                "date": "2025-01-23", "category": "EXECUTIVE",
     "desc": "Executive order on digital asset strategic reserve"},
]


def load_data():
    """Load BTC and ETH 4h data, compute daily aggregation and ratio"""
    # BTC 4h
    btc4 = pd.read_csv(f"{DATA_DIR}/btc_price_4h_cache.csv")
    btc4['datetime'] = pd.to_datetime(btc4['datetime'], utc=True)
    btc4 = btc4.sort_values('datetime').reset_index(drop=True)

    # ETH 4h
    eth4 = pd.read_csv(f"{DATA_DIR}/ETH_USDT_4h_730d.csv")
    eth4['datetime'] = pd.to_datetime(eth4['datetime'])
    eth4 = eth4.sort_values('datetime').reset_index(drop=True)
    eth4['datetime'] = eth4['datetime'].dt.tz_localize('UTC')

    # Daily aggregation
    btc4['date'] = btc4['datetime'].dt.date
    eth4['date'] = eth4['datetime'].dt.date

    btc_daily = btc4.groupby('date').agg(
        open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
        close=('close', 'last'), volume=('volume', 'sum')
    ).reset_index()
    btc_daily['date'] = pd.to_datetime(btc_daily['date'])

    eth_daily = eth4.groupby('date').agg(
        open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
        close=('close', 'last'), volume=('volume', 'sum')
    ).reset_index()
    eth_daily['date'] = pd.to_datetime(eth_daily['date'])

    # Merge on date
    merged = pd.merge(btc_daily, eth_daily, on='date', suffixes=('_btc', '_eth'))
    merged['ratio'] = merged['close_eth'] / merged['close_btc']
    merged['ratio_chg'] = merged['ratio'].pct_change() * 100
    merged = merged.dropna().reset_index(drop=True)

    return btc4, eth4, merged


def calc_rsi(series, period=14):
    """Calculate RSI"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_bollinger_width(series, period=20):
    """Bollinger Band width as % of SMA"""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    bb_width = (4 * std / sma) * 100  # Upper-Lower as % of SMA
    return bb_width


# ============================================================
# 1. Volatility Pattern
# ============================================================
def analyze_volatility_pattern(merged):
    print("=" * 90)
    print("1. VOLATILITY PATTERN ANALYSIS")
    print("   ボラティリティパターン: pre-10d vol vs post-10d vol around events")
    print("=" * 90)

    results = []
    for ev in REGULATORY_EVENTS:
        ev_date = pd.to_datetime(ev['date'])
        # Find closest date in data
        idx = merged['date'].searchsorted(ev_date)
        if idx >= len(merged):
            print(f"  {ev['name']} ({ev['date']}): Outside data range, SKIPPED")
            continue
        closest = merged.iloc[idx]
        if abs((closest['date'] - ev_date).days) > 3:
            # Try idx-1
            if idx > 0:
                closest = merged.iloc[idx - 1]
            if abs((closest['date'] - ev_date).days) > 3:
                print(f"  {ev['name']} ({ev['date']}): No nearby data, SKIPPED")
                continue

        ev_idx = merged.index[merged['date'] == closest['date']][0]

        # Pre 10d and Post 10d
        pre_start = max(0, ev_idx - 10)
        post_end = min(len(merged) - 1, ev_idx + 10)
        pre_10 = merged.iloc[pre_start:ev_idx]
        post_10 = merged.iloc[ev_idx + 1:post_end + 1]

        if len(pre_10) < 5 or len(post_10) < 5:
            print(f"  {ev['name']}: Insufficient data ({len(pre_10)} pre, {len(post_10)} post), SKIPPED")
            continue

        pre_vol = pre_10['ratio_chg'].std()
        post_vol = post_10['ratio_chg'].std()
        vol_ratio = post_vol / pre_vol if pre_vol > 0 else np.nan

        # Pre 5d vs Pre 20d for compression check
        pre5_start = max(0, ev_idx - 5)
        pre20_start = max(0, ev_idx - 20)
        pre5_vol = merged.iloc[pre5_start:ev_idx]['ratio_chg'].std()
        pre20_vol = merged.iloc[pre20_start:ev_idx]['ratio_chg'].std()
        compression = pre5_vol < pre20_vol

        # Post direction
        ratio_at_event = merged.iloc[ev_idx]['ratio']
        ratio_post5 = merged.iloc[min(ev_idx + 5, len(merged) - 1)]['ratio']
        post_direction = "UP" if ratio_post5 > ratio_at_event else "DOWN"
        post_pct = (ratio_post5 - ratio_at_event) / ratio_at_event * 100

        r = {
            'event': ev['name'], 'date': ev['date'], 'category': ev['category'],
            'pre_vol': pre_vol, 'post_vol': post_vol, 'vol_ratio': vol_ratio,
            'pre5_vol': pre5_vol, 'pre20_vol': pre20_vol,
            'compression': compression,
            'post_direction': post_direction, 'post_5d_pct': post_pct
        }
        results.append(r)

        print(f"\n  {ev['name']} ({ev['date']}) [{ev['category']}]")
        print(f"    Pre-10d vol:  {pre_vol:.6f}")
        print(f"    Post-10d vol: {post_vol:.6f}")
        print(f"    Vol ratio:    {vol_ratio:.3f}x")
        print(f"    Compression (5d<20d): {compression} (5d={pre5_vol:.6f}, 20d={pre20_vol:.6f})")
        print(f"    Post-5d direction: {post_direction} ({post_pct:+.4f}%)")

    if not results:
        print("  No events with sufficient data.")
        return []

    # Summary
    df_r = pd.DataFrame(results)
    print(f"\n  --- SUMMARY ---")
    print(f"  Events analyzed: {len(df_r)}")
    print(f"  Avg vol ratio (post/pre): {df_r['vol_ratio'].mean():.3f}x")
    print(f"  Vol expansion (ratio > 1): {(df_r['vol_ratio'] > 1).sum()}/{len(df_r)} = {(df_r['vol_ratio'] > 1).mean()*100:.1f}%")
    print(f"  Compression rate: {df_r['compression'].sum()}/{len(df_r)} = {df_r['compression'].mean()*100:.1f}%")

    compressed = df_r[df_r['compression']]
    if len(compressed) > 0:
        print(f"\n  After compression -> direction:")
        print(f"    UP:   {(compressed['post_direction'] == 'UP').sum()}")
        print(f"    DOWN: {(compressed['post_direction'] == 'DOWN').sum()}")
    return results


# ============================================================
# 2. Volume Pattern
# ============================================================
def analyze_volume_pattern(merged):
    print("\n" + "=" * 90)
    print("2. VOLUME PATTERN ANALYSIS")
    print("   イベント当日の出来高 vs 20日平均")
    print("=" * 90)

    results = []
    for ev in REGULATORY_EVENTS:
        ev_date = pd.to_datetime(ev['date'])
        idx = merged['date'].searchsorted(ev_date)
        if idx >= len(merged):
            continue
        closest = merged.iloc[idx]
        if abs((closest['date'] - ev_date).days) > 3:
            if idx > 0:
                closest = merged.iloc[idx - 1]
            if abs((closest['date'] - ev_date).days) > 3:
                continue

        ev_idx = merged.index[merged['date'] == closest['date']][0]

        # 20d average before event
        avg20_start = max(0, ev_idx - 20)
        window20 = merged.iloc[avg20_start:ev_idx]
        if len(window20) < 10:
            continue

        avg20_eth_vol = window20['volume_eth'].mean()
        avg20_btc_vol = window20['volume_btc'].mean()

        event_eth_vol = merged.iloc[ev_idx]['volume_eth']
        event_btc_vol = merged.iloc[ev_idx]['volume_btc']

        eth_vol_ratio = event_eth_vol / avg20_eth_vol if avg20_eth_vol > 0 else np.nan
        btc_vol_ratio = event_btc_vol / avg20_btc_vol if avg20_btc_vol > 0 else np.nan

        # Normal volume ratio (ETH/BTC) in 20d window vs event day
        avg20_ratio = (window20['volume_eth'] / window20['volume_btc']).mean()
        event_ratio = event_eth_vol / event_btc_vol if event_btc_vol > 0 else np.nan

        # Post-5d ratio change
        ratio_at = merged.iloc[ev_idx]['ratio']
        ratio_post5 = merged.iloc[min(ev_idx + 5, len(merged) - 1)]['ratio']
        ratio_chg_5d = (ratio_post5 - ratio_at) / ratio_at * 100

        r = {
            'event': ev['name'], 'date': ev['date'], 'category': ev['category'],
            'eth_vol_ratio': eth_vol_ratio, 'btc_vol_ratio': btc_vol_ratio,
            'avg20_eth_btc_vol_ratio': avg20_ratio, 'event_eth_btc_vol_ratio': event_ratio,
            'ratio_chg_5d': ratio_chg_5d,
            'event_eth_vol': event_eth_vol, 'event_btc_vol': event_btc_vol
        }
        results.append(r)

        print(f"\n  {ev['name']} ({ev['date']}) [{ev['category']}]")
        print(f"    ETH vol ratio (event/20d avg): {eth_vol_ratio:.2f}x")
        print(f"    BTC vol ratio (event/20d avg): {btc_vol_ratio:.2f}x")
        print(f"    ETH/BTC volume ratio: avg20={avg20_ratio:.2f}, event={event_ratio:.2f}")
        print(f"    Ratio 5d change: {ratio_chg_5d:+.4f}%")

    if not results:
        print("  No events with sufficient data.")
        return []

    df_r = pd.DataFrame(results)

    print(f"\n  --- SUMMARY ---")
    print(f"  Events analyzed: {len(df_r)}")
    print(f"  Avg ETH vol ratio: {df_r['eth_vol_ratio'].mean():.2f}x")
    print(f"  Avg BTC vol ratio: {df_r['btc_vol_ratio'].mean():.2f}x")
    print(f"  ETH volume increase > BTC: {(df_r['eth_vol_ratio'] > df_r['btc_vol_ratio']).sum()}/{len(df_r)}")

    # Correlation: high volume -> large ratio change?
    high_vol = df_r[df_r['eth_vol_ratio'] > df_r['eth_vol_ratio'].median()]
    low_vol = df_r[df_r['eth_vol_ratio'] <= df_r['eth_vol_ratio'].median()]
    print(f"\n  High ETH volume events (>{df_r['eth_vol_ratio'].median():.2f}x):")
    print(f"    Avg |ratio 5d change|: {high_vol['ratio_chg_5d'].abs().mean():.4f}%")
    print(f"  Low ETH volume events (<={df_r['eth_vol_ratio'].median():.2f}x):")
    print(f"    Avg |ratio 5d change|: {low_vol['ratio_chg_5d'].abs().mean():.4f}%")

    return results


# ============================================================
# 3. Pre-event Positioning Signals
# ============================================================
def analyze_positioning_signals(merged):
    print("\n" + "=" * 90)
    print("3. PRE-EVENT POSITIONING SIGNALS")
    print("   イベント前のRSI, BB幅, 3dトレンド → イベント後ratio方向の予測力")
    print("=" * 90)

    # Pre-compute indicators on merged daily
    merged['rsi14'] = calc_rsi(merged['ratio'], 14)
    merged['bb_width'] = calc_bollinger_width(merged['ratio'], 20)

    results = []
    for ev in REGULATORY_EVENTS:
        ev_date = pd.to_datetime(ev['date'])
        idx = merged['date'].searchsorted(ev_date)
        if idx >= len(merged):
            continue
        closest = merged.iloc[idx]
        if abs((closest['date'] - ev_date).days) > 3:
            if idx > 0:
                closest = merged.iloc[idx - 1]
            if abs((closest['date'] - ev_date).days) > 3:
                continue

        ev_idx = merged.index[merged['date'] == closest['date']][0]
        if ev_idx < 25:
            continue

        # Pre-3d ratio trend
        ratio_3d_ago = merged.iloc[ev_idx - 3]['ratio']
        ratio_at = merged.iloc[ev_idx]['ratio']
        if ratio_3d_ago == 0:
            continue
        pre3d_trend_pct = (ratio_at - ratio_3d_ago) / ratio_3d_ago * 100
        if pre3d_trend_pct > 0.3:
            pre_trend = "UP"
        elif pre3d_trend_pct < -0.3:
            pre_trend = "DOWN"
        else:
            pre_trend = "RANGE"

        # RSI at event
        rsi = merged.iloc[ev_idx]['rsi14']
        if pd.isna(rsi):
            continue

        # BB width at event
        bb = merged.iloc[ev_idx]['bb_width']
        if pd.isna(bb):
            continue

        # Post-5d direction
        post5_idx = min(ev_idx + 5, len(merged) - 1)
        ratio_post5 = merged.iloc[post5_idx]['ratio']
        post_chg = (ratio_post5 - ratio_at) / ratio_at * 100
        post_dir = "UP" if post_chg > 0 else "DOWN"

        r = {
            'event': ev['name'], 'date': ev['date'], 'category': ev['category'],
            'pre3d_trend': pre_trend, 'pre3d_pct': pre3d_trend_pct,
            'rsi14': rsi, 'bb_width': bb,
            'post_5d_dir': post_dir, 'post_5d_pct': post_chg
        }
        results.append(r)

        print(f"\n  {ev['name']} ({ev['date']}) [{ev['category']}]")
        print(f"    Pre-3d trend: {pre_trend} ({pre3d_trend_pct:+.4f}%)")
        print(f"    RSI(14):      {rsi:.1f}")
        print(f"    BB width:     {bb:.4f}%")
        print(f"    Post-5d:      {post_dir} ({post_chg:+.4f}%)")

    if not results:
        print("  No events with sufficient data.")
        return []

    df_r = pd.DataFrame(results)

    print(f"\n  --- PREDICTIVE POWER ANALYSIS ---")

    # Pre-3d trend -> post direction
    print(f"\n  [Pre-3d trend -> Post-5d direction]")
    for trend in ['UP', 'DOWN', 'RANGE']:
        subset = df_r[df_r['pre3d_trend'] == trend]
        if len(subset) > 0:
            up_rate = (subset['post_5d_dir'] == 'UP').mean() * 100
            print(f"    Pre-3d {trend:6s}: Post UP = {up_rate:.0f}% (n={len(subset)})")

    # RSI levels -> post direction
    print(f"\n  [RSI level -> Post-5d direction]")
    rsi_low = df_r[df_r['rsi14'] < 40]
    rsi_mid = df_r[(df_r['rsi14'] >= 40) & (df_r['rsi14'] <= 60)]
    rsi_high = df_r[df_r['rsi14'] > 60]
    for label, subset in [('<40 oversold', rsi_low), ('40-60 neutral', rsi_mid), ('>60 overbought', rsi_high)]:
        if len(subset) > 0:
            up_rate = (subset['post_5d_dir'] == 'UP').mean() * 100
            print(f"    RSI {label:20s}: Post UP = {up_rate:.0f}% (n={len(subset)})")

    # BB width -> post volatility
    print(f"\n  [BB width -> Post-5d |change|]")
    if len(df_r) >= 4:
        bb_median = df_r['bb_width'].median()
        tight_bb = df_r[df_r['bb_width'] <= bb_median]
        wide_bb = df_r[df_r['bb_width'] > bb_median]
        print(f"    Tight BB (<={bb_median:.4f}%): Avg |change| = {tight_bb['post_5d_pct'].abs().mean():.4f}% (n={len(tight_bb)})")
        print(f"    Wide BB (>{bb_median:.4f}%):  Avg |change| = {wide_bb['post_5d_pct'].abs().mean():.4f}% (n={len(wide_bb)})")

    return results


# ============================================================
# 4. Event Type Analysis
# ============================================================
def analyze_event_types(vol_results, vol_results_list):
    print("\n" + "=" * 90)
    print("4. EVENT TYPE ANALYSIS")
    print("   イベントタイプ別: SEC系 / 立法系 / 行政系")
    print("=" * 90)

    if not vol_results_list:
        print("  No data available.")
        return

    df = pd.DataFrame(vol_results_list)

    for cat in ['SEC', 'LEGISLATIVE', 'EXECUTIVE']:
        subset = df[df['category'] == cat]
        if len(subset) == 0:
            continue

        print(f"\n  [{cat}] ({len(subset)} events)")
        print(f"  {'Event':<40s} {'Date':<12s} {'Post-5d':>10s} {'Direction':>10s}")
        print(f"  {'-'*40} {'-'*12} {'-'*10} {'-'*10}")
        for _, row in subset.iterrows():
            print(f"  {row['event']:<40s} {row['date']:<12s} {row['post_5d_pct']:>+9.4f}% {row['post_direction']:>10s}")

        avg_chg = subset['post_5d_pct'].mean()
        win_rate = (subset['post_5d_pct'] > 0).mean() * 100
        max_up = subset['post_5d_pct'].max()
        max_down = subset['post_5d_pct'].min()

        print(f"  ---")
        print(f"  Avg ratio change (post-5d): {avg_chg:+.4f}%")
        print(f"  Win rate (ratio UP):        {win_rate:.0f}%")
        print(f"  Max rise:                   {max_up:+.4f}%")
        print(f"  Max fall:                   {max_down:+.4f}%")

    # Cross-type comparison
    print(f"\n  --- CROSS-TYPE COMPARISON ---")
    for cat in ['SEC', 'LEGISLATIVE', 'EXECUTIVE']:
        subset = df[df['category'] == cat]
        if len(subset) > 0:
            print(f"  {cat:12s}: avg={subset['post_5d_pct'].mean():+.4f}%, "
                  f"vol_ratio={subset['vol_ratio'].mean():.2f}x, "
                  f"compression={subset['compression'].mean()*100:.0f}%")


# ============================================================
# 5. 4h Intraday Pattern on Event Days
# ============================================================
def analyze_4h_intraday(btc4, eth4, merged):
    print("\n" + "=" * 90)
    print("5. 4H INTRADAY PATTERN ON EVENT DAYS")
    print("   4h足でのイベント当日時間帯別ratio変動")
    print("=" * 90)

    # Build 4h ratio series
    btc4 = btc4.rename(columns={'open': 'btc_open', 'high': 'btc_high', 'low': 'btc_low',
                                 'close': 'btc_close', 'volume': 'btc_volume'})
    eth4 = eth4.rename(columns={'open': 'eth_open', 'high': 'eth_high', 'low': 'eth_low',
                                 'close': 'eth_close', 'volume': 'eth_volume'})

    # Merge 4h data
    btc4['dt_merge'] = btc4['datetime'].dt.strftime('%Y-%m-%d %H:%M')
    eth4['dt_merge'] = eth4['datetime'].dt.strftime('%Y-%m-%d %H:%M')
    m4 = pd.merge(btc4[['dt_merge', 'btc_close', 'btc_volume']],
                   eth4[['dt_merge', 'eth_close', 'eth_volume']],
                   on='dt_merge', how='inner')
    m4['ratio'] = m4['eth_close'] / m4['btc_close']
    m4['datetime'] = pd.to_datetime(m4['dt_merge'], utc=True)
    m4['hour'] = m4['datetime'].dt.hour
    m4['date'] = m4['datetime'].dt.date

    # Time windows
    time_windows = [
        ('00-04 UTC', 0, 4),
        ('04-08 UTC', 4, 8),
        ('08-12 UTC', 8, 12),
        ('12-16 UTC', 12, 16),
        ('16-20 UTC', 16, 20),
        ('20-24 UTC', 20, 24),
    ]

    for ev in REGULATORY_EVENTS:
        ev_date = pd.to_datetime(ev['date']).date()

        day_data = m4[m4['date'] == ev_date]
        if len(day_data) == 0:
            # Try adjacent day
            for offset in [-1, 1, -2, 2]:
                alt_date = ev_date + timedelta(days=offset)
                day_data = m4[m4['date'] == alt_date]
                if len(day_data) > 0:
                    break

        if len(day_data) == 0:
            continue

        print(f"\n  {ev['name']} ({ev['date']}) [{ev['category']}]")

        # Compute ratio change per 4h candle
        day_data = day_data.sort_values('datetime').copy()
        day_data['ratio_chg'] = day_data['ratio'].pct_change() * 100

        # Max move window
        max_chg = 0
        max_window = "N/A"
        max_abs_chg = 0

        for win_name, h_start, h_end in time_windows:
            win_data = day_data[(day_data['hour'] >= h_start) & (day_data['hour'] < h_end)]
            if len(win_data) > 0:
                win_chg = win_data['ratio_chg'].sum()
                print(f"    {win_name}: ratio change = {win_chg:+.4f}%", end="")
                if abs(win_chg) > abs(max_abs_chg):
                    max_abs_chg = win_chg
                    max_window = win_name
                # Highlight US market time
                if h_start == 12:
                    print("  <-- US pre-market / open")
                elif h_start == 16:
                    print("  <-- US active trading")
                else:
                    print()

        print(f"    >>> Max move: {max_window} ({max_abs_chg:+.4f}%)")

        # US market focus (13:30-16:00 UTC = 12-16 window)
        us_windows = day_data[(day_data['hour'] >= 12) & (day_data['hour'] < 20)]
        if len(us_windows) >= 2:
            us_start = us_windows.iloc[0]['ratio']
            us_end = us_windows.iloc[-1]['ratio']
            us_chg = (us_end - us_start) / us_start * 100
            pre_us = day_data[day_data['hour'] < 12]
            if len(pre_us) >= 2:
                pre_start = pre_us.iloc[0]['ratio']
                pre_end = pre_us.iloc[-1]['ratio']
                pre_chg = (pre_end - pre_start) / pre_start * 100
                print(f"    Pre-US (00-12 UTC): {pre_chg:+.4f}%")
                print(f"    US hours (12-20 UTC): {us_chg:+.4f}%")

    # Aggregate: which time window sees most activity?
    print(f"\n  --- AGGREGATE: Most active time window across all events ---")
    window_stats = {w[0]: [] for w in time_windows}

    for ev in REGULATORY_EVENTS:
        ev_date = pd.to_datetime(ev['date']).date()
        day_data = m4[m4['date'] == ev_date]
        if len(day_data) == 0:
            for offset in [-1, 1, -2, 2]:
                alt_date = ev_date + timedelta(days=offset)
                day_data = m4[m4['date'] == alt_date]
                if len(day_data) > 0:
                    break
        if len(day_data) == 0:
            continue

        day_data = day_data.sort_values('datetime').copy()
        day_data['ratio_chg'] = day_data['ratio'].pct_change() * 100

        for win_name, h_start, h_end in time_windows:
            win_data = day_data[(day_data['hour'] >= h_start) & (day_data['hour'] < h_end)]
            if len(win_data) > 0:
                window_stats[win_name].append(win_data['ratio_chg'].sum())

    print(f"  {'Window':<12s} {'Avg |change|':>14s} {'Avg change':>12s} {'Events':>8s}")
    for win_name, changes in window_stats.items():
        if changes:
            avg_abs = np.mean([abs(c) for c in changes])
            avg_chg = np.mean(changes)
            print(f"  {win_name:<12s} {avg_abs:>13.4f}% {avg_chg:>+11.4f}% {len(changes):>8d}")


# ============================================================
# MAIN
# ============================================================
def main():
    print("Loading data...")
    btc4, eth4, merged = load_data()
    print(f"  BTC 4h: {len(btc4)} rows ({btc4['datetime'].min()} to {btc4['datetime'].max()})")
    print(f"  ETH 4h: {len(eth4)} rows ({eth4['datetime'].min()} to {eth4['datetime'].max()})")
    print(f"  Merged daily: {len(merged)} rows ({merged['date'].min().date()} to {merged['date'].max().date()})")
    print(f"  Ratio range: {merged['ratio'].min():.6f} to {merged['ratio'].max():.6f}")
    print()

    # 1. Volatility Pattern
    vol_results = analyze_volatility_pattern(merged)

    # 2. Volume Pattern
    vol_pattern_results = analyze_volume_pattern(merged)

    # 3. Positioning Signals
    positioning_results = analyze_positioning_signals(merged)

    # 4. Event Type
    analyze_event_types(None, vol_results)

    # 5. 4h Intraday
    analyze_4h_intraday(btc4, eth4, merged)

    print("\n" + "=" * 90)
    print("ANALYSIS COMPLETE")
    print("=" * 90)


if __name__ == '__main__':
    main()
