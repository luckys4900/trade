#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clarity Act Optimized Backtest with Relaxed Parameters
Objective: Generate sufficient trade signals for robust statistical analysis
Focus: Higher-frequency trading compatible with 40-day event window
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class OptimizedClarityBacktester:
    """Optimized backtest with higher trade frequency"""

    def __init__(self, slippage_pct=0.15):
        self.btc_data = None
        self.eth_data = None
        self.slippage_pct = slippage_pct

    def load_data(self, btc_path, eth_path):
        self.btc_data = pd.read_csv(btc_path)
        self.btc_data['datetime'] = pd.to_datetime(self.btc_data['datetime'])
        self.btc_data = self.btc_data.sort_values('datetime').reset_index(drop=True)

        eth_raw = pd.read_csv(eth_path)
        eth_raw['datetime'] = pd.to_datetime(eth_raw['datetime'])
        eth_raw['date'] = eth_raw['datetime'].dt.date
        self.eth_data = eth_raw.groupby('date').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()
        self.eth_data['datetime'] = pd.to_datetime(self.eth_data['date'])
        self.eth_data = self.eth_data[['datetime', 'open', 'high', 'low', 'close', 'volume']]

    def get_period(self, start_date_str, days=40):
        start = pd.to_datetime(start_date_str).date()
        end = start + timedelta(days=days)

        btc = self.btc_data[
            (self.btc_data['datetime'].dt.date >= start) &
            (self.btc_data['datetime'].dt.date <= end)
        ].copy().reset_index(drop=True)

        eth = self.eth_data[
            (self.eth_data['datetime'].dt.date >= start) &
            (self.eth_data['datetime'].dt.date <= end)
        ].copy().reset_index(drop=True)

        return btc, eth

    def add_indicators(self, df):
        df = df.copy()

        # Moving averages - longer & shorter
        for period in [2, 3, 5, 10, 20]:
            df[f'ma{period}'] = df['close'].rolling(window=period, min_periods=1).mean()

        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr14'] = df['tr'].rolling(window=14, min_periods=1).mean()

        # Returns and volatility
        df['ret'] = df['close'].pct_change()
        df['vol10'] = df['ret'].rolling(window=10, min_periods=1).std() * 100
        df['vol10_ma'] = df['vol10'].rolling(window=20, min_periods=1).mean()

        # Daily direction
        df['up'] = (df['close'] > df['close'].shift(1)).astype(int)

        return df

    # ===== STRATEGY 1: SIMPLIFIED TREND FOLLOWING =====
    def strategy1_relaxed(self, btc_df):
        """
        Relaxed Trend Following
        Entry: Close > MA(3) on day 2 (simpler, more frequent)
        Exit: Close < MA(5) OR end
        SL: Entry - 1.5×ATR | TP: Entry + 2.5×ATR
        """
        df = self.add_indicators(btc_df)
        trades = []
        in_pos = False
        entry_px = None
        entry_idx = None

        for i in range(5, len(df)):
            close = df.loc[i, 'close']
            ma3 = df.loc[i, 'ma3']
            ma5 = df.loc[i, 'ma5']
            atr = df.loc[i, 'atr14']

            if not in_pos:
                # Entry: close > MA3, confirmation
                if close > ma3 and i > 0 and df.loc[i-1, 'close'] > df.loc[i-1, 'ma3']:
                    entry_px = close * (1 + self.slippage_pct/100)
                    entry_idx = i
                    sl = entry_px - 1.5 * atr
                    tp = entry_px + 2.5 * atr
                    in_pos = True

            else:
                exit_reason = None
                exit_px = close

                if close <= sl:
                    exit_reason = 'SL'
                    exit_px = sl
                elif close >= tp:
                    exit_reason = 'TP'
                    exit_px = tp
                elif close < ma5:
                    exit_reason = 'MA5_CROSS'

                if i == len(df) - 1 and in_pos:
                    exit_reason = 'EOP'

                if exit_reason:
                    exit_px = exit_px * (1 - self.slippage_pct/100)
                    pnl = ((exit_px - entry_px) / entry_px) * 100
                    trades.append({
                        'entry_date': df.loc[entry_idx, 'datetime'].date(),
                        'exit_date': df.loc[i, 'datetime'].date(),
                        'entry_px': entry_px,
                        'exit_px': exit_px,
                        'pnl': pnl,
                        'exit_reason': exit_reason,
                        'days': i - entry_idx
                    })
                    in_pos = False

        return trades

    # ===== STRATEGY 2: VOLATILITY EXPANSION (RELAXED) =====
    def strategy2_relaxed(self, btc_df, vol_threshold=1.10):
        """
        Relaxed Volatility Expansion
        Entry: Vol > 110% of 20d MA (easier trigger)
        Exit: Vol < MA OR end
        """
        df = self.add_indicators(btc_df)
        trades = []
        in_pos = False
        entry_px = None
        entry_idx = None

        for i in range(20, len(df)):
            vol = df.loc[i, 'vol10']
            vol_ma = df.loc[i, 'vol10_ma']
            close = df.loc[i, 'close']

            if not in_pos:
                if vol > vol_ma * vol_threshold:
                    entry_px = close * (1 + self.slippage_pct/100)
                    entry_idx = i
                    in_pos = True

            else:
                exit_reason = None
                exit_px = close

                if vol < vol_ma:
                    exit_reason = 'VOL_DOWN'

                if i == len(df) - 1 and in_pos:
                    exit_reason = 'EOP'

                if exit_reason:
                    exit_px = exit_px * (1 - self.slippage_pct/100)
                    pnl = ((exit_px - entry_px) / entry_px) * 100
                    trades.append({
                        'entry_date': df.loc[entry_idx, 'datetime'].date(),
                        'exit_date': df.loc[i, 'datetime'].date(),
                        'entry_px': entry_px,
                        'exit_px': exit_px,
                        'pnl': pnl,
                        'exit_reason': exit_reason,
                        'days': i - entry_idx
                    })
                    in_pos = False

        return trades

    # ===== STRATEGY 3: PAIR TRADING (RELAXED) =====
    def strategy3_relaxed(self, btc_df, eth_df):
        """
        Relaxed Pair Trading
        Entry: BTC/ETH ratio > simple trend
        Exit: Ratio changes direction OR end
        """
        df_btc = self.add_indicators(btc_df)
        df_eth = self.add_indicators(eth_df)

        dates_btc = set(df_btc['datetime'].dt.date)
        dates_eth = set(df_eth['datetime'].dt.date)
        common_dates = sorted(dates_btc & dates_eth)

        df_btc = df_btc[df_btc['datetime'].dt.date.isin(common_dates)].reset_index(drop=True)
        df_eth = df_eth[df_eth['datetime'].dt.date.isin(common_dates)].reset_index(drop=True)

        ratio = df_btc['close'] / df_eth['close']
        ratio_ma10 = ratio.rolling(10, min_periods=1).mean()

        trades = []
        in_pos = False
        entry_ratio = None
        entry_idx = None
        position_direction = None  # 'up' or 'down'

        for i in range(10, len(ratio)):
            cur_ratio = ratio.iloc[i]
            ma_ratio = ratio_ma10.iloc[i]
            prev_ratio = ratio.iloc[i-1] if i > 0 else cur_ratio

            if not in_pos:
                if cur_ratio > ma_ratio and cur_ratio > prev_ratio:
                    entry_ratio = cur_ratio
                    entry_idx = i
                    position_direction = 'up'
                    in_pos = True

            else:
                exit_reason = None
                exit_ratio = cur_ratio

                # Exit on reversal
                if position_direction == 'up' and cur_ratio < prev_ratio:
                    exit_reason = 'REVERSE'
                elif position_direction == 'down' and cur_ratio > prev_ratio:
                    exit_reason = 'REVERSE'

                if i == len(ratio) - 1 and in_pos:
                    exit_reason = 'EOP'

                if exit_reason:
                    pnl = ((exit_ratio - entry_ratio) / entry_ratio) * 100
                    trades.append({
                        'entry_date': df_btc.loc[entry_idx, 'datetime'].date(),
                        'exit_date': df_btc.loc[i, 'datetime'].date(),
                        'entry_ratio': entry_ratio,
                        'exit_ratio': exit_ratio,
                        'pnl': pnl,
                        'exit_reason': exit_reason,
                        'days': i - entry_idx
                    })
                    in_pos = False

        return trades

    def calc_metrics(self, trades):
        if not trades:
            return None

        df = pd.DataFrame(trades)
        pnls = df['pnl'].values
        winning = df[df['pnl'] > 0]
        losing = df[df['pnl'] < 0]

        n = len(df)
        wr = len(winning) / n if n > 0 else 0
        aw = winning['pnl'].mean() if len(winning) > 0 else 0
        al = abs(losing['pnl'].mean()) if len(losing) > 0 else 0

        total_profit = winning['pnl'].sum() if len(winning) > 0 else 0
        total_loss = abs(losing['pnl'].sum()) if len(losing) > 0 else 0
        pf = total_profit / total_loss if total_loss > 0 else (1 if total_profit > 0 else 0)

        if len(pnls) > 1 and np.std(pnls) > 0:
            sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(252))
        else:
            sharpe = 0

        cum = np.cumsum(pnls)
        peak = 0
        mdd = 0
        for c in cum:
            if c > peak:
                peak = c
            mdd = max(mdd, peak - c)

        ev = (wr * aw) - ((1 - wr) * al)
        kelly = (wr * aw) / al if al > 0 else 0

        return {
            'trades': n,
            'wr': wr,
            'aw': aw,
            'al': al,
            'pf': pf,
            'total_ret': pnls.sum(),
            'sharpe': sharpe,
            'mdd': mdd,
            'ev': ev,
            'kelly': kelly,
            'avg_days': df['days'].mean()
        }

    def evaluate_verdict(self, m):
        if m is None or m['trades'] == 0:
            return "✗ NO TRADES"

        score = 0
        if m['wr'] >= 0.40:
            score += 1
        if m['pf'] >= 1.0:
            score += 1
        if m['sharpe'] >= 0.3:
            score += 1
        if m['mdd'] <= 25:
            score += 1
        if m['ev'] > 0:
            score += 1

        if score >= 4:
            return "✓ IMPLEMENTABLE"
        elif score >= 3:
            return "◐ MARGINAL"
        else:
            return "✗ NOT VIABLE"

    def backtest_event(self, event_name, event_date):
        btc, eth = self.get_period(event_date, days=40)

        if len(btc) < 10:
            return None

        s1 = self.strategy1_relaxed(btc)
        s2 = self.strategy2_relaxed(btc)
        s3 = self.strategy3_relaxed(btc, eth)

        return {
            'event': event_name,
            'date': event_date,
            'days_available': len(btc),
            'strategy1': {'trades': s1, 'metrics': self.calc_metrics(s1)},
            'strategy2': {'trades': s2, 'metrics': self.calc_metrics(s2)},
            'strategy3': {'trades': s3, 'metrics': self.calc_metrics(s3)}
        }

    def run_backtest(self):
        events = [
            ('FIT21 House Pass', '2024-05-22'),
            ('Gary Gensler Resignation', '2025-01-09'),
        ]

        results = {}
        for name, date in events:
            print(f"\n[{name}] {date}")
            result = self.backtest_event(name, date)

            if result is None:
                print(f"  [!] Insufficient data")
                continue

            results[name] = result

            for strat_num in [1, 2, 3]:
                key = f'strategy{strat_num}'
                m = result[key]['metrics']

                if m is None:
                    print(f"  [{key}] No trades")
                else:
                    verdict = self.evaluate_verdict(m)
                    print(f"  [{key}] {m['trades']} trades | WR:{m['wr']:.1%} | PF:{m['pf']:.2f} | "
                          f"Sharpe:{m['sharpe']:.2f} | DD:{m['mdd']:.1f}% | EV:{m['ev']:+.2f}% | {verdict}")

        return results


