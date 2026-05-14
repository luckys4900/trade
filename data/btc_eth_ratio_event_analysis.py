"""
BTC/ETH Ratio - Regulatory Event Phase Analysis
イベント前後フェーズごとのレシオ変動を詳細分析
"""

import pandas as pd
import numpy as np
from scipy import stats
import json
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 1. データ読み込み
# ============================================================
print("=" * 80)
print("BTC/ETH Ratio - 規制イベント フェーズ別分析")
print("=" * 80)

# BTC 4h data
btc_4h = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/btc_price_4h_cache.csv')
btc_4h['datetime'] = pd.to_datetime(btc_4h['datetime'], utc=True)
btc_4h['datetime'] = btc_4h['datetime'].dt.tz_localize(None)  # tz-naiveに統一
btc_4h = btc_4h.set_index('datetime').sort_index()

# ETH 4h data
eth_4h = pd.read_csv('C:/Users/user/Desktop/cursor/trade/data/ETH_USDT_4h_730d.csv')
eth_4h['datetime'] = pd.to_datetime(eth_4h['datetime'], utc=True)
eth_4h['datetime'] = eth_4h['datetime'].dt.tz_localize(None)
eth_4h = eth_4h.set_index('datetime').sort_index()

print(f"\nBTC 4h: {btc_4h.index[0]} ~ {btc_4h.index[-1]} ({len(btc_4h)} rows)")
print(f"ETH 4h: {eth_4h.index[0]} ~ {eth_4h.index[-1]} ({len(eth_4h)} rows)")

# ============================================================
# 2. 追加データ取得 (ccxtで最新ETH 4hを取得)
# ============================================================
try:
    import ccxt
    exchange = ccxt.binance({'enableRateLimit': True})

    # 最終日から現在まで
    eth_last = eth_4h.index[-1]
    since_ms = int(eth_last.timestamp() * 1000) + 1  # 1ms after last

    print(f"\nccxtでETH 4hデータを {eth_last} から取得中...")

    new_eth_candles = []
    all_ohlcv = []
    current_since = since_ms
    while True:
        ohlcv = exchange.fetch_ohlcv('ETH/USDT', '4h', since=current_since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        current_since = ohlcv[-1][0] + 1
        if len(ohlcv) < 1000:
            break

    if all_ohlcv:
        new_df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        new_df['datetime'] = pd.to_datetime(new_df['timestamp'], unit='ms', utc=True)
        new_df['datetime'] = new_df['datetime'].dt.tz_localize(None)
        new_df = new_df.set_index('datetime').sort_index()
        new_df = new_df[['open', 'high', 'low', 'close', 'volume']]
        # 結合
        eth_4h = pd.concat([eth_4h[['open', 'high', 'low', 'close', 'volume']], new_df])
        eth_4h = eth_4h[~eth_4h.index.duplicated(keep='last')]
        eth_4h = eth_4h.sort_index()
        print(f"  → {len(new_df)} 追加行取得。ETH終了: {eth_4h.index[-1]}")
    else:
        print("  → 追加データなし")
except Exception as e:
    print(f"ccxtエラー（既存データのみ使用）: {e}")

# ============================================================
# 3. 日足集約
# ============================================================
def to_daily(df_4h):
    """4h → 日足 (UTC日付で集約)"""
    df = df_4h.copy()
    df['date'] = df.index.date
    daily = df.groupby('date').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        volume=('volume', 'sum')
    )
    daily.index = pd.to_datetime(daily.index)
    return daily

btc_daily = to_daily(btc_4h)
eth_daily = to_daily(eth_4h)

# BTC/ETH Ratio (日足close基準)
common_idx = btc_daily.index.intersection(eth_daily.index)
btc_d = btc_daily.loc[common_idx]
eth_d = eth_daily.loc[common_idx]
ratio_daily = (btc_d['close'] / eth_d['close'])
ratio_daily.name = 'ratio'
ratio_df = pd.DataFrame({
    'btc_close': btc_d['close'],
    'eth_close': eth_d['close'],
    'ratio': ratio_daily
}, index=common_idx)

