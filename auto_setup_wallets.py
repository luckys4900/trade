# -*- coding: utf-8 -*-
"""
Auto Setup Wallets from Existing Configuration
Automatically populates whale_wallets.json with real wallet data from:
1. .env file (HL_WALLET_ADDRESS)
2. config.json (account_address)
3. Known trader wallets (from check_all_wallets.py)
4. Queries Hyperliquid API for current performance metrics
"""

import os, sys, json, time, logging
from datetime import datetime
from typing import Optional, List, Dict
import requests

# ==================================================================
# LOGGER SETUP
# ==================================================================

def setup_logger(log_dir="logs", name="auto_setup_wallets"):
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
# AUTO WALLET SETUP
# ==================================================================

class AutoWalletSetup:
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

    def discover_wallets_from_config(self) -> Dict[str, str]:
        """
        Discover all wallet addresses from:
        1. .env file
        2. config.json
        3. Known trader wallets
        """
        discovered = {}

        # 1. From .env
        try:
            with open('.env') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('HL_WALLET_ADDRESS='):
                        addr = line.split('=')[1].strip()
                        if addr.startswith('0x'):
                            discovered['.env (HL_WALLET_ADDRESS)'] = addr
                            self.logger.info(f"Found .env wallet: {addr[:12]}...")
        except:
            pass

        # 2. From config.json
        try:
            with open('config.json') as f:
                config = json.load(f)
                if 'account_address' in config:
                    addr = config['account_address']
                    if addr.startswith('0x'):
                        discovered['config.json (account_address)'] = addr
                        self.logger.info(f"Found config.json wallet: {addr[:12]}...")
        except:
            pass

        # 3. Known trader wallets (from check_all_wallets.py)
        known_wallets = {
            'Trader_A (.env)': '0x8455b70a5a0d942eb9a1598a0e9e1214a3b31b55',
            'Trader_B (config)': '0xE2Ce93147a19c5b8B1dd222499dE0A56987E1188',
            'Agent_Wallet': '0xF8b04CEbEc49EFFdE2c9d8C65a3268e875CB3332',
        }

        for label, addr in known_wallets.items():
            if addr not in discovered.values() and addr.startswith('0x'):
                discovered[label] = addr
                self.logger.info(f"Found known wallet: {label} - {addr[:12]}...")

        return discovered

    def get_wallet_metrics(self, address: str) -> Optional[dict]:
        """
        Fetch wallet metrics from Hyperliquid API.
        Returns account value, position count, and basic stats.
        """
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
                'active_positions': active_pos,
                'total_notional': float(margin.get('totalNtlPos', 0))
            }
        except Exception as e:
            self.logger.warning(f"Error parsing metrics for {address[:12]}...: {e}")
            return None

    def generate_whale_config(self, wallets: Dict[str, str],
                              output_path: str = "whale_wallets.json") -> bool:
        """
        Generate whale_wallets.json with discovered wallets.
        """
        if not wallets:
            self.logger.error("No wallets to configure")
            return False

        try:
            # Load existing config to preserve scoring params
            config = {}
            if os.path.exists(output_path):
                with open(output_path) as f:
                    config = json.load(f)

            # Generate wallet entries with metrics
            wallet_entries = []
            for i, (label, addr) in enumerate(wallets.items(), 1):
                metrics = self.get_wallet_metrics(addr)

                if metrics:
                    notes = f"Account Value: ${metrics['account_value']:,.2f}, Positions: {metrics['active_positions']}"
                else:
                    notes = "Metrics unavailable"

                wallet_entries.append({
                    'address': addr,
                    'label': f"Whale_{i}",
                    'active': True,
                    'notes': notes
                })

                self.logger.info(f"Whale_{i}: {addr[:12]}... - {notes}")

            # Replace wallets, preserve config structure
            config['wallets'] = wallet_entries

            # Write backup
            backup_path = output_path + '.backup'
            if os.path.exists(output_path):
                import shutil
                shutil.copy(output_path, backup_path)
                self.logger.info(f"Backup created: {backup_path}")

            # Write new config
            with open(output_path, 'w') as f:
                json.dump(config, f, indent=2)

            self.logger.info(f"✓ Generated {output_path} with {len(wallet_entries)} wallets")
            return True

        except Exception as e:
            self.logger.error(f"Failed to generate config: {e}")
            return False

    def run(self, output_path: str = "whale_wallets.json") -> bool:
        """
        Execute full auto setup workflow.
        """
        self.logger.info("=== Auto Wallet Setup ===")

        # Step 1: Discover wallets
        self.logger.info("Step 1: Discovering wallets from configuration...")
        wallets = self.discover_wallets_from_config()

        if not wallets:
            self.logger.error("No wallets discovered")
            return False

        self.logger.info(f"Found {len(wallets)} wallets")

        # Step 2: Generate config
        self.logger.info("Step 2: Fetching wallet metrics from Hyperliquid...")
        success = self.generate_whale_config(wallets, output_path)

        if success:
            self.logger.info("✓ Auto setup completed successfully")

            # Step 3: Display summary
            self.logger.info("\n" + "="*70)
            self.logger.info("CONFIGURED WALLETS")
            self.logger.info("="*70)

            with open(output_path) as f:
                config = json.load(f)
                for i, w in enumerate(config['wallets'], 1):
                    self.logger.info(f"{i}. {w['label']}: {w['address']}")
                    self.logger.info(f"   {w['notes']}")

        return success

# ==================================================================
# MAIN
# ==================================================================

if __name__ == "__main__":
    import argparse
    import sys

    # Force UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="Auto-populate whale_wallets.json from existing configuration"
    )
    parser.add_argument("--config", type=str, default="whale_wallets.json",
                        help="Path to whale_wallets.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done, don't write")
    args = parser.parse_args()

    setup = AutoWalletSetup(setup_logger())

    if args.dry_run:
        wallets = setup.discover_wallets_from_config()
        print(f"\nWould configure {len(wallets)} wallets:")
        for label, addr in wallets.items():
            print(f"  - {label}: {addr}")
    else:
        success = setup.run(args.config)
        sys.exit(0 if success else 1)
