# -*- coding: utf-8 -*-
"""
Interactive Whale Candidate Collector
Manually collect wallets from Hyperliquid leaderboard for analysis
"""

import os, sys, json, time, logging
from datetime import datetime
from typing import Optional, List, Dict
import requests

def setup_logger(log_dir="logs", name="whale_collector"):
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{name}_{ts}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

class WhaleCollector:
    HL_API_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, logger=None):
        self.logger = logger or setup_logger()
        self.wallets = []

    def _raw_post(self, payload: dict, timeout: int = 10) -> Optional[dict]:
        try:
            resp = requests.post(self.HL_API_URL, json=payload, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self.logger.debug(f"API error: {e}")
        return None

    def validate_wallet(self, address: str) -> bool:
        """Validate wallet exists on Hyperliquid"""
        payload = {'type': 'clearinghouseState', 'user': address}
        return self._raw_post(payload) is not None

    def get_wallet_summary(self, address: str) -> Optional[dict]:
        """Get wallet summary"""
        payload = {'type': 'clearinghouseState', 'user': address}
        data = self._raw_post(payload)

        if not data:
            return None

        try:
            margin = data.get('marginSummary', {})
            account_value = float(margin.get('accountValue', 0))
            positions = data.get('assetPositions', [])
            active_pos = len([p for p in positions if float(p.get('position', {}).get('szi', 0)) != 0])

            # Get recent fills
            fills_payload = {'type': 'userFills', 'user': address}
            fills_data = self._raw_post(fills_payload)
            recent_trades = len(fills_data) if isinstance(fills_data, list) else 0

            return {
                'address': address,
                'account_value': account_value,
                'active_positions': active_pos,
                'recent_fills': recent_trades
            }
        except:
            return None

    def collect_interactive(self) -> List[dict]:
        """Interactive collection from user"""
        print("\n" + "="*80)
        print("INTERACTIVE WHALE CANDIDATE COLLECTOR")
        print("="*80)
        print("\nInstructions:")
        print("1. Visit: https://app.hyperliquid.xyz/leaderboard")
        print("2. Sort by ROI (descending) or Profit (descending)")
        print("3. Look for wallets with:")
        print("   - ROI > 20% (past 90 days)")
        print("   - Trades > 50-200")
        print("   - Account Value > $100k")
        print("4. Click on wallet row to copy address")
        print("5. Paste address below")
        print("6. Enter 'done' when finished")
        print("="*80)

        count = 0
        while True:
            count += 1
            prompt = f"\nWallet {count} address (or 'done' to finish): "

            try:
                address = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nCollection interrupted.")
                break

            if address.lower() == 'done':
                break

            if not address or not address.startswith('0x'):
                print("  [!] Invalid address (must start with 0x)")
                continue

            if len(address) != 42:
                print("  [!] Invalid address (must be 42 characters)")
                continue

            # Validate
            print(f"  [-] Validating {address[:16]}...", end='', flush=True)
            if not self.validate_wallet(address):
                print(" [X] Not found on Hyperliquid")
                continue

            # Get summary
            summary = self.get_wallet_summary(address)
            if summary:
                self.wallets.append(summary)
                av = summary['account_value']
                ap = summary['active_positions']
                rf = summary['recent_fills']
                print(f" [OK] Account: ${av:,.0f}, Positions: {ap}, Recent fills: {rf}")
            else:
                print(" [!] No data available")

        return self.wallets

    def save_to_file(self, filename: str = "collected_whales.json"):
        """Save collected wallets to file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.wallets, f, indent=2)
        print(f"\n[OK] Saved {len(self.wallets)} wallets to {filename}")
        return filename

    def generate_leaderboard_url_guide(self):
        """Generate guide for finding wallets"""
        guide = """
================================================================================
HYPERLIQUID LEADERBOARD WALLET COLLECTION GUIDE
================================================================================

STEP 1: OPEN LEADERBOARD
  URL: https://app.hyperliquid.xyz/leaderboard

STEP 2: FILTER AND SORT
  - Click on "ROI %" column header to sort descending
  - Look for traders with ROI > 20%
  - Check "Trades" column (should be > 50)
  - Check "Account Value" (should be > $100k)

STEP 3: COPY WALLET ADDRESS
  - Click on the trader's row
  - Address will be displayed or can be copied from URL
  - Paste into this script

STEP 4: IDEAL CANDIDATE PROFILE
  ROI:           20% - 200% (past 90 days)
  Trades:        50 - 500 (statistical significance)
  Account Value: $100k - $10M (not too large, not too small)
  Win Rate:      45% - 70% (consistent but not lucky)
  Recent Activity: Active in past 7 days

STEP 5: RED FLAGS (AVOID)
  ROI > 500% (likely one lucky trade or scam)
  Trades < 20 (insufficient sample size)
  Account Value < $10k (retail trader, not institutional)
  Account Value > $100M (market-moving whale, not followable)

================================================================================
"""
        print(guide)
        input("\nPress Enter to continue...")

def main():
    collector = WhaleCollector()

    # Show guide
    collector.generate_leaderboard_url_guide()

    # Collect wallets
    wallets = collector.collect_interactive()

    if not wallets:
        print("\n[!] No wallets collected. Exiting.")
        return

    # Save
    filename = collector.save_to_file("collected_whales.json")

    # Show summary
    print("\n" + "="*80)
    print("COLLECTION SUMMARY")
    print("="*80)
    print(f"Total wallets collected: {len(wallets)}")
    print("\nWallet details:")
    for i, w in enumerate(wallets, 1):
        print(f"  {i}. {w['address']}")
        print(f"     Account: ${w['account_value']:,.0f}")
        print(f"     Positions: {w['active_positions']}")
        print(f"     Recent fills: {w['recent_fills']}")

    print(f"\n[OK] Saved to {filename}")
    print("\nNext step: Run whale_candidate_scanner.py with these addresses")

if __name__ == "__main__":
    main()
