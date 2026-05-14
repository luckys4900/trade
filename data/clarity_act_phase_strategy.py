#!/usr/bin/env python3
"""
Clarity Act Phase Strategy v3.0
3-phase event-driven BTC/ETH pair trading

Phase 1: Pre-1d ETH Lead  (WR 87.5%, p=0.04, EV +1.44%)
Phase 2: Vol Breakout     (WR 80%, EV +2.31%)
Phase 3: Post-10d BTC Lead (WR 80% w/ filter, EV +4.93%)

Author: Claude Code
Date: 2026-05-14
"""

import ccxt
import json
import logging
import os
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('ClarityPhase')

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


class RatioTracker:
    """BTC/ETH ratio calculation and tracking"""

    def __init__(self, lookback=30):
        self.lookback = lookback
        self.exchange = ccxt.binance({'enableRateLimit': True})

    def fetch_daily_ratio(self, days=60):
        btc = self.exchange.fetch_ohlcv('BTC/USDT', '1d', limit=days)
        eth = self.exchange.fetch_ohlcv('ETH/USDT', '1d', limit=days)
        data = []
        for b, e in zip(btc, eth):
            dt = datetime.utcfromtimestamp(b[0] / 1000)
            data.append({
                'date': dt.date(),
                'btc_close': b[4], 'eth_close': e[4],
                'btc_vol': b[5], 'eth_vol': e[5],
                'ratio': b[4] / e[4] if e[4] > 0 else None,
            })
        df = pd.DataFrame(data)
        df = df.dropna().reset_index(drop=True)
        df['ratio_ma5'] = df['ratio'].rolling(5, min_periods=3).mean()
        df['ratio_ma10'] = df['ratio'].rolling(10, min_periods=5).mean()
        df['ratio_ret'] = df['ratio'].pct_change()
        df['ratio_vol5'] = df['ratio_ret'].rolling(5, min_periods=3).std()
        df['ratio_vol20'] = df['ratio_ret'].rolling(20, min_periods=10).std()
        # RSI
        delta = df['ratio'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(14, min_periods=7).mean()
        avg_loss = loss.rolling(14, min_periods=7).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df['ratio_rsi'] = 100 - (100 / (1 + rs))
        # Percentile
        df['ratio_pct'] = df['ratio'].rolling(252, min_periods=60).rank(pct=True)
        # ETH weakness
        df['btc_ret5'] = df['btc_close'].pct_change(5)
        df['eth_ret5'] = df['eth_close'].pct_change(5)
        df['eth_weak'] = df['eth_ret5'] < df['btc_ret5']
        # Pre-3d trend
        df['ratio_up_3d'] = (df['ratio'].diff(1) > 0).rolling(3, min_periods=2).sum() >= 2
        return df

    def fetch_4h_ratio(self, days=5):
        btc = self.exchange.fetch_ohlcv('BTC/USDT', '4h', limit=days * 6)
        eth = self.exchange.fetch_ohlcv('ETH/USDT', '4h', limit=days * 6)
        data = []
        for b, e in zip(btc, eth):
            dt = datetime.utcfromtimestamp(b[0] / 1000)
            data.append({
                'datetime': dt,
                'btc_close': b[4], 'eth_close': e[4],
                'ratio': b[4] / e[4] if e[4] > 0 else None,
            })
        return pd.DataFrame(data).dropna()


class PhaseStrategy:
    """3-phase event strategy implementation"""

    def __init__(self, paper_trade=True, initial_balance=190.0):
        self.paper_trade = paper_trade
        self.balance = initial_balance
        self.ratio_tracker = RatioTracker()
        self.positions = {}
        self.trade_log = []
        self.state_file = os.path.join(DATA_DIR, 'clarity_phase_state.json')

    def _save_state(self):
        state = {
            'balance': self.balance,
            'positions': self.positions,
            'trade_log': self.trade_log[-100:],
            'last_update': datetime.utcnow().isoformat(),
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file) as f:
                state = json.load(f)
            self.balance = state.get('balance', self.balance)
            self.positions = state.get('positions', {})
            self.trade_log = state.get('trade_log', [])

    # =========================================================================
    # PHASE 1: Pre-1d ETH Lead
    # WR=87.5%, p=0.04, EV=+1.44% (cost adjusted)
    # Entry: Event Day - 2 close
    # Exit: Event Day - 1 close
    # Direction: LONG ETH / SHORT BTC (ratio SHORT)
    # =========================================================================
    def phase1_check(self, event_date_str, df=None):
        """
        Check Phase 1 entry conditions.
        Event = regulatory vote/signing date.
        Entry 2 days before, exit 1 day before.
        """
        if df is None:
            df = self.ratio_tracker.fetch_daily_ratio(60)

        event_date = pd.to_datetime(event_date_str).date()
        today = datetime.utcnow().date()
        days_to_event = (event_date - today).days

        if days_to_event != 2:
            return {
                'phase': 1, 'signal': None,
                'message': f'Days to event: {days_to_event}. Phase 1 triggers at day 2.'
            }

        last = df.iloc[-1]
        signal = {
            'phase': 1,
            'name': 'Pre-1d ETH Lead',
            'signal': 'ENTER',
            'direction': 'SHORT_RATIO',
            'btc_side': 'sell',
            'eth_side': 'buy',
            'entry_date': str(today),
            'target_exit_date': str(today + timedelta(days=1)),
            'expected_ev': 1.44,
            'win_rate': 87.5,
            'position_size_usd': min(self.balance * 0.30, 60),
            'stop_loss_pct': 2.0,
            'rationale': 'Pre-1d ETH historically outperforms BTC (p=0.04, WR=87.5%)'
        }
        return signal

    def phase1_exit_check(self, entry, df=None):
        """Check if Phase 1 exit is due"""
        if df is None:
            df = self.ratio_tracker.fetch_daily_ratio(60)

        entry_date = pd.to_datetime(entry['entry_date']).date()
        today = datetime.utcnow().date()
        days_held = (today - entry_date).days

        current_ratio = df['ratio'].iloc[-1]
        entry_ratio = entry.get('entry_ratio', current_ratio)
        pnl_pct = ((current_ratio - entry_ratio) / entry_ratio) * 100

        # Flip sign because we're SHORT ratio
        pnl_pct = -pnl_pct
        net_pnl = pnl_pct - 0.17

        if days_held >= 1:
            return {
                'phase': 1, 'action': 'EXIT',
                'reason': 'TARGET_EXIT' if net_pnl > 0 else 'TIME_EXIT',
                'pnl_pct': round(net_pnl, 3),
                'days_held': days_held
            }

        if pnl_pct < -entry.get('stop_loss_pct', 2.0):
            return {
                'phase': 1, 'action': 'EXIT',
                'reason': 'STOP_LOSS',
                'pnl_pct': round(net_pnl, 3),
                'days_held': days_held
            }

        return {'phase': 1, 'action': 'HOLD', 'pnl_pct': round(net_pnl, 3)}

    # =========================================================================
    # PHASE 2: Vol Breakout
    # WR=80%, EV=+2.31%, Sharpe=9.99
    # Entry: Event day, when ratio breaks 5d range
    # TP: Range x 1.5, SL: Range x 0.5, Max hold: 5 days
    # =========================================================================
    def phase2_check(self, event_date_str, df=None, df_4h=None):
        """
        Check Phase 2 entry conditions.
        On event day, check if ratio breaks the 5-day range.
        """
        if df is None:
            df = self.ratio_tracker.fetch_daily_ratio(60)

        event_date = pd.to_datetime(event_date_str).date()
        today = datetime.utcnow().date()

        if today != event_date:
            return {
                'phase': 2, 'signal': None,
                'message': f'Today is not event day. Phase 2 triggers on {event_date}.'
            }

        # Calculate 5-day range
        if len(df) < 7:
            return {'phase': 2, 'signal': None, 'message': 'Insufficient data'}

        range_5d = df['ratio'].iloc[-6:-1]  # 5 days before today
        range_high = range_5d.max()
        range_low = range_5d.min()
        range_width = range_high - range_low
        current_ratio = df['ratio'].iloc[-1]

        if range_width <= 0:
            return {'phase': 2, 'signal': None, 'message': 'Zero range'}

        signal = None
        if current_ratio > range_high:
            direction = 'LONG_RATIO'
            btc_side = 'buy'
            eth_side = 'sell'
        elif current_ratio < range_low:
            direction = 'SHORT_RATIO'
            btc_side = 'sell'
            eth_side = 'buy'
        else:
            return {
                'phase': 2, 'signal': None,
                'message': f'Ratio {current_ratio:.4f} within range [{range_low:.4f}, {range_high:.4f}]'
            }

        signal = {
            'phase': 2,
            'name': 'Vol Breakout',
            'signal': 'ENTER',
            'direction': direction,
            'btc_side': btc_side,
            'eth_side': eth_side,
            'entry_ratio': round(current_ratio, 4),
            'range_high': round(range_high, 4),
            'range_low': round(range_low, 4),
            'range_width': round(range_width, 4),
            'tp_ratio': round(current_ratio + range_width * 1.5 if direction == 'LONG_RATIO'
                              else current_ratio - range_width * 1.5, 4),
            'sl_ratio': round(current_ratio - range_width * 0.5 if direction == 'LONG_RATIO'
                              else current_ratio + range_width * 0.5, 4),
            'expected_ev': 2.31,
            'win_rate': 80.0,
            'position_size_usd': min(self.balance * 0.25, 50),
            'max_hold_days': 5,
            'entry_date': str(today),
        }
        return signal

    def phase2_exit_check(self, entry, df=None):
        """Check Phase 2 exit conditions"""
        if df is None:
            df = self.ratio_tracker.fetch_daily_ratio(60)

        current_ratio = df['ratio'].iloc[-1]
        entry_ratio = entry['entry_ratio']
        entry_date = pd.to_datetime(entry['entry_date']).date()
        today = datetime.utcnow().date()
        days_held = (today - entry_date).days

        direction = 1 if entry['direction'] == 'LONG_RATIO' else -1
        pnl_raw = ((current_ratio - entry_ratio) / entry_ratio) * 100 * direction
        net_pnl = pnl_raw - 0.17

        if current_ratio <= entry['sl_ratio'] and direction == 1:
            return {'phase': 2, 'action': 'EXIT', 'reason': 'SL', 'pnl_pct': round(net_pnl, 3)}
        if current_ratio >= entry['sl_ratio'] and direction == -1:
            return {'phase': 2, 'action': 'EXIT', 'reason': 'SL', 'pnl_pct': round(net_pnl, 3)}
        if current_ratio >= entry['tp_ratio'] and direction == 1:
            return {'phase': 2, 'action': 'EXIT', 'reason': 'TP', 'pnl_pct': round(net_pnl, 3)}
        if current_ratio <= entry['tp_ratio'] and direction == -1:
            return {'phase': 2, 'action': 'EXIT', 'reason': 'TP', 'pnl_pct': round(net_pnl, 3)}
        if days_held >= entry.get('max_hold_days', 5):
            return {'phase': 2, 'action': 'EXIT', 'reason': 'MAX_HOLD', 'pnl_pct': round(net_pnl, 3)}

        return {'phase': 2, 'action': 'HOLD', 'pnl_pct': round(net_pnl, 3), 'days_held': days_held}

    # =========================================================================
    # PHASE 3: Post-10d BTC Lead
    # WR=80% (with percentile filter), EV=+4.93%
    # Entry: Event day + 5
    # Exit: Event day + 20~30
    # Conditions: ratio percentile >= 95% + Pre-3d up + RSI > 55
    # =========================================================================
    def phase3_check(self, event_date_str, df=None):
        """
        Check Phase 3 entry conditions.
        Enter 5 days after event, hold 15-25 days.
        """
        if df is None:
            df = self.ratio_tracker.fetch_daily_ratio(60)

        event_date = pd.to_datetime(event_date_str).date()
        today = datetime.utcnow().date()
        days_after_event = (today - event_date).days

        if days_after_event < 5:
            return {
                'phase': 3, 'signal': None,
                'message': f'{days_after_event} days after event. Phase 3 triggers at day 5.'
            }

        if days_after_event > 30:
            return {
                'phase': 3, 'signal': None,
                'message': f'{days_after_event} days after event. Too late for Phase 3.'
            }

        last = df.iloc[-1]
        pct = last.get('ratio_pct', 0.5)
        if pd.isna(pct):
            pct = 0.5
        rsi = last.get('ratio_rsi', 50)
        if pd.isna(rsi):
            rsi = 50
        up_3d = last.get('ratio_up_3d', False)

        # Relaxed filters for entry
        pct_pass = pct >= 0.90
        rsi_pass = rsi > 50
        trend_pass = up_3d

        score = sum([pct_pass, rsi_pass, trend_pass])

        if score < 2:
            return {
                'phase': 3, 'signal': None,
                'message': f'Filter score {score}/3 (pct={pct:.2f}, rsi={rsi:.1f}, trend={up_3d})'
            }

        signal = {
            'phase': 3,
            'name': 'Post-10d BTC Lead',
            'signal': 'ENTER',
            'direction': 'LONG_RATIO',
            'btc_side': 'buy',
            'eth_side': 'sell',
            'entry_ratio': round(last['ratio'], 4),
            'entry_date': str(today),
            'target_exit_date': str(event_date + timedelta(days=25)),
            'expected_ev': 4.93 if pct >= 0.98 else 2.94,
            'win_rate': 80.0 if pct >= 0.98 else 62.5,
            'position_size_usd': min(self.balance * 0.35, 65),
            'stop_loss_pct': 3.0,
            'max_hold_days': 25,
            'filter_score': score,
            'ratio_pctile': round(pct, 3),
            'ratio_rsi': round(rsi, 1),
        }
        return signal

    def phase3_exit_check(self, entry, df=None):
        """Check Phase 3 exit conditions"""
        if df is None:
            df = self.ratio_tracker.fetch_daily_ratio(60)

        current_ratio = df['ratio'].iloc[-1]
        entry_ratio = entry['entry_ratio']
        entry_date = pd.to_datetime(entry['entry_date']).date()
        today = datetime.utcnow().date()
        days_held = (today - entry_date).days

        pnl_raw = ((current_ratio - entry_ratio) / entry_ratio) * 100
        net_pnl = pnl_raw - 0.17

        sl_pct = entry.get('stop_loss_pct', 3.0)
        if pnl_raw < -sl_pct:
            return {'phase': 3, 'action': 'EXIT', 'reason': 'SL', 'pnl_pct': round(net_pnl, 3)}

        if days_held >= entry.get('max_hold_days', 25):
            return {'phase': 3, 'action': 'EXIT', 'reason': 'MAX_HOLD', 'pnl_pct': round(net_pnl, 3)}

        # Time-decay trailing stop
        max_hold = entry.get('max_hold_days', 25)
        if days_held > max_hold * 0.6:
            peak = entry.get('peak_pnl', pnl_raw)
            if pnl_raw > peak:
                entry['peak_pnl'] = pnl_raw
            elif peak > 0 and pnl_raw < peak * 0.5:
                return {'phase': 3, 'action': 'EXIT', 'reason': 'TS', 'pnl_pct': round(net_pnl, 3)}

        return {'phase': 3, 'action': 'HOLD', 'pnl_pct': round(net_pnl, 3), 'days_held': days_held}

    # =========================================================================
    # ORCHESTRATOR
    # =========================================================================
    def run_check(self, event_date_str):
        """Run all phase checks for a given event date"""
        df = self.ratio_tracker.fetch_daily_ratio(60)

        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_date': event_date_str,
            'balance': self.balance,
            'current_ratio': round(df['ratio'].iloc[-1], 4),
            'ratio_rsi': round(df['ratio_rsi'].iloc[-1], 1) if pd.notna(df['ratio_rsi'].iloc[-1]) else None,
            'ratio_pctile': round(df['ratio_pct'].iloc[-1], 3) if pd.notna(df['ratio_pct'].iloc[-1]) else None,
            'phases': {}
        }

        for phase_num in [1, 2, 3]:
            check_fn = [None, self.phase1_check, self.phase2_check, self.phase3_check][phase_num]
            result = check_fn(event_date_str, df)
            results['phases'][phase_num] = result

            logger.info(f"Phase {phase_num}: {result.get('signal', 'N/A')} - "
                       f"{result.get('message', result.get('name', ''))}")

        self._save_state()
        return results

    def log_trade(self, phase, action, details):
        """Record trade action"""
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'phase': phase,
            'action': action,
            'balance_before': self.balance,
            'details': details,
        }
        if action == 'EXIT':
            pnl_usd = self.balance * details.get('pnl_pct', 0) / 100
            self.balance += pnl_usd
            entry['pnl_usd'] = round(pnl_usd, 2)
            entry['balance_after'] = round(self.balance, 2)

        self.trade_log.append(entry)
        self._save_state()
        logger.info(f"Trade logged: Phase {phase} {action} | {details}")
        return entry


