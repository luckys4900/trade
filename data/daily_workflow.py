"""
Clarity Act Pair Trading Strategy - Daily Workflow
Automated execution of DynamicTimelineManager, SignalGenerator, and risk management
"""

import schedule
import time
import json
from datetime import datetime
import logging

from clarity_act_core import (
    DynamicTimelineManager,
    RatioCalculator,
    SignalGenerator,
    ConfigurationManager
)
from committee_vote_monitor import VoteResultAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clarity_act_workflow.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DailyWorkflow:
    """
    Daily automated workflow orchestration
    """

    def __init__(self):
        self.timeline_manager = DynamicTimelineManager()
        self.config_manager = ConfigurationManager()
        self.vote_analyzer = VoteResultAnalyzer()
        self.ratio_calc = RatioCalculator()
        self.signal_gen = SignalGenerator()
        self.trade_log = []

    def daily_congress_check(self):
        """
        Execute at: 00:30 UTC daily (8:30 PM ET previous day)
        Purpose: Check Congress.gov for Senate floor vote date update
        """
        logger.info("=== Daily Congress.gov Check ===")

        vote_updated = self.timeline_manager.daily_check()

        if vote_updated:
            logger.info("📢 NEW SENATE FLOOR VOTE DATE DETECTED!")
            params = self.timeline_manager.calculate_optimal_params()
            self.config_manager.update_params(params)
            logger.info(f"Parameters updated: {params}")
        else:
            logger.info("No new vote date detected")

        # Check committee vote status if still pending
        report = self.vote_analyzer.generate_report()
        with open('vote_status.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)

        return vote_updated

    def hourly_market_check(self, btc_price: float, eth_price: float):
        """
        Execute at: Every hour (or configurable interval)
        Purpose: Generate trading signals
        """
        logger.info("=== Hourly Market Check ===")

        # Calculate BTC/ETH ratio
        ratio = self.ratio_calc.calculate_ratio(btc_price, eth_price)
        self.ratio_calc.add_price_data(btc_price, eth_price)

        # Get current MA
        ma = self.ratio_calc.calculate_ma()

        if not ma:
            logger.info("Insufficient data for MA calculation")
            return

        # Check entry signal
        can_trade, reason = self.timeline_manager.get_entry_trigger_status()

        if not can_trade:
            logger.info(f"Cannot trade: {reason}")
            return

        # Generate entry signal
        entry_signal, entry_reason = self.signal_gen.entry_signal(btc_price, eth_price, ma)

        if entry_signal:
            logger.info(f"✅ ENTRY SIGNAL GENERATED: {entry_reason}")
            self._record_entry(btc_price, eth_price, ma, ratio)
        else:
            logger.info(f"No entry: {entry_reason}")

        # Check exit signal
        if self.signal_gen.position_active:
            exit_signal, exit_reason = self.signal_gen.exit_signal(btc_price, eth_price)

            if exit_signal:
                logger.info(f"🛑 EXIT SIGNAL: {exit_reason}")
                self._record_exit(btc_price, eth_price)

    def _record_entry(self, btc_price: float, eth_price: float, ma: float, ratio: float):
        """Record entry trade"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "entry",
            "btc_price": btc_price,
            "eth_price": eth_price,
            "ratio": ratio,
            "ma": ma,
            "ma_window": self.signal_gen.ma_window
        }
        self.trade_log.append(entry)
        with open('trade_log.json', 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def _record_exit(self, btc_price: float, eth_price: float):
        """Record exit trade"""
        exit_trade = {
            "timestamp": datetime.now().isoformat(),
            "type": "exit",
            "btc_price": btc_price,
            "eth_price": eth_price
        }
        self.trade_log.append(exit_trade)
        with open('trade_log.json', 'a') as f:
            f.write(json.dumps(exit_trade) + '\n')

    def schedule_jobs(self):
        """Schedule all jobs"""
        # Congress.gov check: 00:30 UTC daily
        schedule.every().day.at("00:30").do(self.daily_congress_check)

        # Market check: Every hour
        schedule.every().hour.do(lambda: self.hourly_market_check(0, 0))  # Replace with real prices

        logger.info("Jobs scheduled successfully")

    def run_scheduler(self):
        """Run the scheduler continuously"""
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute


class WorkflowCoordinator:
    """
    Coordinate entire trading workflow including risk management
    """

    def __init__(self):
        self.workflow = DailyWorkflow()
        self.max_daily_loss = -5.0  # Max 5% daily loss
        self.daily_pnl = 0

    def execute_daily_routine(self, market_data: Dict):
        """
        Execute complete daily routine
        market_data: {
            'btc_price': float,
            'eth_price': float,
            'timestamp': datetime
        }
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Daily Routine Execution: {datetime.now()}")
        logger.info(f"{'='*60}")

        # 1. Congress.gov check (if it's 00:30 UTC)
        if datetime.now().hour == 0 and datetime.now().minute == 30:
            self.workflow.daily_congress_check()

        # 2. Market check
        btc = market_data.get('btc_price')
        eth = market_data.get('eth_price')

        if btc and eth:
            self.workflow.hourly_market_check(btc, eth)

        # 3. Check daily loss limit
        if self.daily_pnl < self.max_daily_loss:
            logger.warning(f"⚠️ Daily loss limit reached: {self.daily_pnl:.2f}%")
            logger.info("STOPPING TRADING FOR THE DAY")


if __name__ == "__main__":
    logger.info("Clarity Act Pair Trading Workflow Started")

    coordinator = WorkflowCoordinator()

    # Example: Test with dummy market data
    test_data = {
        'btc_price': 65000,
        'eth_price': 3500,
        'timestamp': datetime.now()
    }

    coordinator.execute_daily_routine(test_data)
