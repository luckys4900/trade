#!/usr/bin/env python3
"""
Verify that Kronos is actually being applied to trades in real-time.
Run this in a terminal to watch for the next trading signal.
"""

import json
import os
import time
from datetime import datetime

def check_latest_trade():
    """Check if the latest trade has Kronos applied"""

    log_file = None

    # Find the latest unified_live log
    logs_dir = 'logs'
    if os.path.exists(logs_dir):
        log_files = [f for f in os.listdir(logs_dir) if f.startswith('unified_live_') and f.endswith('.log')]
        if log_files:
            log_file = os.path.join(logs_dir, sorted(log_files)[-1])

    print("="*80)
    print("KRONOS LIVE VERIFICATION")
    print("="*80)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print(f"Monitoring log: {log_file}")
    print("\nWaiting for next trading signal...")
    print("(This script will detect when an OCPM/MR/RSISwing signal is triggered)")
    print("-"*80)

    last_line_count = 0

    while True:
        try:
            # Read alignment log to check for new trades
            if os.path.exists('trade_alignment_log.json'):
                with open('trade_alignment_log.json') as f:
                    trades = json.load(f)

                # Check if new trade added
                if len(trades) > last_line_count:
                    new_trade = trades[-1]
                    last_line_count = len(trades)

                    print(f"\n[NEW TRADE #{len(trades)}] {new_trade.get('ts')}")
                    print(f"  Strategy: {new_trade.get('strategy')}")
                    print(f"  Direction: {new_trade.get('direction')}")
                    print(f"  Entry Price: ${new_trade.get('entry_px', 0):.2f}")

                    # Check Kronos fields
                    kronos_dir = new_trade.get('kronos_direction')
                    kronos_prob = new_trade.get('kronos_prob_up')
                    kronos_mult = new_trade.get('kronos_multiplier')
                    kronos_aligned = new_trade.get('kronos_aligned')

                    print(f"\n  [KRONOS DATA]")
                    print(f"    Direction: {kronos_dir}")
                    print(f"    Prob UP: {kronos_prob}")
                    print(f"    Multiplier: {kronos_mult}")
                    print(f"    Aligned: {kronos_aligned}")

                    # Check if Kronos was actually applied
                    if kronos_mult is not None and kronos_mult != 1.0:
                        print(f"\n  >>> KRONOS ACTIVE: Size adjusted by {kronos_mult:.2f}x")
                        if kronos_aligned:
                            print(f"      Both signals agree - FULL CONFIDENCE")
                        else:
                            print(f"      Signals disagree - SIZE REDUCED")
                    else:
                        print(f"\n  >>> KRONOS NEUTRAL: No size adjustment")

                    print("-"*80)

            time.sleep(5)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    check_latest_trade()