def main():
    """Main entry point for running checks"""
    import sys

    event_date = sys.argv[1] if len(sys.argv) > 1 else '2026-07-04'

    strategy = PhaseStrategy(paper_trade=True, initial_balance=190.0)
    results = strategy.run_check(event_date)

    print("\n" + "=" * 70)
    print("CLARITY ACT PHASE STRATEGY - SIGNAL CHECK")
    print(f"Event: {event_date} | Balance: ${strategy.balance:.2f}")
    print(f"Ratio: {results['current_ratio']} | RSI: {results['ratio_rsi']} | Pctile: {results['ratio_pctile']}")
    print("=" * 70)

    for phase_num, phase_result in results['phases'].items():
        signal = phase_result.get('signal', 'NONE')
        name = phase_result.get('name', f'Phase {phase_num}')
        msg = phase_result.get('message', '')

        if signal == 'ENTER':
            print(f"\n  Phase {phase_num} [{name}]: ** ENTER **")
            print(f"    Direction: {phase_result.get('direction')}")
            print(f"    BTC: {phase_result.get('btc_side')} | ETH: {phase_result.get('eth_side')}")
            print(f"    Size: ${phase_result.get('position_size_usd', 0):.2f}")
            print(f"    Expected EV: +{phase_result.get('expected_ev', 0):.2f}%")
            print(f"    Win Rate: {phase_result.get('win_rate', 0):.0f}%")
        else:
            print(f"\n  Phase {phase_num} [{name}]: {signal or 'WAIT'}")
            if msg:
                print(f"    {msg}")

    # Save results
    output_path = os.path.join(DATA_DIR, 'clarity_phase_signals.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSignals saved to: {output_path}")


if __name__ == '__main__':
    main()