print(f"\n共通期間(日足): {ratio_df.index[0].date()} ~ {ratio_df.index[-1].date()} ({len(ratio_df)} days)")

# ============================================================
# 4. 4h足でBTC/ETH ratio
# ============================================================
btc_4h_aligned = btc_4h[['open', 'high', 'low', 'close']].rename(
    columns=lambda x: f'btc_{x}')
eth_4h_aligned = eth_4h[['open', 'high', 'low', 'close']].rename(
    columns=lambda x: f'eth_{x}')
# 共通インデックス
common_4h = btc_4h_aligned.index.intersection(eth_4h_aligned.index)
ratio_4h = pd.DataFrame(index=common_4h)
ratio_4h['btc_close'] = btc_4h_aligned.loc[common_4h, 'btc_close']
ratio_4h['eth_close'] = eth_4h_aligned.loc[common_4h, 'eth_close']
ratio_4h['btc_high'] = btc_4h_aligned.loc[common_4h, 'btc_high']
ratio_4h['btc_low'] = btc_4h_aligned.loc[common_4h, 'btc_low']
ratio_4h['eth_high'] = eth_4h_aligned.loc[common_4h, 'eth_high']
ratio_4h['eth_low'] = eth_4h_aligned.loc[common_4h, 'eth_low']
ratio_4h['ratio'] = ratio_4h['btc_close'] / ratio_4h['eth_close']

print(f"共通期間(4h): {ratio_4h.index[0]} ~ {ratio_4h.index[-1]} ({len(ratio_4h)} rows)")

# ============================================================
# 5. イベントリスト
# ============================================================
events = [
    ('FIT21 House Pass', '2024-05-22'),
    ('ETH ETF Approval', '2024-05-23'),
    ('SAB121 Override', '2024-05-09'),
    ('Trump Wins', '2024-11-06'),
    ('Gensler Resigns', '2024-11-21'),
    ('Gensler Steps Down', '2025-01-20'),
    ('Trump Crypto EO', '2025-03-07'),
    ('SAB121 Repealed', '2025-04-01'),
]

# ============================================================
# 6. フェーズ別レシオ変化計算
# ============================================================
phase_labels = [
    'Pre-5d', 'Pre-3d', 'Pre-1d', 'Event Day',
    'Post-1d', 'Post-3d', 'Post-5d', 'Post-10d', 'Post-20d', 'Post-30d'
]

def get_ratio_on_date(date_str, ratio_series):
    """指定日のratio取得（祝日等は直近を使用）"""
    target = pd.Timestamp(date_str)
    # 営業日（暗号は毎日あるが、データ不足の場合）
    if target in ratio_series.index:
        return ratio_series.loc[target]
    # 直近を探す
    mask = ratio_series.index <= target
    if mask.any():
        return ratio_series.loc[mask].iloc[-1]
    return np.nan

def get_ratio_shifted(date_str, days, ratio_series):
    """指定日からdays日後（前）のratio"""
    target = pd.Timestamp(date_str) + pd.Timedelta(days=days)
    return get_ratio_on_date(target.strftime('%Y-%m-%d'), ratio_series)

# 結果格納
all_phase_results = []  # list of dict
per_event_details = {}  # event_name -> {phase: change_pct}

