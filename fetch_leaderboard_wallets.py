# -*- coding: utf-8 -*-
"""
Setup Whale Wallets - Interactive wallet configuration
Allows manual entry or API fetch of Hyperliquid top wallets
"""

import os, sys, json, time, logging
from datetime import datetime
from typing import Optional, List, Dict
import requests

# ==================================================================
# LOGGER SETUP
# ==================================================================

def setup_logger(log_dir="logs", name="fetch_leaderboard"):
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

# ==================================================================
# WALLET SETUP
# ==================================================================

class WalletSetup:
    HL_API_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, logger=None):
        self.logger = logger or setup_logger()

    def _raw_post(self, payload: dict, timeout: int = 10) -> Optional[dict]:
        """POST to Hyperliquid info endpoint"""
        try:
            resp = requests.post(self.HL_API_URL, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            else:
                self.logger.debug(f"HL API returned {resp.status_code}")
                return None
        except Exception as e:
            self.logger.debug(f"HL API error: {e}")
            return None

    def validate_wallet(self, address: str) -> bool:
        """
        Validate that wallet address exists on Hyperliquid.
        Attempts to fetch clearinghouseState for given address.
        """
        payload = {'type': 'clearinghouseState', 'user': address}
        data = self._raw_post(payload)
        return data is not None

    def get_wallet_stats(self, address: str) -> Optional[dict]:
        """Fetch wallet stats to display"""
        payload = {'type': 'clearinghouseState', 'user': address}
        data = self._raw_post(payload)

        if not data:
            return None

        try:
            margin = data.get('marginSummary', {})
            account_value = float(margin.get('accountValue', 0))
            positions = data.get('assetPositions', [])
            active_pos = len([p for p in positions if float(p.get('position', {}).get('szi', 0)) != 0])

            return {
                'address': address,
                'account_value': account_value,
                'active_positions': active_pos
            }
        except:
            return None

    def prompt_wallet_entry(self) -> List[dict]:
        """
        Interactive prompt for manual wallet entry.
        User can paste wallet addresses from Hyperliquid leaderboard.
        """
        wallets = []

        print("\n" + "="*70)
        print("WHALE WALLET SETUP - Manual Entry")
        print("="*70)
        print("\nInstructions:")
        print("1. Visit: https://app.hyperliquid.xyz/leaderboard")
        print("2. Identify 6-10 top performers by ROI or PnL")
        print("3. Copy wallet addresses and paste below")
        print("4. Enter 'done' when finished")
        print("\nTip: Look for wallets with:")
        print("  - ROI > 20% (past 90 days)")
        print("  - Trade count > 50")
        print("  - Consistent profitability (no extreme drawdowns)")
        print("="*70 + "\n")

        i = 1
        while len(wallets) < 10:
            prompt = f"Wallet {i} address (or 'done' to finish): "
            addr = input(prompt).strip()

            if addr.lower() == 'done':
                if len(wallets) >= 6:
                    break
                else:
                    print(f"Please enter at least 6 wallets (you have {len(wallets)})")
                    continue

            # Validate
            if not addr.startswith('0x') or len(addr) != 42:
                print(f"  ✗ Invalid address format (must be 0x... 42 chars)")
                continue

            # Check if exists
            print(f"  Validating {addr[:12]}...", end=" ", flush=True)
            if not self.validate_wallet(addr):
                print("✗ Not found on Hyperliquid")
                continue

            # Get stats
            stats = self.get_wallet_stats(addr)
            if stats:
                print(f"✓ Account value: ${stats['account_value']:.2f}, Positions: {stats['active_positions']}")
            else:
                print("✓ Valid")

            wallets.append({
                'address': addr,
                'label': f"Whale_{i}",
                'active': True,
                'notes': f"Manual entry from leaderboard"
            })

            i += 1

        return wallets

    def update_whale_config(self, wallets: List[dict],
                            config_path: str = "whale_wallets.json") -> bool:
        """
        Update whale_wallets.json with provided wallets.
        """
        if not wallets:
            self.logger.error("No wallets provided")
            return False

        try:
            # Load existing config
            config = {}
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)

            # Preserve scoring config, replace wallets
            new_wallets = [
                {
                    'address': w['address'],
                    'label': w['label'],
                    'active': w.get('active', True),
                    'notes': w.get('notes', '')
                }
                for w in wallets
            ]

            config['wallets'] = new_wallets

            # Write backup
            backup_path = config_path + '.backup'
            if os.path.exists(config_path):
                import shutil
                shutil.copy(config_path, backup_path)
                self.logger.info(f"Backup: {backup_path}")

            # Write new config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            self.logger.info(f"✓ Updated {config_path} with {len(new_wallets)} wallets")
            return True

        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            return False

    def display_config(self, config_path: str = "whale_wallets.json") -> None:
        """Display current wallet configuration"""
        try:
            with open(config_path) as f:
                config = json.load(f)

            wallets = config.get('wallets', [])
            print("\n" + "="*70)
            print("CURRENT WHALE WALLET CONFIGURATION")
            print("="*70)
            print(f"Total wallets: {len(wallets)}\n")

            for i, w in enumerate(wallets, 1):
                status = "✓ ACTIVE" if w.get('active', False) else "✗ INACTIVE"
                print(f"{i}. {w.get('label', 'Unknown')}")
                print(f"   Address: {w.get('address', 'N/A')}")
                print(f"   Status:  {status}")
                print(f"   Notes:   {w.get('notes', '-')}")
                print()

        except Exception as e:
            print(f"Error reading config: {e}")

# ==================================================================
# MAIN
# ==================================================================

if __name__ == "__main__":
    import argparse
    import sys

    # Force UTF-8 encoding
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="Setup Hyperliquid whale wallets for monitoring"
    )
    parser.add_argument("--show", action="store_true",
                        help="Display current configuration")
    parser.add_argument("--config", type=str, default="whale_wallets.json",
                        help="Path to whale_wallets.json")
    args = parser.parse_args()

    setup = WalletSetup(setup_logger())

    if args.show:
        setup.display_config(args.config)
        sys.exit(0)

    # Interactive setup
    wallets = setup.prompt_wallet_entry()

    if wallets:
        print(f"\n\nConfirming {len(wallets)} wallets...")
        for w in wallets:
            print(f"  • {w['label']}: {w['address']}")

        confirm = input("\nProceed with update? (y/n): ").strip().lower()
        if confirm == 'y':
            if setup.update_whale_config(wallets, args.config):
                print("\n✓ Configuration updated successfully!")
                setup.display_config(args.config)
            else:
                print("\n✗ Failed to update configuration")
                sys.exit(1)
        else:
            print("Aborted.")
    else:
        print("No wallets configured.")
        sys.exit(1)
