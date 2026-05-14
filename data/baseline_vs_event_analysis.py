#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clarity Act戦略: 通常期間ベースライン vs イベント期間 比較分析
目的: BTC/ETH ratio戦略が「規制イベント期間中」に特有のエッジを持つのか判定する
"""

import pandas as pd
import numpy as np
import json
import os
import warnings
from datetime import datetime, timedelta
from scipy import stats

warnings.filterwarnings('ignore')

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


class BaselineVsEventAnalyzer:
    """通常期間 vs イベント期間の比較分析"""

    def __init__(self, cost_pct=0.17):
        self.cost_pct = cost_pct
        self.data = None

    def load_data(self):
        # BTC daily
        btc_path = os.path.join(DATA_DIR, 'btc_price_1d_cache.csv')
        btc = pd.read_csv(btc_path)
        btc['datetime'] = pd.to_datetime(btc['datetime'])
        btc = btc.sort_values('datetime').reset_index(drop=True)
        btc['date'] = btc['datetime'].dt.date

        # ETH 4h -> daily
        eth_path = os.path.join(DATA_DIR, 'ETH_USDT_4h_730d.csv')
        eth_raw = pd.read_csv(eth_path)
        eth_raw['datetime'] = pd.to_datetime(eth_raw['datetime'])
        eth_raw['date'] = eth_raw['datetime'].dt.date
        eth = eth_raw.groupby('date').agg({
            'open': 'first', 'high': 'max', 'low': 'min',
            'close': 'last', 'volume': 'sum'
        }).reset_index()
        eth['date'] = pd.to_datetime(eth['date']).dt.date

        # Merge
        merged = btc.merge(eth, on='date', suffixes=('_btc', '_eth'))
        merged = merged.sort_values('date').reset_index(drop=True)

        # Ratio
        merged['ratio'] = merged['close_btc'] / merged['close_eth']

        # Ratio ATR
        merged['ratio_change'] = merged['ratio'].diff().abs()
        merged['ratio_atr14'] = merged['ratio_change'].rolling(14, min_periods=5).mean()

        # Ratio MAs
        for w in [3, 5, 10, 14, 20]:
            merged[f'ratio_ma{w}'] = merged['ratio'].rolling(w, min_periods=1).mean()

        # ETH weakness
        merged['btc_ret5'] = merged['close_btc'].pct_change(5)
        merged['eth_ret5'] = merged['close_eth'].pct_change(5)
        merged['eth_weak'] = merged['eth_ret5'] < merged['btc_ret5']

        # Volume
        merged['eth_vol_ma10'] = merged['volume_eth'].rolling(10, min_periods=3).mean()
        merged['eth_vol_high'] = merged['volume_eth'] > merged['eth_vol_ma10'] * 1.2

        self.data = merged
        return merged

    def get_event_exclusion_ranges(self, event_dates, buffer_days=45):
        """規制イベントの前後45日間を除外期間として返す"""
        ranges = []
        for event_name, event_date_str in event_dates:
            event_date = pd.to_datetime(event_date_str).date()
            start = event_date - timedelta(days=buffer_days)
            end = event_date + timedelta(days=buffer_days)
            ranges.append((start, end, event_name))
        return ranges

    def is_in_event_window(self, date, ranges):
        """指定日がイベント期間内かどうか"""
        for start, end, name in ranges:
            if start <= date <= end:
                return True
        return False

    def split_data(self, event_dates, buffer_days=45):
        """データをイベント期間と通常期間に分割"""
        ranges = self.get_event_exclusion_ranges(event_dates, buffer_days)

        self.data['is_event'] = self.data['date'].apply(
            lambda d: self.is_in_event_window(d, ranges)
        )

        event_data = self.data[self.data['is_event']].copy().reset_index(drop=True)
        normal_data = self.data[~self.data['is_event']].copy().reset_index(drop=True)

        return normal_data, event_data, ranges

    def strategy_fixed_full(self, df):
        """
        FIXED_FULL戦略 (v2と同一ロジック)
        - trailing stop (activation 0.8%, distance 0.4%)
        - ATR SL/TP (1.5x / 3.0x)
        - ETH弱気フィルター
        - time-decay SL
        """
        params = {
            'ma_window': 10,
            'trailing_stop': True,
            'trailing_activation_pct': 0.8,
            'trailing_distance_pct': 0.4,
            'atr_sl_tp': True,
            'atr_sl_mult': 1.5,
            'atr_tp_mult': 3.0,
            'fixed_sl_pct': 2.0,
            'eth_weakness_filter': True,
            'time_decay_sl': True,
            'time_decay_start_pct': 0.5,
            'max_hold_days': 35,
        }

        ma_window = params['ma_window']
        use_trailing = params['trailing_stop']
        trailing_activation_pct = params['trailing_activation_pct']
        trailing_distance_pct = params['trailing_distance_pct']
        use_atr_sl = params['atr_sl_tp']
        atr_sl_mult = params['atr_sl_mult']
        atr_tp_mult = params['atr_tp_mult']
        fixed_sl_pct = params['fixed_sl_pct']
        use_eth_filter = params['eth_weakness_filter']
        use_time_decay = params['time_decay_sl']
        time_decay_start = params['time_decay_start_pct']
        max_hold = params['max_hold_days']
        cost = self.cost_pct

        trades = []
        in_pos = False
        entry_ratio = None
        entry_idx = None
        peak_ratio = None
        sl_ratio = None
        tp_ratio = None
        fixed_sl = None

        ma_col = f'ratio_ma{ma_window}'

        for i in range(ma_window, len(df)):
            cur_ratio = df['ratio'].iloc[i]
            ma = df[ma_col].iloc[i]
            prev_ratio = df['ratio'].iloc[i - 1]

            if pd.isna(cur_ratio) or pd.isna(ma):
                continue

            if not in_pos:
                # Entry conditions
                cond_ratio_above_ma = cur_ratio > ma
                cond_uptrend = cur_ratio > prev_ratio
                cond_eth_weak = True
                if use_eth_filter and 'eth_weak' in df.columns:
                    val = df['eth_weak'].iloc[i]
                    if pd.notna(val):
                        cond_eth_weak = bool(val)

                if cond_ratio_above_ma and cond_uptrend and cond_eth_weak:
                    entry_ratio = cur_ratio
                    entry_idx = i
                    peak_ratio = cur_ratio
                    in_pos = True

                    # Set SL/TP
                    if use_atr_sl and 'ratio_atr14' in df.columns:
                        atr = df['ratio_atr14'].iloc[i]
                        if pd.notna(atr) and atr > 0:
                            sl_ratio = entry_ratio - atr_sl_mult * atr
                            tp_ratio = entry_ratio + atr_tp_mult * atr
                        else:
                            sl_ratio = entry_ratio * (1 - fixed_sl_pct / 100)
                            tp_ratio = None
                    else:
                        sl_ratio = entry_ratio * (1 - fixed_sl_pct / 100)
                        tp_ratio = None

                    fixed_sl = sl_ratio

            else:
                exit_reason = None
                exit_ratio = cur_ratio
                days_held = i - entry_idx

                # Update peak
                if cur_ratio > peak_ratio:
                    peak_ratio = cur_ratio

                # 1. Fixed SL check
                if cur_ratio <= sl_ratio:
                    exit_reason = 'SL'
                    exit_ratio = cur_ratio

                # 2. Trailing stop check
                elif use_trailing:
                    unrealized_at_peak = ((peak_ratio - entry_ratio) / entry_ratio) * 100
                    if unrealized_at_peak >= trailing_activation_pct:
                        ts_ratio = peak_ratio * (1 - trailing_distance_pct / 100)
                        # Time decay
                        if use_time_decay and days_held > max_hold * time_decay_start:
                            progress = min((days_held - max_hold * time_decay_start) /
                                          (max_hold * (1 - time_decay_start)), 1.0)
                            decay_sl = entry_ratio * (1 - (fixed_sl_pct * (1 - progress * 0.7)) / 100)
                            ts_ratio = max(ts_ratio, decay_sl)
                        ts_ratio = max(ts_ratio, fixed_sl)

                        if cur_ratio <= ts_ratio:
                            exit_reason = 'TS'
                            exit_ratio = cur_ratio

                # 3. TP check
                if exit_reason is None and tp_ratio is not None and cur_ratio >= tp_ratio:
                    exit_reason = 'TP'
                    exit_ratio = cur_ratio

                # 4. MA reversal exit
                if exit_reason is None and cur_ratio < ma:
                    exit_reason = 'MA_CROSS'
                    exit_ratio = cur_ratio

                # 5. Max hold
                if exit_reason is None and days_held >= max_hold:
                    exit_reason = 'MAX_HOLD'
                    exit_ratio = cur_ratio

                # 6. End of data
                if exit_reason is None and i == len(df) - 1:
                    exit_reason = 'EOP'
                    exit_ratio = cur_ratio

                if exit_reason:
                    raw_pnl = ((exit_ratio - entry_ratio) / entry_ratio) * 100
                    net_pnl = raw_pnl - cost

                    trades.append({
                        'entry_date': str(df['date'].iloc[entry_idx]),
                        'exit_date': str(df['date'].iloc[i]),
                        'entry_ratio': round(entry_ratio, 4),
                        'exit_ratio': round(exit_ratio, 4),
                        'pnl_raw': round(raw_pnl, 4),
                        'pnl_net': round(net_pnl, 4),
                        'exit_reason': exit_reason,
                        'days': days_held,
                        'peak_pct': round(((peak_ratio - entry_ratio) / entry_ratio) * 100, 4),
                    })
                    in_pos = False

        return trades

    def run_strategy_on_segments(self, df, segment_label):
        """連続データ上で戦略を実行"""
        trades = self.strategy_fixed_full(df)
        metrics = self.calc_metrics(trades)
        return trades, metrics

    def run_sliding_window(self, df, window_days=45):
        """
        通常期間で45日間のスライディングウィンドウで戦略を実行
        各ウィンドウは独立した「イベント期間に相当する期間」として扱う
        """
        all_trades = []
        window_metrics = []

        dates = sorted(df['date'].unique())
        if len(dates) < window_days:
            return [], []

        start_idx = 0
        while start_idx + window_days <= len(dates):
            window_start = dates[start_idx]
            window_end = dates[start_idx + window_days - 1]

            window_df = df[
                (df['date'] >= window_start) & (df['date'] <= window_end)
            ].copy().reset_index(drop=True)

            if len(window_df) >= 15:
                trades = self.strategy_fixed_full(window_df)
                if trades:
                    all_trades.extend(trades)
                    m = self.calc_metrics(trades)
                    if m:
                        window_metrics.append({
                            'start': str(window_start),
                            'end': str(window_end),
                            'n_trades': m['n'],
                            'ev': m['ev'],
                            'wr': m['wr'],
                            'sharpe': m['sharpe'],
                            'total_pnl': m['total_pnl'],
                        })

            start_idx += window_days  # non-overlapping windows

        return all_trades, window_metrics

    def calc_metrics(self, trades):
        if not trades:
            return None

        df = pd.DataFrame(trades)
        pnls = df['pnl_net'].values
        wins = df[df['pnl_net'] > 0]
        losses = df[df['pnl_net'] <= 0]

        n = len(df)
        wr = len(wins) / n if n > 0 else 0
        aw = wins['pnl_net'].mean() if len(wins) > 0 else 0
        al = abs(losses['pnl_net'].mean()) if len(losses) > 0 else 0

        total_profit = wins['pnl_net'].sum() if len(wins) > 0 else 0
        total_loss = abs(losses['pnl_net'].sum()) if len(losses) > 0 else 0
        pf = total_profit / total_loss if total_loss > 0 else (1 if total_profit > 0 else 0)

        sharpe = 0
        if len(pnls) > 1 and np.std(pnls) > 0:
            sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252)

        cum = np.cumsum(pnls)
        peak_val = 0
        mdd = 0
        for c in cum:
            if c > peak_val:
                peak_val = c
            mdd = max(mdd, peak_val - c)

        ev = np.mean(pnls)

        if n >= 2:
            t_stat, p_val = stats.ttest_1samp(pnls, 0)
        else:
            t_stat, p_val = 0, 1.0

        if n >= 5:
            boot_evs = []
            rng = np.random.RandomState(42)
            for _ in range(2000):
                sample = rng.choice(pnls, size=n, replace=True)
                boot_evs.append(np.mean(sample))
            ci_lo = np.percentile(boot_evs, 2.5)
            ci_hi = np.percentile(boot_evs, 97.5)
        else:
            ci_lo, ci_hi = ev - np.std(pnls), ev + np.std(pnls)

        rr = aw / al if al > 0 else 0

        return {
            'n': n,
            'wr': round(wr, 4),
            'aw': round(aw, 4),
            'al': round(al, 4),
            'pf': round(pf, 4),
            'sharpe': round(sharpe, 4),
            'mdd': round(mdd, 4),
            'ev': round(ev, 4),
            'rr': round(rr, 4),
            't_stat': round(t_stat, 4),
            'p_val': round(p_val, 6),
            'ci_lo': round(ci_lo, 4),
            'ci_hi': round(ci_hi, 4),
            'avg_days': round(df['days'].mean(), 1),
            'total_pnl': round(pnls.sum(), 4),
            'exit_reasons': df['exit_reason'].value_counts().to_dict(),
        }

    def compare_event_vs_normal(self, event_trades, normal_trades):
        """イベント期間と通常期間のEVの統計的検定"""
        if not event_trades or not normal_trades:
            return None

        event_pnls = [t['pnl_net'] for t in event_trades]
        normal_pnls = [t['pnl_net'] for t in normal_trades]

        # Welch's t-test (2-sample, unequal variance)
        t_stat, p_val = stats.ttest_ind(event_pnls, normal_pnls, equal_var=False)

        # Mann-Whitney U test (non-parametric)
        u_stat, u_p_val = stats.mannwhitneyu(event_pnls, normal_pnls, alternative='greater')

        # Effect size (Cohen's d)
        mean_diff = np.mean(event_pnls) - np.mean(normal_pnls)
        pooled_std = np.sqrt((np.var(event_pnls) + np.var(normal_pnls)) / 2)
        cohens_d = mean_diff / pooled_std if pooled_std > 0 else 0

        return {
            'event_n': len(event_pnls),
            'normal_n': len(normal_pnls),
            'event_ev': round(np.mean(event_pnls), 4),
            'normal_ev': round(np.mean(normal_pnls), 4),
            'event_wr': round(sum(1 for p in event_pnls if p > 0) / len(event_pnls), 4),
            'normal_wr': round(sum(1 for p in normal_pnls if p > 0) / len(normal_pnls), 4),
            'event_sharpe': round(np.mean(event_pnls) / np.std(event_pnls) * np.sqrt(252), 4) if np.std(event_pnls) > 0 else 0,
            'normal_sharpe': round(np.mean(normal_pnls) / np.std(normal_pnls) * np.sqrt(252), 4) if np.std(normal_pnls) > 0 else 0,
            'welch_t': round(t_stat, 4),
            'welch_p': round(p_val, 6),
            'mann_whitney_u': round(u_stat, 4),
            'mann_whitney_p': round(u_p_val, 6),
            'cohens_d': round(cohens_d, 4),
            'ev_diff': round(np.mean(event_pnls) - np.mean(normal_pnls), 4),
        }


def main():
    print("=" * 100)
    print("Clarity Act戦略: 通常期間ベースライン vs イベント期間 比較分析")
    print("目的: BTC/ETH ratio戦略が「規制イベント期間中」に特有のエッジを持つのか判定")
    print("戦略: FIXED_FULL (trailing stop, ATR SL/TP, ETH弱気フィルター, time-decay SL)")
    print("=" * 100)

    analyzer = BaselineVsEventAnalyzer(cost_pct=0.17)
    data = analyzer.load_data()

    print("\n[1] データ読み込み完了")
    print("  BTC期間: %s ~ %s" % (data['date'].min(), data['date'].max()))
    print("  総日数: %d" % len(data))
    print("  ETH データ範囲: %s ~ %s" % (
        data[data['close_eth'].notna()]['date'].min(),
        data[data['close_eth'].notna()]['date'].max()
    ))

    # 規制イベント定義
    event_dates = [
        ('FIT21 House Pass', '2024-05-22'),
        ('ETH ETF Surprise Approval', '2024-05-23'),
        ('SAB121 Override Vote', '2024-05-09'),
        ('Trump Wins Election (Pro-Crypto)', '2024-11-06'),
        ('Gensler Resignation Announced', '2024-11-21'),
        ('Gensler Steps Down', '2025-01-20'),
        ('Trump Crypto EO', '2025-03-07'),
        ('SAB121 Repealed', '2025-04-01'),
    ]

    print("\n[2] 規制イベント期間の除外設定 (各イベント前後45日)")
    for name, date in event_dates:
        print("  - %s: %s" % (name, date))

    # データ分割
    normal_data, event_data, ranges = analyzer.split_data(event_dates, buffer_days=45)

    print("\n[3] データ分割結果")
    print("  通常期間: %d日 (%.1f%%)" % (len(normal_data), len(normal_data) / len(data) * 100))
    print("  イベント期間: %d日 (%.1f%%)" % (len(event_data), len(event_data) / len(data) * 100))

    # 通常期間の表示
    if len(normal_data) > 0:
        print("  通常期間: %s ~ %s" % (normal_data['date'].min(), normal_data['date'].max()))
    if len(event_data) > 0:
        print("  イベント期間: %s ~ %s" % (event_data['date'].min(), event_data['date'].max()))

    # ===== 分析A: 連続データ上での戦略実行 =====
    print("\n" + "=" * 100)
    print("[分析A] 連続データ上での戦略実行")
    print("=" * 100)

    # 通常期間 - 連続データで実行
    print("\n--- 通常期間 (連続) ---")
    normal_trades, normal_metrics = analyzer.run_strategy_on_segments(normal_data, "通常期間")
    if normal_metrics:
        print("  トレード数: %d" % normal_metrics['n'])
        print("  勝率: %.1f%%" % (normal_metrics['wr'] * 100))
        print("  EV: %+.4f%%" % normal_metrics['ev'])
        print("  Sharpe: %.4f" % normal_metrics['sharpe'])
        print("  PF: %.4f" % normal_metrics['pf'])
        print("  RR: %.4f" % normal_metrics['rr'])
        print("  MDD: %.2f%%" % normal_metrics['mdd'])
        print("  Total PnL: %+.4f%%" % normal_metrics['total_pnl'])
        print("  平均保持日数: %.1f" % normal_metrics['avg_days'])
        print("  t-stat: %.4f (p=%.4f)" % (normal_metrics['t_stat'], normal_metrics['p_val']))
        print("  CI: [%.4f, %.4f]" % (normal_metrics['ci_lo'], normal_metrics['ci_hi']))
        print("  決済理由: %s" % normal_metrics['exit_reasons'])
    else:
        print("  (トレードなし)")

    # イベント期間 - 連続データで実行
    print("\n--- イベント期間 (連続) ---")
    event_trades, event_metrics = analyzer.run_strategy_on_segments(event_data, "イベント期間")
    if event_metrics:
        print("  トレード数: %d" % event_metrics['n'])
        print("  勝率: %.1f%%" % (event_metrics['wr'] * 100))
        print("  EV: %+.4f%%" % event_metrics['ev'])
        print("  Sharpe: %.4f" % event_metrics['sharpe'])
        print("  PF: %.4f" % event_metrics['pf'])
        print("  RR: %.4f" % event_metrics['rr'])
        print("  MDD: %.2f%%" % event_metrics['mdd'])
        print("  Total PnL: %+.4f%%" % event_metrics['total_pnl'])
        print("  平均保持日数: %.1f" % event_metrics['avg_days'])
        print("  t-stat: %.4f (p=%.4f)" % (event_metrics['t_stat'], event_metrics['p_val']))
        print("  CI: [%.4f, %.4f]" % (event_metrics['ci_lo'], event_metrics['ci_hi']))
        print("  決済理由: %s" % event_metrics['exit_reasons'])
    else:
        print("  (トレードなし)")

    # ===== 分析B: スライディングウィンドウ =====
    print("\n" + "=" * 100)
    print("[分析B] 45日スライディングウィンドウ分析 (各期間をイベント期間と同等に扱う)")
    print("=" * 100)

    normal_sw_trades, normal_sw_metrics = analyzer.run_sliding_window(normal_data, window_days=45)

    print("\n--- 通常期間 (45日ウィンドウ) ---")
    print("  ウィンドウ数: %d" % len(normal_sw_metrics))
    if normal_sw_trades:
        agg = analyzer.calc_metrics(normal_sw_trades)
        if agg:
            print("  トレード数: %d" % agg['n'])
            print("  勝率: %.1f%%" % (agg['wr'] * 100))
            print("  EV: %+.4f%%" % agg['ev'])
            print("  Sharpe: %.4f" % agg['sharpe'])
            print("  PF: %.4f" % agg['pf'])
            print("  MDD: %.2f%%" % agg['mdd'])
            print("  t-stat: %.4f (p=%.4f)" % (agg['t_stat'], agg['p_val']))
            print("  CI: [%.4f, %.4f]" % (agg['ci_lo'], agg['ci_hi']))
            print("  決済理由: %s" % agg['exit_reasons'])

            # ウィンドウ別EVの分布
            window_evs = [m['ev'] for m in normal_sw_metrics]
            window_wrs = [m['wr'] for m in normal_sw_metrics]
            positive_ev_windows = sum(1 for e in window_evs if e > 0)
            print("\n  ウィンドウ別EV分布:")
            print("    平均EV: %+.4f%%" % np.mean(window_evs))
            print("    EV中央値: %+.4f%%" % np.median(window_evs))
            print("    EV標準偏差: %.4f" % np.std(window_evs))
            print("    EV > 0のウィンドウ: %d/%d (%.1f%%)" % (
                positive_ev_windows, len(window_evs),
                positive_ev_windows / len(window_evs) * 100 if window_evs else 0))
    else:
        print("  (トレードなし)")

    # ===== 分析C: 既存のイベント期間バックテスト結果との比較 =====
    print("\n" + "=" * 100)
    print("[分析C] 既存イベント期間結果 (FIXED_FULL from clarity_act_v2_results.json)")
    print("=" * 100)

    v2_results_path = os.path.join(DATA_DIR, 'clarity_act_v2_results.json')
    event_period_data = None
    if os.path.exists(v2_results_path):
        with open(v2_results_path, 'r') as f:
            v2_results = json.load(f)
        fixed_full = v2_results.get('FIXED_FULL', {})
        agg = fixed_full.get('aggregate', {})
        if agg:
            print("  [イベント期間 FIXED_FULL]")
            print("  トレード数: %d" % agg['n'])
            print("  勝率: %.1f%%" % (agg['wr'] * 100))
            print("  EV: %+.4f%%" % agg['ev'])
            print("  Sharpe: %.4f" % agg['sharpe'])
            print("  PF: %.4f" % agg['pf'])
            print("  MDD: %.2f%%" % agg['mdd'])
            print("  t-stat: %.4f (p=%.4f)" % (agg.get('t_stat', 0), agg.get('p_val', 1)))
            print("  CI: [%.4f, %.4f]" % (agg.get('ci_lo', 0), agg.get('ci_hi', 0)))

            # 個別イベント
            event_summaries = fixed_full.get('event_summaries', {})
            event_individual_trades = []
            for ename, esum in event_summaries.items():
                m = esum.get('metrics', {})
                if m:
                    print("\n  [%s] n=%d WR=%.1f%% EV=%+.4f%% Total=%+.4f%%" % (
                        ename, m['n'], m['wr'] * 100, m['ev'], m.get('total_pnl', 0)))
                    # 個別トレードのEVを収集
                    for _ in range(m['n']):
                        # 個別トレードPnLを復元できないので集計値を使う
                        pass
            event_period_data = agg

    # ===== 統計的検定 =====
    print("\n" + "=" * 100)
    print("[統計的検定] イベント期間 vs 通常期間")
    print("=" * 100)

    if normal_trades and event_trades:
        comparison = analyzer.compare_event_vs_normal(event_trades, normal_trades)
        if comparison:
            print("\n  === Welch's t-test (2群比較) ===")
            print("  イベント期間 EV: %+.4f%% (n=%d)" % (comparison['event_ev'], comparison['event_n']))
            print("  通常期間 EV:     %+.4f%% (n=%d)" % (comparison['normal_ev'], comparison['normal_n']))
            print("  EV差分:          %+.4f%%" % comparison['ev_diff'])
            print("  t-stat: %.4f" % comparison['welch_t'])
            print("  p-value: %.6f %s" % (comparison['welch_p'], "***" if comparison['welch_p'] < 0.01 else "**" if comparison['welch_p'] < 0.05 else "*" if comparison['welch_p'] < 0.1 else "(n.s.)"))
            print("  Cohen's d: %.4f" % comparison['cohens_d'])

            print("\n  === Mann-Whitney U検定 (ノンパラメトリック) ===")
            print("  U-stat: %.4f" % comparison['mann_whitney_u'])
            print("  p-value: %.6f (片側: イベント > 通常) %s" % (
                comparison['mann_whitney_p'],
                "***" if comparison['mann_whitney_p'] < 0.01 else "**" if comparison['mann_whitney_p'] < 0.05 else "*" if comparison['mann_whitney_p'] < 0.1 else "(n.s.)"
            ))

            print("\n  === 各指標比較 ===")
            print("  項目        | イベント期間 | 通常期間   | 差分")
            print("  " + "-" * 60)
            print("  勝率        | %8.1f%%    | %8.1f%%  | %+.1f%%" % (
                comparison['event_wr'] * 100, comparison['normal_wr'] * 100,
                (comparison['event_wr'] - comparison['normal_wr']) * 100))
            print("  EV          | %+8.4f%%   | %+8.4f%% | %+.4f%%" % (
                comparison['event_ev'], comparison['normal_ev'], comparison['ev_diff']))
            print("  Sharpe      | %8.4f    | %8.4f  | %+.4f" % (
                comparison['event_sharpe'], comparison['normal_sharpe'],
                comparison['event_sharpe'] - comparison['normal_sharpe']))

    elif normal_trades and event_period_data:
        # スライディングウィンドウの通常期間データ vs イベント期間データ
        print("\n  [注] イベント期間はv2_results.jsonのFIXED_FULLを使用")
        print("  [注] 通常期間はスライディングウィンドウ分析を使用")

        normal_pnls = [t['pnl_net'] for t in normal_sw_trades] if normal_sw_trades else []

        if normal_pnls and event_period_data:
            # 疑似的なイベント期間PnL (EVから分布を推定)
            # 直接比較として、集計値を比較
            print("\n  === 集計値比較 ===")
            print("  項目        | イベント期間 | 通常期間(SW)")
            print("  " + "-" * 60)

            normal_agg = analyzer.calc_metrics(normal_sw_trades) if normal_sw_trades else None

            if normal_agg:
                print("  トレード数  | %8d    | %8d" % (event_period_data['n'], normal_agg['n']))
                print("  勝率        | %8.1f%%    | %8.1f%%" % (event_period_data['wr'] * 100, normal_agg['wr'] * 100))
                print("  EV          | %+8.4f%%   | %+8.4f%%" % (event_period_data['ev'], normal_agg['ev']))
                print("  Sharpe      | %8.4f    | %8.4f" % (event_period_data['sharpe'], normal_agg['sharpe']))
                print("  PF          | %8.4f    | %8.4f" % (event_period_data['pf'], normal_agg['pf']))
                print("  MDD         | %8.2f%%   | %8.2f%%" % (event_period_data['mdd'], normal_agg['mdd']))
                print("  t-stat      | %8.4f    | %8.4f" % (event_period_data.get('t_stat', 0), normal_agg['t_stat']))
                print("  p-value     | %8.6f    | %8.6f" % (event_period_data.get('p_val', 1), normal_agg['p_val']))

                ev_diff = event_period_data['ev'] - normal_agg['ev']
                print("\n  EV差分: %+.4f%%" % ev_diff)

                if ev_diff > 0:
                    print("  → イベント期間の方がEVが高い")
                else:
                    print("  → 通常期間の方がEVが高い、または同等")

                # ウィンドウEV分布との比較
                window_evs = [m['ev'] for m in normal_sw_metrics] if normal_sw_metrics else []
                if window_evs:
                    event_ev = event_period_data['ev']
                    pct_above = sum(1 for e in window_evs if e > event_ev) / len(window_evs) * 100
                    print("\n  イベント期間EV(%+.4f%%)が通常期間ウィンドウEV分布の何パーセンタイルか:" % event_ev)
                    sorted_evs = sorted(window_evs)
                    rank = sum(1 for e in sorted_evs if e <= event_ev)
                    percentile = rank / len(sorted_evs) * 100
                    print("  → %.1fパーセンタイル" % percentile)

    # ===== 最終判定 =====
    print("\n" + "=" * 100)
    print("[最終判定]")
    print("=" * 100)

    if normal_trades and event_trades:
        comparison = analyzer.compare_event_vs_normal(event_trades, normal_trades)

        if comparison:
            is_significant = comparison['welch_p'] < 0.05
            event_better = comparison['event_ev'] > comparison['normal_ev']

            if is_significant and event_better:
                print("\n  結論: Clarity Act戦略は規制イベント期間中に「統計的に有意なエッジ」を持つ")
                print("  p=%.4f < 0.05, イベントEV = %+.4f%% > 通常EV = %+.4f%%" % (
                    comparison['welch_p'], comparison['event_ev'], comparison['normal_ev']))
                print("  → イベント期間に限定して運用する意義あり")
            elif is_significant and not event_better:
                print("\n  結論: イベント期間と通常期間で有意差あり、但し通常期間の方が優位")
                print("  p=%.4f < 0.05, 通常EV = %+.4f%% > イベントEV = %+.4f%%" % (
                    comparison['welch_p'], comparison['normal_ev'], comparison['event_ev']))
                print("  → イベント期間限定の意義なし、むしろ通常期間の方が良い")
            else:
                print("\n  結論: イベント期間と通常期間で「統計的に有意な差なし」")
                print("  p=%.4f >= 0.05" % comparison['welch_p'])
                print("  → Clarity Act戦略は「いつでもBTC/ETH ratio > MAでエントリーする戦略」と同じ")
                print("  → イベント期間限定の運用に特段の意義なし")

    elif normal_sw_trades and event_period_data:
        normal_agg = analyzer.calc_metrics(normal_sw_trades)
        if normal_agg:
            ev_diff = event_period_data['ev'] - normal_agg['ev']
            print("\n  [間接比較] (イベント期間はv2 results, 通常期間はSW分析)")
            print("  イベント期間 EV: %+.4f%%" % event_period_data['ev'])
            print("  通常期間 EV:     %+.4f%%" % normal_agg['ev'])
            print("  差分: %+.4f%%" % ev_diff)

            if abs(ev_diff) < 0.3:
                print("\n  → EV差が小さい(< 0.3%)。イベント期間の特別なエッジは確認できない")
            elif ev_diff > 0:
                print("\n  → イベント期間のEVが高いが、統計的検定なしでは有意性不明")
            else:
                print("\n  → 通常期間のEVがむしろ高い")
    else:
        print("\n  データ不足のため判定不可")

    # 結果を保存
    output = {
        'analysis_date': str(datetime.now()),
        'parameters': {
            'strategy': 'FIXED_FULL',
            'cost_pct': 0.17,
            'event_buffer_days': 45,
            'sliding_window_days': 45,
        },
        'event_dates': event_dates,
        'normal_period_metrics': normal_metrics,
        'event_period_metrics': event_metrics,
        'normal_sw_metrics': normal_sw_metrics if normal_sw_metrics else None,
        'comparison': comparison if normal_trades and event_trades else None,
    }

    output_path = os.path.join(DATA_DIR, 'baseline_vs_event_results.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str, ensure_ascii=False)
    print("\n結果保存: %s" % output_path)


if __name__ == '__main__':
    main()