for ev_name, ev_date in events:
    ev_dt = pd.Timestamp(ev_date)
    detail = {}

    # Pre-5d: 5日前 → 当日
    for phase, offset_start, offset_end in [
        ('Pre-5d', -5, 0),
        ('Pre-3d', -3, 0),
        ('Pre-1d', -1, 0),
    ]:
        r_start = get_ratio_shifted(ev_date, offset_start, ratio_df['ratio'])
        r_end = get_ratio_shifted(ev_date, offset_end, ratio_df['ratio'])
        pct = (r_end / r_start - 1) * 100 if r_start > 0 and not np.isnan(r_start) and not np.isnan(r_end) else np.nan
        detail[phase] = pct

    # Event Day (4h内の最大変動)
    day_data = ratio_4h.loc[
        (ratio_4h.index.date >= ev_dt.date()) &
        (ratio_4h.index.date <= ev_dt.date())
    ]
    if len(day_data) > 0:
        # ratio range in 4h candles
        ratio_highs = day_data['btc_high'] / day_data['eth_low']  # BTC high / ETH low = ratio max
        ratio_lows = day_data['btc_low'] / day_data['eth_high']  # BTC low / ETH high = ratio min
        ratio_range_pct = (ratio_highs.max() / ratio_lows.min() - 1) * 100
        detail['Event Day'] = ratio_range_pct
    else:
        detail['Event Day'] = np.nan

    # Post phases
    for phase, offset in [
        ('Post-1d', 1),
        ('Post-3d', 3),
        ('Post-5d', 5),
        ('Post-10d', 10),
        ('Post-20d', 20),
        ('Post-30d', 30),
    ]:
        r_start = get_ratio_shifted(ev_date, 0, ratio_df['ratio'])
        r_end = get_ratio_shifted(ev_date, offset, ratio_df['ratio'])
        pct = (r_end / r_start - 1) * 100 if r_start > 0 and not np.isnan(r_start) and not np.isnan(r_end) else np.nan
        detail[phase] = pct

    per_event_details[ev_name] = detail

    for phase in phase_labels:
        all_phase_results.append({
            'event': ev_name,
            'date': ev_date,
            'phase': phase,
            'change_pct': detail[phase]
        })

# ============================================================
# 7. BTC/ETH 個別変化（ドライバー分析）
# ============================================================
per_event_btc = {}
per_event_eth = {}

for ev_name, ev_date in events:
    btc_detail = {}
    eth_detail = {}

    for phase, offset_start, offset_end in [
        ('Pre-5d', -5, 0), ('Pre-3d', -3, 0), ('Pre-1d', -1, 0),
    ]:
        for asset, series, store in [('btc', ratio_df['btc_close'], btc_detail), ('eth', ratio_df['eth_close'], eth_detail)]:
            r_start = get_ratio_shifted(ev_date, offset_start, series)
            r_end = get_ratio_shifted(ev_date, offset_end, series)
            pct = (r_end / r_start - 1) * 100 if r_start > 0 and not np.isnan(r_start) and not np.isnan(r_end) else np.nan
            store[phase] = pct

    for phase, offset in [
        ('Post-1d', 1), ('Post-3d', 3), ('Post-5d', 5),
        ('Post-10d', 10), ('Post-20d', 20), ('Post-30d', 30),
    ]:
        for asset, series, store in [('btc', ratio_df['btc_close'], btc_detail), ('eth', ratio_df['eth_close'], eth_detail)]:
            r_start = get_ratio_shifted(ev_date, 0, series)
            r_end = get_ratio_shifted(ev_date, offset, series)
            pct = (r_end / r_start - 1) * 100 if r_start > 0 and not np.isnan(r_start) and not np.isnan(r_end) else np.nan
            store[phase] = pct

    # Event Day用
    btc_detail['Event Day'] = np.nan  # 後で計算
    eth_detail['Event Day'] = np.nan

    per_event_btc[ev_name] = btc_detail
    per_event_eth[ev_name] = eth_detail

# ============================================================
# 8. 統計分析
# ============================================================
results_df = pd.DataFrame(all_phase_results)

print("\n" + "=" * 80)
print("【結果1】イベント別 × フェーズ別 レシオ変化（%）")
print("=" * 80)

# ピボットテーブル
pivot = results_df.pivot(index='event', columns='phase', values='change_pct')
pivot = pivot[phase_labels]  # 順序固定

# 表示
col_widths = {p: 9 for p in phase_labels}
print(f"{'イベント':<22}", end='')
for p in phase_labels:
    print(f"{p:>10}", end='')
print()
print("-" * (22 + 10 * len(phase_labels)))

