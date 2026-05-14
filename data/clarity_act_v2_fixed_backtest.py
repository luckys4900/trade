#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clarity Act Pair Trading Strategy v2.0 - FIXED & IMPROVED
Fixes: ratio-based P&L, trailing stop, ATR SL/TP, ETH weakness filter, time-decay SL
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


class ClarityActV2Backtester:
    """Fixed pair trading backtest with proper ratio-based logic"""

    def __init__(self, cost_pct=0.17):
        self.cost_pct = cost_pct  # round-trip cost %
        self.btc_1d = None
        self.eth_1d = None

    def load_data(self):
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

        # Ratio ATR (absolute change)
        merged['ratio_change'] = merged['ratio'].diff().abs()
        merged['ratio_atr14'] = merged['ratio_change'].rolling(14, min_periods=5).mean()

        # Ratio MAs
        for w in [3, 5, 10, 14, 20]:
            merged[f'ratio_ma{w}'] = merged['ratio'].rolling(w, min_periods=1).mean()

        # ETH weakness: ETH return vs BTC return over 5d
        merged['btc_ret5'] = merged['close_btc'].pct_change(5)
        merged['eth_ret5'] = merged['close_eth'].pct_change(5)
        merged['eth_weak'] = merged['eth_ret5'] < merged['btc_ret5']

        # Ratio volatility
        merged['ratio_ret'] = merged['ratio'].pct_change()
        merged['ratio_vol10'] = merged['ratio_ret'].rolling(10, min_periods=3).std()
        merged['ratio_vol30'] = merged['ratio_ret'].rolling(30, min_periods=10).std()
        merged['high_vol'] = merged['ratio_vol10'] > merged['ratio_vol30'] * 1.2

        # Volume filter
        merged['eth_vol_ma10'] = merged['volume_eth'].rolling(10, min_periods=3).mean()
        merged['eth_vol_high'] = merged['volume_eth'] > merged['eth_vol_ma10'] * 1.2

        self.data = merged
        self.btc_1d = btc
        self.eth_1d = eth
        return merged

    def get_event_window(self, event_date_str, days_before=5, days_after=40):
        start = pd.to_datetime(event_date_str).date() - timedelta(days=days_before)
        end = pd.to_datetime(event_date_str).date() + timedelta(days=days_after)
        mask = (self.data['date'] >= start) & (self.data['date'] <= end)
        return self.data[mask].reset_index(drop=True)

    def strategy_fixed(self, df, params):
        """
        Fixed Strategy 3: BTC/ETH ratio pair trading
        With trailing stop, ATR SL/TP, ETH weakness filter, time-decay SL
        """
        ma_window = params.get('ma_window', 10)
        use_trailing = params.get('trailing_stop', True)
        trailing_activation_pct = params.get('trailing_activation_pct', 1.0)
        trailing_distance_pct = params.get('trailing_distance_pct', 0.5)
        use_atr_sl = params.get('atr_sl_tp', True)
        atr_sl_mult = params.get('atr_sl_mult', 1.5)
        atr_tp_mult = params.get('atr_tp_mult', 3.0)
        fixed_sl_pct = params.get('fixed_sl_pct', 2.5)
        use_eth_filter = params.get('eth_weakness_filter', True)
        use_time_decay = params.get('time_decay_sl', True)
        time_decay_start = params.get('time_decay_start_pct', 0.5)
        max_hold = params.get('max_hold_days', 35)
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

                # Unrealized P&L %
                unrealized_pct = ((cur_ratio - entry_ratio) / entry_ratio) * 100

                # 1. Fixed SL check
                if cur_ratio <= sl_ratio:
                    exit_reason = 'SL'
                    exit_ratio = cur_ratio

                # 2. Trailing stop check
                elif use_trailing:
                    unrealized_at_peak = ((peak_ratio - entry_ratio) / entry_ratio) * 100
                    if unrealized_at_peak >= trailing_activation_pct:
                        ts_ratio = peak_ratio * (1 - trailing_distance_pct / 100)
                        # Time decay: tighten SL over time
                        if use_time_decay and days_held > max_hold * time_decay_start:
                            progress = min((days_held - max_hold * time_decay_start) /
                                          (max_hold * (1 - time_decay_start)), 1.0)
                            decay_sl = entry_ratio * (1 - (fixed_sl_pct * (1 - progress * 0.7)) / 100)
                            ts_ratio = max(ts_ratio, decay_sl)
                        ts_ratio = max(ts_ratio, fixed_sl)  # never worse than fixed SL

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

                # 6. End of period
                if exit_reason is None and i == len(df) - 1:
                    exit_reason = 'EOP'
                    exit_ratio = cur_ratio

                if exit_reason:
                    raw_pnl = ((exit_ratio - entry_ratio) / entry_ratio) * 100
                    net_pnl = raw_pnl - cost  # round-trip cost

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

        # t-test for EV > 0
        if n >= 2:
            t_stat, p_val = stats.ttest_1samp(pnls, 0)
        else:
            t_stat, p_val = 0, 1.0

        # Bootstrap CI
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

    def run_full_backtest(self):
        """Run backtest across multiple regulatory events and parameter configs"""

        # Regulatory events with potential BTC/ETH asymmetric impact
        events = [
            ('FIT21 House Pass', '2024-05-22'),
            ('ETH ETF Surprise Approval', '2024-05-23'),
            ('SAB121 Override Vote', '2024-05-09'),
            ('Trump Wins Election (Pro-Crypto)', '2024-11-06'),
            ('Gensler Resignation Announced', '2024-11-21'),
            ('Gensler Steps Down', '2025-01-20'),
            ('Trump Crypto EO', '2025-03-07'),
            ('SAB121 Repealed', '2025-04-01'),
        ]

        # Parameter configs to test
        configs = {
            'BASELINE (old logic)': {
                'ma_window': 10, 'trailing_stop': False, 'atr_sl_tp': False,
                'fixed_sl_pct': 2.5, 'eth_weakness_filter': False,
                'time_decay_sl': False, 'max_hold_days': 35,
            },
            'FIXED_A': {
                'ma_window': 10, 'trailing_stop': True, 'trailing_activation_pct': 1.0,
                'trailing_distance_pct': 0.5, 'atr_sl_tp': True,
                'atr_sl_mult': 1.5, 'atr_tp_mult': 3.0,
                'fixed_sl_pct': 2.5, 'eth_weakness_filter': False,
                'time_decay_sl': False, 'max_hold_days': 35,
            },
            'FIXED_A_ETH': {
                'ma_window': 10, 'trailing_stop': True, 'trailing_activation_pct': 1.0,
                'trailing_distance_pct': 0.5, 'atr_sl_tp': True,
                'atr_sl_mult': 1.5, 'atr_tp_mult': 3.0,
                'fixed_sl_pct': 2.5, 'eth_weakness_filter': True,
                'time_decay_sl': False, 'max_hold_days': 35,
            },
            'FIXED_FULL': {
                'ma_window': 10, 'trailing_stop': True, 'trailing_activation_pct': 0.8,
                'trailing_distance_pct': 0.4, 'atr_sl_tp': True,
                'atr_sl_mult': 1.5, 'atr_tp_mult': 3.0,
                'fixed_sl_pct': 2.0, 'eth_weakness_filter': True,
                'time_decay_sl': True, 'time_decay_start_pct': 0.5,
                'max_hold_days': 35,
            },
            'AGGRESSIVE': {
                'ma_window': 5, 'trailing_stop': True, 'trailing_activation_pct': 0.6,
                'trailing_distance_pct': 0.3, 'atr_sl_tp': True,
                'atr_sl_mult': 1.2, 'atr_tp_mult': 2.5,
                'fixed_sl_pct': 1.5, 'eth_weakness_filter': True,
                'time_decay_sl': True, 'time_decay_start_pct': 0.4,
                'max_hold_days': 25,
            },
            'CONSERVATIVE': {
                'ma_window': 14, 'trailing_stop': True, 'trailing_activation_pct': 1.5,
                'trailing_distance_pct': 0.8, 'atr_sl_tp': True,
                'atr_sl_mult': 2.0, 'atr_tp_mult': 4.0,
                'fixed_sl_pct': 3.0, 'eth_weakness_filter': True,
                'time_decay_sl': True, 'time_decay_start_pct': 0.6,
                'max_hold_days': 45,
            },
        }

        print("=" * 100)
        print("CLARITY ACT PAIR TRADING v2.0 - FIXED BACKTEST")
        print("Fixes: ratio-based P&L, trailing stop, ATR SL/TP, ETH filter, time-decay SL")
        print("Cost: %.2f%% round-trip" % self.cost_pct)
        print("=" * 100)

        all_results = {}

        for config_name, params in configs.items():
            print("\n" + "=" * 100)
            print("CONFIG: %s" % config_name)
            print("Params: %s" % json.dumps(params, indent=2))
            print("-" * 100)

            config_trades = []
            event_results = {}

            for event_name, event_date in events:
                df = self.get_event_window(event_date, days_before=5, days_after=40)
                if len(df) < 15:
                    print("  %-35s SKIP (data: %d days)" % (event_name, len(df)))
                    continue

                trades = self.strategy_fixed(df, params)
                metrics = self.calc_metrics(trades)

                event_results[event_name] = {
                    'trades': trades, 'metrics': metrics
                }
                config_trades.extend(trades)

                if metrics:
                    print("  %-35s n=%2d WR=%5.1f%% EV=%+6.3f%% PF=%5.2f RR=%4.2f Total=%+7.3f%%  exits=%s" % (
                        event_name, metrics['n'], metrics['wr'] * 100, metrics['ev'],
                        metrics['pf'], metrics['rr'], metrics['total_pnl'],
                        metrics['exit_reasons']))
                else:
                    print("  %-35s NO TRADES" % event_name)

            # Aggregate
            agg_metrics = self.calc_metrics(config_trades)
            all_results[config_name] = {
                'params': params,
                'events': event_results,
                'aggregate': agg_metrics,
            }

            if agg_metrics:
                print("\n  AGGREGATE: n=%d WR=%.1f%% EV=%+.3f%% PF=%.2f Sharpe=%.2f RR=%.2f p=%.4f CI=[%.3f, %.3f]" % (
                    agg_metrics['n'], agg_metrics['wr'] * 100, agg_metrics['ev'],
                    agg_metrics['pf'], agg_metrics['sharpe'], agg_metrics['rr'],
                    agg_metrics['p_val'], agg_metrics['ci_lo'], agg_metrics['ci_hi']))
            else:
                print("\n  AGGREGATE: NO TRADES")

        # Summary comparison
        print("\n\n" + "=" * 100)
        print("SUMMARY COMPARISON")
        print("=" * 100)
        print("%-25s %4s %6s %6s %6s %6s %6s %8s %8s %6s" % (
            "Config", "N", "WR%", "EV%", "PF", "RR", "Sh", "p-val", "CI-lo", "Tot%"))
        print("-" * 100)

        for config_name, res in all_results.items():
            m = res.get('aggregate')
            if m:
                sig = "*" if m['p_val'] < 0.05 else " "
                print("%-25s %4d %5.1f%% %+5.2f%% %5.2f %5.2f %5.2f %7.4f%s %+7.3f%% %+6.2f%%" % (
                    config_name[:25], m['n'], m['wr'] * 100, m['ev'],
                    m['pf'], m['rr'], m['sharpe'], m['p_val'], sig,
                    m['ci_lo'], m['total_pnl']))

        # Save results
        output_path = os.path.join(DATA_DIR, 'clarity_act_v2_results.json')
        # Convert for JSON serialization
        json_results = {}
        for cn, res in all_results.items():
            json_results[cn] = {
                'params': res['params'],
                'aggregate': res['aggregate'],
                'event_summaries': {}
            }
            for en, er in res['events'].items():
                json_results[cn]['event_summaries'][en] = {
                    'metrics': er['metrics'],
                    'trade_count': len(er['trades']),
                }

        with open(output_path, 'w') as f:
            json.dump(json_results, f, indent=2, default=str)
        print("\nResults saved to: %s" % output_path)

        return all_results


def main():
    bt = ClarityActV2Backtester(cost_pct=0.17)
    bt.load_data()
    results = bt.run_full_backtest()


if __name__ == '__main__':
    main()
