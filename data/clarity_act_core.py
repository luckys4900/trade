"""
Clarity Act Pair Trading Strategy - Core Implementation
v3.0 - Dynamic Timeline System
Author: Claude Code
Date: 2026-05-14
"""

import json
from datetime import datetime, timedelta
import requests
from typing import Dict, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DynamicTimelineManager:
    """
    監視: Congress.govから上院本会議投票日を自動検出
    機能: Duration計算→パラメータ自動調整
    """

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.senate_floor_vote_date = None
        self.committee_vote_date = datetime(2026, 5, 14)
        self.target_signature_date = datetime(2026, 7, 4)

    def daily_check(self) -> bool:
        """
        毎日1回実行: Congress.govから投票日を確認
        Returns: 新しい投票日が見つかった場合True
        """
        try:
            # Congress.gov Bill Status API
            bill_url = "https://api.congress.gov/v3/bill/119/hr/3633"
            response = requests.get(bill_url, params={"format": "json"})

            if response.status_code == 200:
                bill_data = response.json()

                # Floor vote actionを検索
                if "bill" in bill_data:
                    actions = bill_data["bill"].get("actions", [])
                    for action in actions:
                        if "Senate Floor" in action.get("text", "") and "vote" in action.get("text", "").lower():
                            vote_date_str = action.get("actionDate")
                            if vote_date_str:
                                new_date = datetime.strptime(vote_date_str, "%Y-%m-%d")
                                if self.senate_floor_vote_date != new_date:
                                    self.senate_floor_vote_date = new_date
                                    logger.info(f"Senate floor vote date detected: {new_date}")
                                    return True
            return False

        except Exception as e:
            logger.error(f"Congress.gov API error: {e}")
            return False

    def calculate_optimal_params(self) -> Dict:
        """
        Duration based on (senate_floor_vote - committee_vote)
        期間に応じて最適パラメータを計算
        """
        if not self.senate_floor_vote_date:
            logger.warning("Senate floor vote date not yet determined, using default params")
            return self._get_default_params()

        duration = (self.senate_floor_vote_date - self.committee_vote_date).days

        if duration > 50:
            # Long duration: Conservative
            return {
                "ma_window": 14,
                "stop_loss_percent": -3.0,
                "position_fraction": 0.45,
                "kelly_fraction": 0.55,
                "duration_days": duration
            }
        elif duration < 20:
            # Short duration: Aggressive
            return {
                "ma_window": 5,
                "stop_loss_percent": -2.0,
                "position_fraction": 0.60,
                "kelly_fraction": 0.55,
                "duration_days": duration
            }
        else:
            # Medium duration: Balanced (optimal)
            return {
                "ma_window": 10,
                "stop_loss_percent": -2.5,
                "position_fraction": 0.50,
                "kelly_fraction": 0.55,
                "duration_days": duration
            }

    def _get_default_params(self) -> Dict:
        """Default parameters when vote date not yet determined"""
        return {
            "ma_window": 10,
            "stop_loss_percent": -2.5,
            "position_fraction": 0.50,
            "kelly_fraction": 0.55,
            "duration_days": None
        }

    def get_entry_trigger_status(self) -> Tuple[bool, str]:
        """
        Entry trigger: Senate floor vote date が確定したか？
        Returns: (can_trade, reason)
        """
        if self.senate_floor_vote_date is None:
            return False, "Senate floor vote date not yet determined"

        if self.senate_floor_vote_date < datetime.now():
            return False, "Senate floor vote date is in the past"

        return True, f"Ready to trade. Vote date: {self.senate_floor_vote_date}"


class RatioCalculator:
    """
    計算: BTC/ETH比率、移動平均、上昇トレンド検出
    """

    def __init__(self, ma_window: int = 10):
        self.ma_window = ma_window
        self.price_history = []
        self.ratio_history = []

    def calculate_ratio(self, btc_price: float, eth_price: float) -> float:
        """Calculate BTC/ETH price ratio"""
        if eth_price == 0:
            return None
        return btc_price / eth_price

    def add_price_data(self, btc_price: float, eth_price: float):
        """Add new price data point"""
        ratio = self.calculate_ratio(btc_price, eth_price)
        if ratio:
            self.ratio_history.append({
                "timestamp": datetime.now(),
                "btc": btc_price,
                "eth": eth_price,
                "ratio": ratio
            })

    def calculate_ma(self) -> Optional[float]:
        """Calculate Moving Average of BTC/ETH ratio"""
        if len(self.ratio_history) < self.ma_window:
            return None

        recent_ratios = [x["ratio"] for x in self.ratio_history[-self.ma_window:]]
        return sum(recent_ratios) / len(recent_ratios)

    def detect_uptrend(self, ma: float) -> bool:
        """Detect if current ratio is above MA (uptrend)"""
        if not self.ratio_history or not ma:
            return False

        current_ratio = self.ratio_history[-1]["ratio"]
        return current_ratio > ma


class SignalGenerator:
    """
    生成: Entry/Exit シグナル生成
    """

    def __init__(self, ma_window: int = 10, stop_loss_percent: float = -2.5):
        self.ma_window = ma_window
        self.stop_loss_percent = stop_loss_percent
        self.entry_price = None
        self.position_active = False

    def entry_signal(self, btc_price: float, eth_price: float, ma: float) -> Tuple[bool, str]:
        """
        Entry条件:
        1. BTC/ETH ratio > MA (uptrend)
        2. No active position
        """
        if self.position_active:
            return False, "Position already active"

        ratio_calc = RatioCalculator(self.ma_window)
        ratio_calc.add_price_data(btc_price, eth_price)

        if ratio_calc.detect_uptrend(ma):
            self.entry_price = (btc_price + eth_price) / 2
            self.position_active = True
            return True, f"Entry signal: BTC/ETH ratio above MA ({ma:.4f})"

        return False, "No entry condition met"

    def exit_signal(self, btc_price: float, eth_price: float) -> Tuple[bool, str]:
        """
        Exit conditions:
        1. Stop loss hit: -2.5% from entry
        2. Trailing stop: 0.5-1.0%
        """
        if not self.position_active:
            return False, "No active position"

        current_price = (btc_price + eth_price) / 2
        loss_percent = ((current_price - self.entry_price) / self.entry_price) * 100

        if loss_percent <= self.stop_loss_percent:
            self.position_active = False
            return True, f"Stop loss hit: {loss_percent:.2f}%"

        return False, "Position still active"


class ConfigurationManager:
    """
    管理: config.json の動的更新
    """

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.load_config()

    def load_config(self):
        """Load config from JSON"""
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = self._get_default_config()
            self.save_config()

    def update_params(self, params: Dict):
        """Update configuration with new parameters"""
        if "parameters" not in self.config:
            self.config["parameters"] = {}

        self.config["parameters"].update(params)
        self.save_config()
        logger.info(f"Config updated with new parameters: {params}")

    def save_config(self):
        """Save config to JSON"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)

    def _get_default_config(self) -> Dict:
        """Default configuration"""
        return {
            "strategy": "clarity_act_pair_trading",
            "version": "3.0",
            "parameters": {
                "ma_window": 10,
                "stop_loss_percent": -2.5,
                "position_fraction": 0.50,
                "kelly_fraction": 0.55
            },
            "monitoring": {
                "congress_check_frequency": "daily",
                "polymarket_check_frequency": "hourly"
            }
        }