for ev_name, _ in events:
    print(f"{ev_name:<22}", end='')
    for p in phase_labels:
        val = per_event_details[ev_name][p]
        if np.isnan(val):
            print(f"{'N/A':>10}", end='')
        else:
            sign = '+' if val >= 0 else ''
            print(f"{sign}{val:>8.2f}", end='')
    print()

# ============================================================
# 平均・勝率・t検定
# ============================================================
print("\n" + "=" * 80)
print("【結果2】フェーズ別 統計サマリー")
print("=" * 80)
print(f"{'フェーズ':<12} {'平均%':>8} {'中央値%':>8} {'勝率':>7} {'サンプル':>6} {'t値':>8} {'p値':>8} {'有意':>5}")
print("-" * 70)

phase_stats = {}
for phase in phase_labels:
    vals = [per_event_details[ev][phase] for ev in [e[0] for e in events]]
    vals = [v for v in vals if not np.isnan(v)]
    if len(vals) == 0:
        continue
    mean = np.mean(vals)
    median = np.median(vals)
    win_rate = sum(1 for v in vals if v > 0) / len(vals)
    n = len(vals)
    if n >= 2:
        t_stat, p_val = stats.ttest_1samp(vals, 0)
        significant = '*' if p_val < 0.10 else '**' if p_val < 0.05 else '***' if p_val < 0.01 else ''
        # 片側検定（平均>0の方向）
        p_one_sided = p_val / 2 if mean > 0 else 1 - p_val / 2
    else:
        t_stat, p_val, p_one_sided, significant = np.nan, np.nan, np.nan, ''

    phase_stats[phase] = {
        'mean': mean, 'median': median, 'win_rate': win_rate,
        'n': n, 't_stat': t_stat, 'p_val': p_val, 'p_one_sided': p_one_sided,
        'significant': significant
    }
    sign_mean = '+' if mean >= 0 else ''
    sign_med = '+' if median >= 0 else ''
    print(f"{phase:<12} {sign_mean}{mean:>7.3f} {sign_med}{median:>7.3f} {win_rate:>6.1%} {n:>5} {t_stat:>8.3f} {p_val:>8.4f} {significant:>5}")

# ============================================================
# 9. ドライバー分析（BTC vs ETH）
# ============================================================
print("\n" + "=" * 80)
print("【結果3】レシオ変化のドライバー分析（BTC変化 vs ETH変化）")
print("=" * 80)
print(f"{'フェーズ':<12} {'BTC平均%':>10} {'ETH平均%':>10} {'BTC勝率':>8} {'ETH勝率':>8} {'ドライバー':>12}")
print("-" * 65)

driver_analysis = {}
for phase in ['Pre-5d', 'Pre-3d', 'Pre-1d', 'Post-1d', 'Post-3d', 'Post-5d', 'Post-10d', 'Post-20d', 'Post-30d']:
    btc_vals = [per_event_btc[ev].get(phase, np.nan) for ev in [e[0] for e in events]]
    eth_vals = [per_event_eth[ev].get(phase, np.nan) for ev in [e[0] for e in events]]
    btc_vals = [v for v in btc_vals if not np.isnan(v)]
    eth_vals = [v for v in eth_vals if not np.isnan(v)]

    btc_mean = np.mean(btc_vals) if btc_vals else np.nan
    eth_mean = np.mean(eth_vals) if eth_vals else np.nan
    btc_wr = sum(1 for v in btc_vals if v > 0) / len(btc_vals) if btc_vals else np.nan
    eth_wr = sum(1 for v in eth_vals if v > 0) / len(eth_vals) if eth_vals else np.nan

    # レシオ上昇 = BTC上昇 > ETH上昇 (またはETH下落 > BTC下落)
    ratio_mean = phase_stats.get(phase, {}).get('mean', np.nan)
    if not np.isnan(ratio_mean):
        if ratio_mean > 0:
            driver = "BTC強" if btc_mean > abs(eth_mean) else "ETH弱"
        else:
            driver = "ETH強" if abs(eth_mean) > abs(btc_mean) else "BTC弱"
    else:
        driver = "N/A"

    driver_analysis[phase] = {
        'btc_mean': btc_mean, 'eth_mean': eth_mean,
        'driver': driver
    }

    sign_btc = '+' if btc_mean >= 0 else ''
    sign_eth = '+' if eth_mean >= 0 else ''
    print(f"{phase:<12} {sign_btc}{btc_mean:>9.2f} {sign_eth}{eth_mean:>9.2f} {btc_wr:>7.1%} {eth_wr:>7.1%} {driver:>12}")

