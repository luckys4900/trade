# -*- coding: utf-8 -*-
"""
Tests for PatternDetector class
Tests wallet loading and transaction history fetching
"""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from whale_backtest.whale_btc_eth_pattern_detector import PatternDetector


class TestPatternDetectorWalletLoading:
    """Tests for load_monitored_wallets() method"""

    def test_load_monitored_wallets_from_default_path(self, tmp_path):
        """Test loading wallets from whale_wallets.json"""
        test_config = {
            "wallets": [
                {"address": "0x863b676e5e4fea0541062c32983dc8f84749ca6d", "label": "Whale_1", "active": True},
                {"address": "0x932bdd2d5e21475e62d2fea8158fc5974507cb1a", "label": "Whale_2", "active": True},
                {"address": "0x523852be2db1a76a0e088ecbff32e849544054e5", "label": "Whale_3", "active": True}
            ],
            "scoring_config": {}
        }

        config_file = tmp_path / "whale_wallets.json"
        with open(config_file, 'w') as f:
            json.dump(test_config, f)

        detector = PatternDetector(config_path=str(config_file))
        wallets = detector.load_monitored_wallets()

        assert isinstance(wallets, list)
        assert len(wallets) == 3
        for wallet in wallets:
            assert 'address' in wallet
            assert 'label' in wallet

    def test_load_monitored_wallets_inactive_filtering(self, tmp_path):
        """Test only active wallets returned"""
        test_config = {
            "wallets": [
                {"address": "0x863b676e5e4fea0541062c32983dc8f84749ca6d", "label": "Whale_1", "active": True},
                {"address": "0x932bdd2d5e21475e62d2fea8158fc5974507cb1a", "label": "Whale_2", "active": False}
            ],
            "scoring_config": {}
        }

        config_file = tmp_path / "whale_wallets.json"
        with open(config_file, 'w') as f:
            json.dump(test_config, f)

        detector = PatternDetector(config_path=str(config_file))
        wallets = detector.load_monitored_wallets()
        assert len(wallets) == 1

    def test_load_monitored_wallets_missing_file(self):
        """Test missing file handling"""
        detector = PatternDetector(config_path="/nonexistent/whale_wallets.json")
        wallets = detector.load_monitored_wallets()
        assert isinstance(wallets, list)


class TestPatternDetectorHistoryFetching:
    """Tests for fetch_wallet_history() method"""

    def test_fetch_wallet_history_return_format(self):
        """Test fetch_wallet_history returns correct format"""
        detector = PatternDetector()
        wallet_addr = "0x863b676e5e4fea0541062c32983dc8f84749ca6d"
        history = detector.fetch_wallet_history(wallet_addr, days=7)

        assert isinstance(history, list)
        for tx in history:
            assert 'timestamp' in tx
            assert 'coin' in tx
            assert 'side' in tx
            assert 'size' in tx
            assert 'price' in tx

    def test_fetch_wallet_history_days_parameter(self):
        """Test days parameter filters correctly"""
        detector = PatternDetector()
        wallet_addr = "0x863b676e5e4fea0541062c32983dc8f84749ca6d"

        history_7d = detector.fetch_wallet_history(wallet_addr, days=7)
        history_30d = detector.fetch_wallet_history(wallet_addr, days=30)
        assert len(history_30d) >= len(history_7d)


class TestPatternDetectorInitialization:
    """Tests for initialization"""

    def test_initialization_creates_logger(self, tmp_path):
        """Test logger creation"""
        log_dir = tmp_path / "logs"
        detector = PatternDetector(log_dir=str(log_dir))
        assert detector.logger is not None

    def test_initialization_with_custom_paths(self, tmp_path):
        """Test custom path"""
        test_config = {"wallets": [], "scoring_config": {}}
        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(test_config, f)

        detector = PatternDetector(config_path=str(config_file))
        assert detector.config_path == str(config_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