def main():
    print("="*100)
    print("CLARITY ACT OPTIMIZED BACKTEST")
    print("Parameters: Relaxed entry conditions for 40-day regulatory event window")
    print("="*100)

    bt = OptimizedClarityBacktester(slippage_pct=0.15)
    bt.load_data(
        '/Users/user/Desktop/trade/data/btc_price_1d_extended.csv',
        '/Users/user/Desktop/trade/data/ETH_USDT_4h_730d.csv'
    )

    results = bt.run_backtest()

    # Generate detailed report
    print("\n" + "="*100)
    print("DETAILED RESULTS")
    print("="*100 + "\n")

    all_metrics = {'strategy1': [], 'strategy2': [], 'strategy3': []}

    for event_name, result in results.items():
        print(f"\n{event_name} ({result['date']}) - {result['days_available']} days")
        print("-"*100)

        for strat_num in [1, 2, 3]:
            key = f'strategy{strat_num}'
            m = result[key]['metrics']

            if m and m['trades'] > 0:
                all_metrics[key].append(m)
                print(f"\n{key}:")
                print(f"  Trades:         {m['trades']}")
                print(f"  Win Rate:       {m['wr']:.1%}")
                print(f"  Avg Win:        {m['aw']:+.2f}%")
                print(f"  Avg Loss:       {m['al']:+.2f}%")
                print(f"  Profit Factor:  {m['pf']:.2f}")
                print(f"  Sharpe Ratio:   {m['sharpe']:.2f}")
                print(f"  Max Drawdown:   {m['mdd']:.1f}%")
                print(f"  Expected Val:   {m['ev']:+.2f}%")
                print(f"  Kelly Crit:     {m['kelly']:.2f}x")
                print(f"  Avg Duration:   {m['avg_days']:.1f} days")

    print("\n" + "="*100)
    print("AGGREGATE ANALYSIS & CLARITY ACT PROJECTIONS")
    print("="*100 + "\n")

    for strat_num, strat_name in [(1, 'Strategy 1: Trend Following'),
                                   (2, 'Strategy 2: Volatility Expansion'),
                                   (3, 'Strategy 3: Pair Trading')]:
        key = f'strategy{strat_num}'
        metrics_list = all_metrics[key]

        if not metrics_list:
            print(f"{strat_name}: Insufficient data")
            continue

        print(f"\n{strat_name}:")
        print("-"*100)

        avg_wr = np.mean([m['wr'] for m in metrics_list])
        avg_aw = np.mean([m['aw'] for m in metrics_list])
        avg_al = np.mean([m['al'] for m in metrics_list])
        avg_pf = np.mean([m['pf'] for m in metrics_list])
        avg_sharpe = np.mean([m['sharpe'] for m in metrics_list])
        avg_mdd = np.mean([m['mdd'] for m in metrics_list])
        avg_ev = np.mean([m['ev'] for m in metrics_list])
        avg_kelly = np.mean([m['kelly'] for m in metrics_list])
        total_trades = sum([m['trades'] for m in metrics_list])

        print(f"  Across {len(metrics_list)} historical events ({total_trades} total trades):")
        print(f"    Win Rate:        {avg_wr:7.1%}")
        print(f"    Avg Win/Loss:    {avg_aw:+7.2f}% / {avg_al:+7.2f}%")
        print(f"    Profit Factor:   {avg_pf:7.2f}")
        print(f"    Sharpe Ratio:    {avg_sharpe:7.2f}")
        print(f"    Max Drawdown:    {avg_mdd:7.1f}%")
        print(f"    Expected Value:  {avg_ev:+7.2f}%")
        print(f"    Kelly Criterion: {avg_kelly:7.2f}x")

        # Verdict
        score = sum([
            avg_wr >= 0.40,
            avg_pf >= 1.0,
            avg_sharpe >= 0.3,
            avg_mdd <= 25,
            avg_ev > 0
        ])

        if score >= 4:
            verdict = "✓ VIABLE FOR CLARITY ACT"
        elif score >= 3:
            verdict = "◐ MARGINAL - OPTIMIZATION NEEDED"
        else:
            verdict = "✗ NOT RECOMMENDED"

        print(f"    Verdict:         {verdict}")
        print(f"\n  Clarity Act Projection (40-day signing period):")
        print(f"    Expected Win Rate: {avg_wr:.1%}")
        print(f"    Expected Return:  {avg_ev:+.2f}% per trade")
        print(f"    Est. Total Trades: {max(1, int(40 / max(5, 40/total_trades)))}-{max(5, total_trades)} trades")
        print(f"    Est. Campaign Return: {avg_ev * max(1, int(40 / max(5, 40/total_trades))):+.2f}% to {avg_ev * total_trades:+.2f}%")

    # Save results
    output = {'results': results, 'metrics': all_metrics}
    with open('/Users/user/Desktop/trade/data/clarity_act_optimized_results.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n[✓] Results saved")


if __name__ == '__main__':
    main()