# ============================================================
# 10. 4h足 イベント当日の時間内パターン分析
# ============================================================
print("\n" + "=" * 80)
print("【結果4】イベント当日 4h足での時間内変動パターン")
print("=" * 80)

for ev_name, ev_date in events:
    ev_dt = pd.Timestamp(ev_date)
    day_data = ratio_4h.loc[
        (ratio_4h.index.date == ev_dt.date())
    ].copy()
    if len(day_data) == 0:
        # 前後1日拡大
        day_data = ratio_4h.loc[
            (ratio_4h.index.date >= (ev_dt - pd.Timedelta(days=1)).date()) &
            (ratio_4h.index.date <= (ev_dt + pd.Timedelta(days=1)).date())
        ]

    if len(day_data) == 0:
        print(f"\n{ev_name} ({ev_date}): データなし")
        continue

    day_data = day_data.copy()
    day_data['ratio'] = day_data['btc_close'] / day_data['eth_close']
    start_ratio = day_data['ratio'].iloc[0]

    # ピーク到達時間
    max_idx = day_data['ratio'].idxmax()
    min_idx = day_data['ratio'].idxmin()

    # 終値ベースの最高到達
    max_ratio = day_data['ratio'].max()
    min_ratio = day_data['ratio'].min()
    end_ratio = day_data['ratio'].iloc[-1]

    # 最大変動（high/lowベース）
    ratio_highs = day_data['btc_high'] / day_data['eth_low']
    ratio_lows = day_data['btc_low'] / day_data['eth_high']

    print(f"\n{ev_name} ({ev_date}):")
    print(f"  開始ratio: {start_ratio:.4f}  終了ratio: {end_ratio:.4f}  変化: {(end_ratio/start_ratio-1)*100:+.3f}%")
    print(f"  4h内最高: {max_ratio:.4f} ({(max_ratio/start_ratio-1)*100:+.3f}%) @ {max_idx}")
    print(f"  4h内最安: {min_ratio:.4f} ({(min_ratio/start_ratio-1)*100:+.3f}%) @ {min_idx}")
    print(f"  瞬間最大ratio: {ratio_highs.max():.4f}  瞬間最小ratio: {ratio_lows.min():.4f}")
    print(f"  瞬間レンジ: {(ratio_highs.max()/ratio_lows.min()-1)*100:.3f}%")

    # 何時間目にピーク？
    hours_to_max = (max_idx - day_data.index[0]).total_seconds() / 3600
    hours_to_min = (min_idx - day_data.index[0]).total_seconds() / 3600
    print(f"  最高到達: {hours_to_max:.0f}h後  最安到達: {hours_to_min:.0f}h後")

# ============================================================
# 11. 事前トレンドと事後反応の関係
# ============================================================
print("\n" + "=" * 80)
print("【結果5】事前トレンド（Pre-5d）と事後反応（Post-5d, Post-10d）の関係")
print("=" * 80)

pre_trends = []
post_reactions = []
for ev_name, ev_date in events:
    pre = per_event_details[ev_name]['Pre-5d']
    post5 = per_event_details[ev_name]['Post-5d']
    post10 = per_event_details[ev_name]['Post-10d']
    pre_trends.append(pre)
    post_reactions.append((post5, post10))
    direction = "上昇" if pre > 0 else "下落"
    print(f"{ev_name:<22} 事前5d: {pre:+.3f}% ({direction}) → 事後5d: {post5:+.3f}%  事後10d: {post10:+.3f}%")

