#!/usr/bin/env python3
"""
Clarity Act Phase Strategy - Daily Monitor & Auto-Execute
Runs daily to check phase signals and execute paper trades.
Can be scheduled via Windows Task Scheduler or cron.

Usage:
  python clarity_phase_monitor.py                    # Check all pending events
  python clarity_phase_monitor.py --event 2026-06-15 # Check specific event
  python clarity_phase_monitor.py --status            # Show current positions
  python clarity_phase_monitor.py --history           # Show trade history
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('PhaseMonitor')

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(DATA_DIR, 'clarity_phase_positions.json')
HISTORY_FILE = os.path.join(DATA_DIR, 'clarity_phase_history.json')
EVENTS_FILE = os.path.join(DATA_DIR, 'clarity_phase_events.json')

# Known upcoming events (update as timeline evolves)
DEFAULT_EVENTS = {
    'committee_vote': '2026-05-14',
    'floor_vote_estimate': '2026-06-15',
    'signature_target': '2026-07-04',
}


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def get_active_events():
    events = load_json(EVENTS_FILE, DEFAULT_EVENTS)
    today = datetime.utcnow().date()
    active = {}
    for name, date_str in events.items():
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        if (d - today).days >= -5:
            active[name] = date_str
    return active


def check_and_execute(strategy, event_name, event_date):
    """Run all phase checks for an event and execute any signals"""
    from clarity_act_phase_strategy import PhaseStrategy

    df = strategy.ratio_tracker.fetch_daily_ratio(60)
    today = datetime.utcnow().date()
    positions = load_json(POSITIONS_FILE, {'phases': {}})
    any_action = False

    # Phase 1 excluded: no edge in backtest (WR=50%, EV=-0.02%, p=0.98)
    for phase_num in [2, 3]:
        phase_key = f'p{phase_num}_{event_name}'

        # Check exit first if position exists
        if phase_key in positions.get('phases', {}):
            entry = positions['phases'][phase_key]
            exit_fn = [None, strategy.phase1_exit_check,
                       strategy.phase2_exit_check,
                       strategy.phase3_exit_check][phase_num]
            exit_result = exit_fn(entry, df)

            if exit_result and exit_result.get('action') == 'EXIT':
                trade = strategy.log_trade(phase_num, 'EXIT', {
                    **exit_result,
                    'event': event_name,
                    'event_date': event_date,
                    'entry': entry,
                })
                del positions['phases'][phase_key]
                save_json(POSITIONS_FILE, positions)
                logger.info(f"Phase {phase_num} EXIT: {exit_result['reason']} "
                           f"PnL={exit_result['pnl_pct']:+.3f}% | "
                           f"Balance=${strategy.balance:.2f}")
                any_action = True
            else:
                pnl = exit_result.get('pnl_pct', 0) if exit_result else 0
                logger.info(f"Phase {phase_num} HOLD | PnL={pnl:+.3f}%")

        else:
            # Check entry
            check_fn = [None, strategy.phase1_check,
                        strategy.phase2_check,
                        strategy.phase3_check][phase_num]
            result = check_fn(event_date, df)

            if result and result.get('signal') == 'ENTER':
                pos = {
                    **result,
                    'event': event_name,
                    'event_date': event_date,
                    'entry_time': datetime.utcnow().isoformat(),
                }
                positions.setdefault('phases', {})[phase_key] = pos
                save_json(POSITIONS_FILE, positions)
                trade = strategy.log_trade(phase_num, 'ENTER', {
                    'event': event_name,
                    'direction': result.get('direction'),
                    'size_usd': result.get('position_size_usd'),
                    'ev': result.get('expected_ev'),
                })
                logger.info(f"Phase {phase_num} ENTER: {result.get('direction')} "
                           f"Size=${result.get('position_size_usd', 0):.2f} "
                           f"EV=+{result.get('expected_ev', 0):.2f}%")
                any_action = True

    return any_action


def show_status():
    positions = load_json(POSITIONS_FILE, {'phases': {}})
    history = load_json(HISTORY_FILE, [])

    print("=" * 70)
    print("CLARITY ACT PHASE STRATEGY - STATUS")
    print(f"Time: {datetime.utcnow().isoformat()}")
    print("=" * 70)

    if positions.get('phases'):
        print("\nOpen Positions:")
        for key, pos in positions['phases'].items():
            print(f"  {key}:")
            print(f"    Phase {pos.get('phase')} | {pos.get('name', '')}")
            print(f"    Direction: {pos.get('direction')} | Size: ${pos.get('position_size_usd', 0):.2f}")
            print(f"    Entry: {pos.get('entry_date')} | Ratio: {pos.get('entry_ratio', 'N/A')}")
            print(f"    Target Exit: {pos.get('target_exit_date', pos.get('max_hold_days', '?'))}")
    else:
        print("\nNo open positions.")

    if history:
        print(f"\nRecent Trades (last 10 of {len(history)}):")
        for t in history[-10:]:
            print(f"  {t['timestamp'][:19]} Phase {t['phase']} {t['action']} | "
                   f"{t.get('details', {}).get('direction', '')} "
                   f"PnL={t.get('details', {}).get('pnl_pct', 'N/A')}")

    balance = positions.get('balance', 190.0)
    print(f"\nBalance: ${balance:.2f}")


def show_history():
    history = load_json(HISTORY_FILE, [])
    if not history:
        print("No trade history.")
        return

    print("=" * 70)
    print("TRADE HISTORY")
    print("=" * 70)
    for t in history:
        d = t.get('details', {})
        print(f"{t['timestamp'][:19]} | Phase {t['phase']} {t['action']:5s} | "
               f"{d.get('event', ''):20s} | "
               f"Dir: {d.get('direction', 'N/A'):12s} | "
               f"PnL: {d.get('pnl_pct', 'N/A')}")
    print(f"\nTotal trades: {len(history)}")


def main():
    strategy_module = os.path.join(DATA_DIR, 'clarity_phase_strategy.py')
    sys.path.insert(0, DATA_DIR)
    from clarity_act_phase_strategy import PhaseStrategy

    # Load or create state
    positions = load_json(POSITIONS_FILE, {'phases': {}, 'balance': 190.0})
    history = load_json(HISTORY_FILE, [])
    strategy = PhaseStrategy(
        paper_trade=True,
        initial_balance=positions.get('balance', 190.0)
    )
    strategy.trade_log = history

    if '--status' in sys.argv:
        show_status()
        return

    if '--history' in sys.argv:
        show_history()
        return

    # Determine event date
    if '--event' in sys.argv:
        idx = sys.argv.index('--event')
        event_date = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if not event_date:
            print("Usage: --event YYYY-MM-DD")
            return
        events = {'manual': event_date}
    else:
        events = get_active_events()

    if not events:
        print("No active events. Update clarity_phase_events.json with event dates.")
        return

    print(f"\n{'=' * 70}")
    print(f"Clarity Act Phase Monitor | {datetime.utcnow().isoformat()}")
    print(f"Active events: {json.dumps(events)}")
    print(f"{'=' * 70}\n")

    for event_name, event_date in events.items():
        logger.info(f"Checking event: {event_name} ({event_date})")
        check_and_execute(strategy, event_name, event_date)

    # Update state
    positions['balance'] = strategy.balance
    save_json(POSITIONS_FILE, positions)
    save_json(HISTORY_FILE, strategy.trade_log)

    print(f"\nBalance: ${strategy.balance:.2f}")


if __name__ == '__main__':
    main()
