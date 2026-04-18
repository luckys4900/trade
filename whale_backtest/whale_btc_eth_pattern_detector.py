# -*- coding: utf-8 -*-
"""
PatternDetector - Fetches whale wallet history and detects trading patterns
Reads monitored wallet list from whale_wallets.json
Fetches past transaction history from Hyperliquid API (userFills endpoint)
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timedelta, timezone, UTC
from pathlib import Path
from typing import List, Dict, Optional


class PatternDetector:
    """Detects patterns in whale wallet trading history"""

    HL_API_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, config_path: str = None, log_dir: str = "logs"):
        """
        Initialize PatternDetector

        Args:
            config_path: Path to whale_wallets.json (default: looks in SYSTEM directory)
            log_dir: Directory for log files
        """
        self.logger = self._setup_logger(log_dir)

        # Resolve config path - try parameter, then CWD, then SYSTEM directory
        if config_path is None:
            config_path = self._resolve_default_config_path()
        self.config_path = self._resolve_path(config_path)

        # Load configuration
        self.config = self._load_config()

        self.logger.info(f"PatternDetector initialized with config: {self.config_path}")

    def _setup_logger(self, log_dir: str) -> logging.Logger:
        """Setup logger with file and console handlers"""
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"pattern_detector_{ts}.log")

        logger = logging.getLogger("PatternDetector")
        logger.setLevel(logging.DEBUG)

        # File handler
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        # Clear existing handlers to avoid duplicates
        logger.handlers = []
        logger.addHandler(fh)
        logger.addHandler(ch)

        return logger

    def _resolve_default_config_path(self) -> str:
        """Try to find whale_wallets.json in standard locations"""
        # Try SYSTEM directory first
        system_dir = Path(__file__).parent.parent / "SYSTEM"
        if system_dir.exists():
            config_in_system = system_dir / "whale_wallets.json"
            if config_in_system.exists():
                return str(config_in_system)

        # Try CWD
        if Path("whale_wallets.json").exists():
            return "whale_wallets.json"

        # Default
        return "whale_wallets.json"

    def _resolve_path(self, path_str: str) -> str:
        """Resolve relative or absolute path"""
        path = Path(path_str)
        if path.is_absolute():
            return str(path)

        if path.exists():
            return str(path)

        # Try relative to script directory
        script_relative = Path(__file__).resolve().parent.parent / path_str
        if script_relative.exists():
            return str(script_relative)

        return str(path)

    def _load_config(self) -> dict:
        """Load whale_wallets.json configuration"""
        if not os.path.exists(self.config_path):
            self.logger.warning(f"Config file not found: {self.config_path}")
            return {"wallets": [], "scoring_config": {}}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            self.logger.info(f"Loaded config with {len(cfg.get('wallets', []))} wallets")
            return cfg
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {"wallets": [], "scoring_config": {}}

    def load_monitored_wallets(self) -> List[Dict]:
        """
        Load monitored wallets from config and filter to active only

        Returns:
            List of wallet dicts with keys: address, label, active, notes
        """
        wallets_cfg = self.config.get("wallets", [])

        # Filter to active wallets
        active_wallets = [w for w in wallets_cfg if w.get("active", False)]

        self.logger.info(f"Loaded {len(active_wallets)} active wallets")
        return active_wallets

    def _raw_post(self, payload: dict, timeout: int = 10) -> Optional[dict]:
        """POST to Hyperliquid info endpoint"""
        try:
            resp = requests.post(self.HL_API_URL, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            else:
                self.logger.warning(f"HL API returned {resp.status_code}")
                return None
        except Exception as e:
            self.logger.warning(f"HL API error: {e}")
            return None

    def fetch_wallet_history(self, wallet_address: str, days: int = 365) -> List[Dict]:
        """
        Fetch past transaction history for a wallet from Hyperliquid

        Args:
            wallet_address: Wallet address to fetch history for
            days: Number of days of history to fetch (default 365)

        Returns:
            List of transactions with format:
            [
                {
                    'timestamp': ms_since_epoch,
                    'coin': 'BTC',
                    'side': 'buy' | 'sell' | 'transfer_out',
                    'size': float,
                    'price': float
                },
                ...
            ]
        """
        # Calculate start time
        start_time_ms = int(
            (datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000
        )

        # Fetch fills from Hyperliquid
        payload = {
            "type": "userFills",
            "user": wallet_address,
            "startTime": start_time_ms
        }

        fills = self._raw_post(payload)
        if not isinstance(fills, list):
            self.logger.warning(f"Failed to fetch fills for {wallet_address}")
            return []

        self.logger.info(f"Fetched {len(fills)} fills for {wallet_address} (past {days} days)")

        # Convert fills to standardized transaction format
        transactions = []
        for fill in fills:
            try:
                # Determine side
                side_char = fill.get('side', '')  # 'A' (ask/sell) or 'B' (bid/buy)
                if side_char == 'B':
                    side = 'buy'
                elif side_char == 'A':
                    side = 'sell'
                else:
                    side = 'unknown'

                tx = {
                    'timestamp': float(fill.get('time', 0)),
                    'coin': fill.get('coin', ''),
                    'side': side,
                    'size': float(fill.get('sz', 0)),
                    'price': float(fill.get('px', 0))
                }
                transactions.append(tx)
            except Exception as e:
                self.logger.debug(f"Failed to parse fill: {fill}, error: {e}")
                continue

        self.logger.info(f"Converted {len(transactions)} fills to transactions")
        return transactions


if __name__ == "__main__":
    detector = PatternDetector()
    wallets = detector.load_monitored_wallets()
    print(f"Found {len(wallets)} monitored wallets")
    for wallet in wallets:
        print(f"  {wallet['label']}: {wallet['address']}")