# 相関分析
pre_valid = [v for v in pre_trends if not np.isnan(v)]
post5_valid = [v for v, _ in post_reactions if not np.isnan(v)]
post10_valid = [v for _, v in post_reactions if not np.isnan(v)]

# ペアで相関
pairs_5d = [(pre_trends[i], post_reactions[i][0]) for i in range(len(events))
            if not np.isnan(pre_trends[i]) and not np.isnan(post_reactions[i][0])]
pairs_10d = [(pre_trends[i], post_reactions[i][1]) for i in range(len(events))
             if not np.isnan(pre_trends[i]) and not np.isnan(post_reactions[i][1])]

if len(pairs_5d) >= 3:
    pre_arr = np.array([p[0] for p in pairs_5d])
    post5_arr = np.array([p[1] for p in pairs_5d])
    corr_5d, p_corr_5d = stats.pearsonr(pre_arr, post5_arr)
    print(f"\nPre-5d と Post-5d の相関: r={corr_5d:.3f}, p={p_corr_5d:.4f}")

if len(pairs_10d) >= 3:
    pre_arr = np.array([p[0] for p in pairs_10d])
    post10_arr = np.array([p[1] for p in pairs_10d])
    corr_10d, p_corr_10d = stats.pearsonr(pre_arr, post10_arr)
    print(f"Pre-5d と Post-10d の相関: r={corr_10d:.3f}, p={p_corr_10d:.4f}")

# 事前上昇 vs 事前下落で事後反応が異なるか
up_indices = [i for i in range(len(events)) if pre_trends[i] > 0 and not np.isnan(post_reactions[i][0])]
dn_indices = [i for i in range(len(events)) if pre_trends[i] <= 0 and not np.isnan(post_reactions[i][0])]

if up_indices and dn_indices:
    up_post5 = [post_reactions[i][0] for i in up_indices]
    dn_post5 = [post_reactions[i][0] for i in dn_indices]
    print(f"\n事前上昇グループ ({len(up_post5)}件) Post-5d平均: {np.mean(up_post5):+.3f}%")
    print(f"事前下落グループ ({len(dn_post5)}件) Post-5d平均: {np.mean(dn_post5):+.3f}%")
    if len(up_post5) >= 2 and len(dn_post5) >= 2:
        t_diff, p_diff = stats.ttest_ind(up_post5, dn_post5)
        print(f"  差のt検定: t={t_diff:.3f}, p={p_diff:.4f}")

# ============================================================
# 12. フェーズ間相関行列
# ============================================================
print("\n" + "=" * 80)
print("【結果6】フェーズ間相関行列（Pre vs Post）")
print("=" * 80)

phase_data = {}
for phase in phase_labels:
    vals = [per_event_details[ev][phase] for ev in [e[0] for e in events]]
    vals = [v if not np.isnan(v) else 0 for v in vals]
    phase_data[phase] = vals

phase_corr_df = pd.DataFrame(phase_data)
corr_matrix = phase_corr_df.corr()

# Pre vs Postの相関だけ表示
pre_phases = ['Pre-5d', 'Pre-3d', 'Pre-1d']
post_phases = ['Post-1d', 'Post-3d', 'Post-5d', 'Post-10d', 'Post-20d', 'Post-30d']
print(f"{'':>12}", end='')
for pp in post_phases:
    print(f"{pp:>10}", end='')
print()
for pr in pre_phases:
    print(f"{pr:<12}", end='')
    for pp in post_phases:
        c = corr_matrix.loc[pr, pp]
        print(f"{c:>10.3f}", end='')
    print()

# ============================================================
# 13. イベント前のratio水準分析
# ============================================================
print("\n" + "=" * 80)
print("【結果7】イベント前のratio水準と事後反応")
print("=" * 80)

# 全期間のratioパーセンタイル
ratio_pct = ratio_df['ratio'].rank(pct=True) * 100

