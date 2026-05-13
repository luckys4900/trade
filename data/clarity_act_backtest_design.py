#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clarity Act Signing Period Backtest Implementation

Purpose: Design and execute backtests for BTC/ETH trading strategies during
the ~40-day regulatory event window (committee pass → presidential signature)

Historical test cases:
1. FIT21: House pass 2024-05-22 → Expected signature July 4, 2024 (~43 days)
2. Other regulatory events (to be identified)

Strategy 1: Trend Following (MA-based)
- Entry: BTC/ETH close > MA(3) after vote confirmation
- Exit: 3-day consecutive decline OR signature date
- SL: Entry - 2×ATR(14) | TP: Entry + 3×ATR(14)

Strategy 2: Volatility Expansion (Mean-reversion)
- Entry: Vol > 120% of MA(30) in uptrend
- Exit: Vol < MA(30) OR signature date
- Dynamic position sizing based on volatility

Strategy 3: Pair Trading (BTC/ETH relative value)
- Entry: BTC/ETH ratio > MA(20) with uptrend
- Exit: Ratio breaks MA(20) OR signature date
- Track convergence/divergence patterns
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class ClarityActBacktester:
    """Backtest trading strategies for regulatory event windows"""

    def __init__(self):
        self.btc_data = None
        self.eth_data = None
        self.btc_eth_ratio = None

    def load_data(self, btc_path, eth_path):
        """Load BTC and ETH daily OHLCV data"""
        # Load BTC data
        self.btc_data = pd.read_csv(btc_path)
        self.btc_data['datetime'] = pd.to_datetime(self.btc_data['datetime'])
        self.btc_data = self.btc_data.sort_values('datetime').reset_index(drop=True)

        # Load ETH data (convert from 4h to daily if needed)
        eth_raw = pd.read_csv(eth_path)
        eth_raw['datetime'] = pd.to_datetime(eth_raw['datetime'])
        eth_raw = eth_raw.sort_values('datetime')

        # Aggregate 4h to daily
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

        print(f"[✓] BTC: {len(self.btc_data)} days ({self.btc_data['datetime'].min().date()} to {self.btc_data['datetime'].max().date()})")
        print(f"[✓] ETH: {len(self.eth_data)} days ({self.eth_data['datetime'].min().date()} to {self.eth_data['datetime'].max().date()})")

    def extract_event_period(self, event_date_str, duration_days=40):
        """Extract 40-day period from event date"""
        event_date = pd.to_datetime(event_date_str).date()
        start_date = event_date
        end_date = event_date + timedelta(days=duration_days)

        # Filter both datasets
        btc_period = self.btc_data[
            (self.btc_data['datetime'].dt.date >= start_date) &
            (self.btc_data['datetime'].dt.date <= end_date)
        ].reset_index(drop=True)

        eth_period = self.eth_data[
            (self.eth_data['datetime'].dt.date >= start_date) &
            (self.eth_data['datetime'].dt.date <= end_date)
        ].reset_index(drop=True)

        if len(btc_period) < duration_days:
            print(f"[!] Warning: Only {len(btc_period)} days available (expected {duration_days})")

        return btc_period, eth_period

    def calculate_indicators(self, df):
        """Calculate technical indicators"""
        df = df.copy()

        # Moving Averages
        df['ma3'] = df['close'].rolling(window=3, min_periods=1).mean()
        df['ma20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['ma30'] = df['close'].rolling(window=30, min_periods=1).mean()

        # ATR (Average True Range)
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr14'] = df['tr'].rolling(window=14, min_periods=1).mean()

        # Volatility (20-day rolling std of returns)
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20, min_periods=1).std() * 100
        df['vol_ma30'] = df['volatility'].rolling(window=30, min_periods=1).mean()

        return df

    def strategy1_trend_following(self, btc_df, entry_offset=1):
        """
        Strategy 1: Trend Following
        - Entry: Close > MA(3) for 3 consecutive days after vote
        - Exit: 3-day consecutive decline OR end of period
        - Risk Management: SL at Entry - 2×ATR, TP at Entry + 3×ATR
        """
        btc_df = self.calculate_indicators(btc_df).copy()

        trades = []
        in_position = False
        entry_price = None
        entry_idx = None
        consecutive_up = 0
        consecutive_down = 0

        for i in range(entry_offset, len(btc_df)):
            close = btc_df.loc[i, 'close']
            ma3 = btc_df.loc[i, 'ma3']
            atr = btc_df.loc[i, 'atr14']

            if not in_position:
                # Entry signal: 3 consecutive closes > MA3
                if close > ma3:
                    consecutive_up += 1
                else:
                    consecutive_up = 0

                if consecutive_up >= 3:
                    entry_price = close
                    entry_idx = i
                    sl = entry_price - 2 * atr
                    tp = entry_price + 3 * atr
                    in_position = True
                    consecutive_up = 0
                    consecutive_down = 0

            else:
                # Exit conditions
                exit_reason = None
                exit_price = close

                # Check stop loss
                if close <= sl:
                    exit_reason = 'SL'
                    exit_price = sl
                # Check take profit
                elif close >= tp:
                    exit_reason = 'TP'
                    exit_price = tp
                # Check 3-day consecutive decline
                else:
                    if close < btc_df.loc[i-1, 'close']:
                        consecutive_down += 1
                    else:
                        consecutive_down = 0

                    if consecutive_down >= 3:
                        exit_reason = '3D_DOWN'

                # Forced exit at end of period
                if i == len(btc_df) - 1 and in_position:
                    exit_reason = 'EOP'

                if exit_reason:
                    pnl = ((exit_price - entry_price) / entry_price) * 100
                    trades.append({
                        'entry_date': btc_df.loc[entry_idx, 'datetime'].date(),
                        'exit_date': btc_df.loc[i, 'datetime'].date(),
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl_pct': pnl,
                        'exit_reason': exit_reason,
                        'duration_days': i - entry_idx
                    })
                    in_position = False
                    consecutive_down = 0

        return trades

    def strategy2_volatility_expansion(self, btc_df, vol_threshold=1.20):
        """
        Strategy 2: Volatility Expansion
        - Entry: Volatility > 120% of 30-day MA, uptrend confirmation
        - Exit: Volatility < 30-day MA OR end of period
        - Position sizing: Increase with volatility
        """
        btc_df = self.calculate_indicators(btc_df).copy()

        trades = []
        in_position = False
        entry_price = None
        entry_idx = None

        for i in range(30, len(btc_df)):  # Need 30 days for vol MA
            vol = btc_df.loc[i, 'volatility']
            vol_ma = btc_df.loc[i, 'vol_ma30']
            close = btc_df.loc[i, 'close']
            prev_close = btc_df.loc[i-1, 'close']

            if not in_position:
                # Entry: Vol > 120% of MA, uptrend
                if vol > vol_ma * vol_threshold and close > prev_close:
                    entry_price = close
                    entry_idx = i
                    in_position = True
                    vol_entry = vol

            else:
                # Exit: Vol drops below MA
                exit_reason = None
                exit_price = close

                if vol < vol_ma:
                    exit_reason = 'VOL_DOWN'

                # Forced exit at end of period
                if i == len(btc_df) - 1 and in_position:
                    exit_reason = 'EOV'

                if exit_reason:
                    pnl = ((exit_price - entry_price) / entry_price) * 100
                    vol_expansion = vol / vol_ma
                    trades.append({
                        'entry_date': btc_df.loc[entry_idx, 'datetime'].date(),
                        'exit_date': btc_df.loc[i, 'datetime'].date(),
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl_pct': pnl,
                        'exit_reason': exit_reason,
                        'vol_expansion_ratio': vol_expansion,
                        'duration_days': i - entry_idx
                    })
                    in_position = False

        return trades

    def strategy3_pair_trading(self, btc_df, eth_df):
        """
        Strategy 3: Pair Trading (BTC/ETH relative value)
        - Entry: BTC/ETH ratio > MA(20) with uptrend
        - Exit: Ratio < MA(20) OR end of period
        - Captures relative performance differences
        """
        # Calculate ratio
        btc_copy = btc_df.copy()
        eth_copy = eth_df.copy()

        # Align dates
        common_dates = pd.to_datetime(btc_copy['datetime'].dt.date).isin(
            pd.to_datetime(eth_copy['datetime'].dt.date)
        )
        btc_copy = btc_copy[common_dates].reset_index(drop=True)

        common_dates = pd.to_datetime(eth_copy['datetime'].dt.date).isin(
            pd.to_datetime(btc_copy['datetime'].dt.date)
        )
        eth_copy = eth_copy[common_dates].reset_index(drop=True)

        # Calculate BTC/ETH ratio
        ratio = btc_copy['close'] / eth_copy['close']
        ratio_ma20 = ratio.rolling(window=20, min_periods=1).mean()

        trades = []
        in_position = False
        entry_ratio = None
        entry_idx = None

        for i in range(20, len(ratio)):
            current_ratio = ratio.iloc[i]
            ma20 = ratio_ma20.iloc[i]
            prev_ratio = ratio.iloc[i-1]

            if not in_position:
                # Entry: Ratio > MA20, uptrend
                if current_ratio > ma20 and current_ratio > prev_ratio:
                    entry_ratio = current_ratio
                    entry_idx = i
                    in_position = True
            else:
                # Exit: Ratio < MA20
                exit_reason = None

                if current_ratio < ma20:
                    exit_reason = 'RATIO_DOWN'

                # Forced exit at end
                if i == len(ratio) - 1 and in_position:
                    exit_reason = 'EOP'

                if exit_reason:
                    exit_ratio = current_ratio
                    pnl = ((exit_ratio - entry_ratio) / entry_ratio) * 100
                    trades.append({
                        'entry_date': btc_copy.loc[entry_idx, 'datetime'].date(),
                        'exit_date': btc_copy.loc[i, 'datetime'].date(),
                        'entry_ratio': entry_ratio,
                        'exit_ratio': exit_ratio,
                        'pnl_pct': pnl,
                        'exit_reason': exit_reason,
                        'duration_days': i - entry_idx
                    })
                    in_position = False

        return trades

    def calculate_metrics(self, trades):
        """Calculate performance metrics for a strategy"""
        if not trades:
            return None

        trades_df = pd.DataFrame(trades)

        # Basic metrics
        num_trades = len(trades_df)
        winning_trades = trades_df[trades_df['pnl_pct'] > 0]
        losing_trades = trades_df[trades_df['pnl_pct'] < 0]

        win_rate = len(winning_trades) / num_trades if num_trades > 0 else 0

        avg_win = winning_trades['pnl_pct'].mean() if len(winning_trades) > 0 else 0
        avg_loss = abs(losing_trades['pnl_pct'].mean()) if len(losing_trades) > 0 else 0

        total_profit = winning_trades['pnl_pct'].sum() if len(winning_trades) > 0 else 0
        total_loss = losing_trades['pnl_pct'].sum() if len(losing_trades) > 0 else 0

        profit_factor = total_profit / total_loss if total_loss != 0 else 0

        # Sharpe Ratio
        returns = trades_df['pnl_pct'].values
        if len(returns) > 1:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
        else:
            sharpe = 0

        # Max Drawdown
        cumulative_pnl = 0
        peak = 0
        max_dd = 0
        for ret in returns:
            cumulative_pnl += ret
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = peak - cumulative_pnl
            if dd > max_dd:
                max_dd = dd

        # Expected Value
        ev = (win_rate * avg_win) - ((1 - win_rate) * avg_loss) if num_trades > 0 else 0

        # Kelly Criterion
        kelly = (win_rate * avg_win) / avg_loss if avg_loss > 0 else 0

        return {
            'num_trades': num_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_return': returns.sum(),
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'expected_value': ev,
            'kelly_criterion': kelly,
            'avg_duration_days': trades_df['duration_days'].mean()
        }

    def backtest_fit21_event(self):
        """Backtest using FIT21 House Pass as test case"""
        print("\n" + "="*80)
        print("FIT21 HOUSE PASS EVENT BACKTEST (2024-05-22)")
        print("="*80 + "\n")

        # Extract 40-day period from FIT21 House pass
        btc_period, eth_period = self.extract_event_period('2024-05-22', duration_days=40)

        if len(btc_period) < 20:
            print("[!] Insufficient data for FIT21 backtest")
            return None

        results = {}

        # Strategy 1: Trend Following
        print("[Strategy 1] Trend Following...")
        trades1 = self.strategy1_trend_following(btc_period, entry_offset=3)
        metrics1 = self.calculate_metrics(trades1)
        results['strategy1_trend'] = {
            'trades': trades1,
            'metrics': metrics1
        }

        if metrics1:
            print(f"  Trades: {metrics1['num_trades']}")
            print(f"  Win Rate: {metrics1['win_rate']:.1%}")
            print(f"  Avg Win: {metrics1['avg_win']:+.2f}% | Avg Loss: {metrics1['avg_loss']:+.2f}%")
            print(f"  Profit Factor: {metrics1['profit_factor']:.2f}")
            print(f"  Sharpe Ratio: {metrics1['sharpe_ratio']:.2f}")
            print(f"  Max Drawdown: {metrics1['max_drawdown']:.2f}%")
            print(f"  Expected Value: {metrics1['expected_value']:+.2f}%")
        print()

        # Strategy 2: Volatility Expansion
        print("[Strategy 2] Volatility Expansion...")
        trades2 = self.strategy2_volatility_expansion(btc_period, vol_threshold=1.20)
        metrics2 = self.calculate_metrics(trades2)
        results['strategy2_volatility'] = {
            'trades': trades2,
            'metrics': metrics2
        }

        if metrics2:
            print(f"  Trades: {metrics2['num_trades']}")
            print(f"  Win Rate: {metrics2['win_rate']:.1%}")
            print(f"  Avg Win: {metrics2['avg_win']:+.2f}% | Avg Loss: {metrics2['avg_loss']:+.2f}%")
            print(f"  Profit Factor: {metrics2['profit_factor']:.2f}")
            print(f"  Sharpe Ratio: {metrics2['sharpe_ratio']:.2f}")
            print(f"  Max Drawdown: {metrics2['max_drawdown']:.2f}%")
            print(f"  Expected Value: {metrics2['expected_value']:+.2f}%")
        print()

        # Strategy 3: Pair Trading
        print("[Strategy 3] Pair Trading (BTC/ETH)...")
        trades3 = self.strategy3_pair_trading(btc_period, eth_period)
        metrics3 = self.calculate_metrics(trades3)
        results['strategy3_pairs'] = {
            'trades': trades3,
            'metrics': metrics3
        }

        if metrics3:
            print(f"  Trades: {metrics3['num_trades']}")
            print(f"  Win Rate: {metrics3['win_rate']:.1%}")
            print(f"  Avg Win: {metrics3['avg_win']:+.2f}% | Avg Loss: {metrics3['avg_loss']:+.2f}%")
            print(f"  Profit Factor: {metrics3['profit_factor']:.2f}")
            print(f"  Sharpe Ratio: {metrics3['sharpe_ratio']:.2f}")
            print(f"  Max Drawdown: {metrics3['max_drawdown']:.2f}%")
            print(f"  Expected Value: {metrics3['expected_value']:+.2f}%")
        print()

        return results

    def generate_report(self, results):
        """Generate comprehensive backtest report"""
        print("\n" + "="*80)
        print("CLARITY ACT BACKTEST REPORT - FIT21 TEST CASE")
        print("="*80 + "\n")

        print("STRATEGY EVALUATION")
        print("-" * 80)
        print()

        strategies = [
            ('Strategy 1 (Trend Following)', 'strategy1_trend'),
            ('Strategy 2 (Volatility Expansion)', 'strategy2_volatility'),
            ('Strategy 3 (Pair Trading)', 'strategy3_pairs')
        ]

        summary = []

        for name, key in strategies:
            if key not in results or results[key]['metrics'] is None:
                continue

            metrics = results[key]['metrics']

            print(f"{name}:")
            print(f"  Win Rate:        {metrics['win_rate']:7.1%}")
            print(f"  Avg Win/Loss:    {metrics['avg_win']:+7.2f}% / {metrics['avg_loss']:+7.2f}%")
            print(f"  Profit Factor:   {metrics['profit_factor']:7.2f}")
            print(f"  Sharpe Ratio:    {metrics['sharpe_ratio']:7.2f}")
            print(f"  Max Drawdown:    {metrics['max_drawdown']:7.2f}%")
            print(f"  Expected Value:  {metrics['expected_value']:+7.2f}%")
            print(f"  Total Return:    {metrics['total_return']:+7.2f}%")
            print(f"  Trades:          {metrics['num_trades']:7d}")
            print(f"  Avg Duration:    {metrics['avg_duration_days']:7.1f} days")

            # Verdict
            verdict = self._evaluate_strategy(metrics)
            print(f"  Verdict:         {verdict}")
            print()

            summary.append({
                'strategy': name,
                'metrics': metrics,
                'verdict': verdict
            })

        return summary

    def _evaluate_strategy(self, metrics):
        """Evaluate if strategy is implementable"""
        if metrics['num_trades'] < 1:
            return "SKIP (no trades)"

        checks = []

        if metrics['win_rate'] >= 0.40:
            checks.append(True)
        else:
            checks.append(False)

        if metrics['profit_factor'] >= 1.0:
            checks.append(True)
        else:
            checks.append(False)

        if metrics['sharpe_ratio'] >= 0.5:
            checks.append(True)
        else:
            checks.append(False)

        if metrics['max_drawdown'] <= 30:
            checks.append(True)
        else:
            checks.append(False)

        if metrics['expected_value'] > 0:
            checks.append(True)
        else:
            checks.append(False)

        passed = sum(checks)
        total = len(checks)

        if passed >= 4:
            return f"✓ IMPLEMENTABLE ({passed}/{total} criteria)"
        elif passed >= 3:
            return f"◐ MARGINAL ({passed}/{total} criteria)"
        else:
            return f"✗ NOT VIABLE ({passed}/{total} criteria)"


def main():
    backtester = ClarityActBacktester()

    # Load data
    print("="*80)
    print("CLARITY ACT REGULATORY EVENT BACKTEST")
    print("Design: Trading Strategies for ~40-day Signing Period")
    print("="*80 + "\n")

    btc_path = '/Users/user/Desktop/trade/data/btc_price_1d_extended.csv'
    eth_path = '/Users/user/Desktop/trade/data/ETH_USDT_4h_730d.csv'

    backtester.load_data(btc_path, eth_path)

    # Run FIT21 backtest as historical test case
    results = backtester.backtest_fit21_event()

    # Generate report
    summary = backtester.generate_report(results)

    # Save results
    output_path = '/Users/user/Desktop/trade/data/clarity_act_backtest_results.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n[✓] Results saved to {output_path}")

    return summary


if __name__ == '__main__':
    main()