print(f"{'イベント':<22} {'当日ratio':>10} {'百分位':>8} {'Post-5d%':>10} {'Post-10d%':>10}")
print("-" * 65)

event_ratio_levels = []
for ev_name, ev_date in events:
    r_event = get_ratio_on_date(ev_date, ratio_df['ratio'])
    # パーセンタイル
    ev_ts = pd.Timestamp(ev_date)
    hist_ratios = ratio_df.loc[:ev_ts, 'ratio']
    if len(hist_ratios) > 0:
        pct_rank = (hist_ratios < r_event).sum() / len(hist_ratios) * 100
    else:
        pct_rank = np.nan

    post5 = per_event_details[ev_name]['Post-5d']
    post10 = per_event_details[ev_name]['Post-10d']

    event_ratio_levels.append({
        'event': ev_name, 'ratio': r_event, 'pct': pct_rank,
        'post5': post5, 'post10': post10
    })

    print(f"{ev_name:<22} {r_event:>10.2f} {pct_rank:>7.1f}% {( '+' if post5>=0 else '') + f'{post5:.3f}':>10} {( '+' if post10>=0 else '') + f'{post10:.3f}':>10}")

# 高水位 vs 低水位で事後反応の差
if event_ratio_levels:
    median_pct = np.median([e['pct'] for e in event_ratio_levels])
    high_pct = [e for e in event_ratio_levels if e['pct'] >= median_pct]
    low_pct = [e for e in event_ratio_levels if e['pct'] < median_pct]

    if high_pct and low_pct:
        print(f"\n高水位グループ (百分位 >= {median_pct:.0f}%):")
        print(f"  Post-5d平均: {np.mean([e['post5'] for e in high_pct]):+.3f}%  Post-10d平均: {np.mean([e['post10'] for e in high_pct]):+.3f}%")
        print(f"低水位グループ (百分位 < {median_pct:.0f}%):")
        print(f"  Post-5d平均: {np.mean([e['post5'] for e in low_pct]):+.3f}%  Post-10d平均: {np.mean([e['post10'] for e in low_pct]):+.3f}%")

# ============================================================
# 14. 全体サマリー
# ============================================================
print("\n" + "=" * 80)
print("【総合分析】フェーズ別エッジ特定")
print("=" * 80)

print("\n--- 全フェーズ一覧 ---")
print(f"{'フェーズ':<12} {'平均変化':>10} {'勝率':>8} {'p値(片側)':>10} {'有意':>5} {'ドライバー':>12}")
print("-" * 60)

for phase in phase_labels:
    ps = phase_stats.get(phase, {})
    if not ps:
        continue
    mean = ps['mean']
    wr = ps['win_rate']
    p1 = ps.get('p_one_sided', np.nan)
    sig = ps.get('significant', '')
    dr = driver_analysis.get(phase, {}).get('driver', 'N/A')

    sign = '+' if mean >= 0 else ''
    p1_str = f'{p1:.4f}' if not np.isnan(p1) else 'N/A'
    print(f"{phase:<12} {sign}{mean:>9.3f}% {wr:>7.1%} {p1_str:>10} {sig:>5} {dr:>12}")

# 最も有意なフェーズを特定
print("\n--- 最もエッジのあるフェーズ ---")
sorted_phases = sorted(
    [(p, s) for p, s in phase_stats.items() if p != 'Event Day'],
    key=lambda x: abs(x[1].get('mean', 0)),
    reverse=True
)

for i, (phase, s) in enumerate(sorted_phases[:5]):
    direction = "ratio上昇(BTC強/ETH弱)" if s['mean'] > 0 else "ratio下落(BTC弱/ETH強)"
    print(f"  {i+1}. {phase}: 平均 {s['mean']:+.3f}% 勝率 {s['win_rate']:.0%} p={s.get('p_val', 1):.4f} ({direction})")

print("\n" + "=" * 80)
print("分析完了")
print("=" * 80)
