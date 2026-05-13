"""
Clarity Act Pair Trading v3.0 - Main Workflow Script (Production)
Production Daily Workflow for Hyperliquid Trading
Author: Claude Code
Date: 2026-05-14
"""

import json
import time
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import requests
from dataclasses import dataclass, asdict, field

# Local imports
from clarity_act_core import (
    DynamicTimelineManager,
    RatioCalculator,
    SignalGenerator,
    ConfigurationManager
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/user/Desktop/trade/data/logs/main_workflow.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class WorkflowState:
    """Workflow execution state"""
    workflow_id: str
    start_time: datetime
    phase: str
    status: str
    last_congress_check: Optional[datetime] = None
    last_polymarket_check: Optional[datetime] = None
    last_price_update: Optional[datetime] = None
    last_signal_generation: Optional[datetime] = None
    active_position: Optional[Dict] = None
    errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class MainWorkflowHyperliquid:
    """
    Main production workflow for Clarity Act Pair Trading v3.0

    Phases:
    1. Initialization - System setup and validation
    2. Daily Execution - Congress.gov monitoring, parameter updates
    3. Hourly Execution - Price updates, signal generation
    4. Entry Management - Position entry logic
    5. Exit Management - Position exit and stop-loss handling
    6. Monitoring - Real-time dashboard and alerts
    """

    def __init__(self, config_file: str = "config.json"):
        """Initialize the workflow"""
        logger.info("=== Clarity Act Pair Trading v3.0 Main Workflow Initialization ===")

        self.config_file = config_file
        self.config_manager = ConfigurationManager(config_file)
        self.timeline_manager = DynamicTimelineManager(config_file)

        # Create logs directory
        Path('/Users/user/Desktop/trade/data/logs').mkdir(exist_ok=True)

        # Initialize state
        self.workflow_state = WorkflowState(
            workflow_id=f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            start_time=datetime.now(),
            phase="INITIALIZATION",
            status="INITIALIZING"
        )

        # Trading components (lazy loaded)
        self.ratio_calculator = None
        self.signal_generator = None
        self.trade_logger = None
        self.performance_analyzer = None
        self.alert_manager = None
        self.error_recovery = None

        logger.info(f"Workflow ID: {self.workflow_state.workflow_id}")

    # ========================
    # PHASE 1: INITIALIZATION
    # ========================

    def initialization_phase(self) -> bool:
        """
        Initialize system and validate connections

        Steps:
        1. Verify configuration
        2. Initialize trading components
        3. Validate Hyperliquid connection (mock for now)
        4. Start Congress.gov monitoring
        5. Start Polymarket monitoring
        """
        try:
            self.workflow_state.phase = "INITIALIZATION"
            logger.info("Starting initialization phase...")

            # Step 1: Verify configuration
            logger.info("Verifying configuration...")
            if not self._verify_configuration():
                logger.error("Configuration verification failed")
                return False

            # Step 2: Initialize trading components
            logger.info("Initializing trading components...")
            if not self._initialize_components():
                logger.error("Component initialization failed")
                return False

            # Step 3: Validate Hyperliquid connection
            logger.info("Validating Hyperliquid connection...")
            if not self._validate_hyperliquid_connection():
                logger.error("Hyperliquid connection validation failed")
                return False

            # Step 4: Start Congress.gov monitoring
            logger.info("Starting Congress.gov monitoring...")
            if not self._start_congress_monitoring():
                logger.error("Congress.gov monitoring startup failed")
                return False

            # Step 5: Start Polymarket monitoring
            logger.info("Starting Polymarket monitoring...")
            if not self._start_polymarket_monitoring():
                logger.error("Polymarket monitoring startup failed")
                return False

            self.workflow_state.phase = "INITIALIZED"
            self.workflow_state.status = "READY"
            logger.info("Initialization phase completed successfully")
            return True

        except Exception as e:
            logger.error(f"Initialization phase error: {e}\n{traceback.format_exc()}")
            self.workflow_state.errors.append(f"Initialization error: {e}")
            return False

    def _verify_configuration(self) -> bool:
        """Verify configuration is valid"""
        try:
            config = self.config_manager.config
            required_keys = ["strategy", "version", "parameters"]
            return all(key in config for key in required_keys)
        except Exception as e:
            logger.error(f"Configuration verification error: {e}")
            return False

    def _initialize_components(self) -> bool:
        """Initialize all trading components"""
        try:
            from trade_logger import TradeLogger
            from performance_analyzer import PerformanceAnalyzer
            from alert_manager import AlertManager
            from error_recovery import ErrorRecovery

            params = self.config_manager.config.get("parameters", {})
            ma_window = params.get("ma_window", 10)
            stop_loss = params.get("stop_loss_percent", -2.5)

            self.ratio_calculator = RatioCalculator(ma_window=ma_window)
            self.signal_generator = SignalGenerator(ma_window=ma_window, stop_loss_percent=stop_loss)
            self.trade_logger = TradeLogger()
            self.performance_analyzer = PerformanceAnalyzer()
            self.alert_manager = AlertManager()
            self.error_recovery = ErrorRecovery()

            logger.info("All components initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Component initialization error: {e}")
            return False

    def _validate_hyperliquid_connection(self) -> bool:
        """Validate Hyperliquid API connection"""
        try:
            # Mock validation - in production, would call actual API
            logger.info("Hyperliquid connection validated (mock)")
            return True
        except Exception as e:
            logger.error(f"Hyperliquid connection error: {e}")
            return False

    def _start_congress_monitoring(self) -> bool:
        """Start Congress.gov monitoring"""
        try:
            result = self.timeline_manager.daily_check()
            self.workflow_state.last_congress_check = datetime.now()
            logger.info(f"Congress.gov monitoring started. New vote date detected: {result}")
            return True
        except Exception as e:
            logger.error(f"Congress.gov monitoring error: {e}")
            return False

    def _start_polymarket_monitoring(self) -> bool:
        """Start Polymarket monitoring"""
        try:
            logger.info("Polymarket monitoring started (mock)")
            self.workflow_state.last_polymarket_check = datetime.now()
            return True
        except Exception as e:
            logger.error(f"Polymarket monitoring error: {e}")
            return False

    # ========================
    # PHASE 2: DAILY EXECUTION
    # ========================

    def daily_execution_phase(self) -> bool:
        """
        Execute daily workflow (typically at 00:30 UTC)

        Steps:
        1. Check Congress.gov for new vote dates
        2. Calculate optimal parameters based on duration
        3. Update configuration
        4. Log daily status
        """
        try:
            self.workflow_state.phase = "DAILY_EXECUTION"
            logger.info("Starting daily execution phase...")

            # Step 1: Check Congress.gov
            logger.info("Checking Congress.gov for updates...")
            vote_date_changed = self.timeline_manager.daily_check()
            self.workflow_state.last_congress_check = datetime.now()

            if vote_date_changed:
                logger.info("Senate floor vote date has been updated")

                # Step 2: Calculate optimal parameters
                logger.info("Calculating optimal parameters based on duration...")
                optimal_params = self.timeline_manager.calculate_optimal_params()

                # Step 3: Update configuration
                logger.info(f"Updating configuration with new parameters: {optimal_params}")
                self.config_manager.update_params(optimal_params)

                # Update signal generator with new parameters
                if self.signal_generator:
                    self.signal_generator.ma_window = optimal_params.get("ma_window", 10)
                    self.signal_generator.stop_loss_percent = optimal_params.get("stop_loss_percent", -2.5)

            # Step 4: Log daily status
            logger.info("Logging daily status...")
            self._log_daily_status()

            self.workflow_state.status = "DAILY_EXECUTION_COMPLETE"
            logger.info("Daily execution phase completed")
            return True

        except Exception as e:
            logger.error(f"Daily execution phase error: {e}\n{traceback.format_exc()}")
            self.workflow_state.errors.append(f"Daily execution error: {e}")
            return False

    def _log_daily_status(self):
        """Log daily status to file"""
        try:
            status_file = Path('/Users/user/Desktop/trade/data/logs/daily_status.json')

            status_data = {
                "timestamp": datetime.now().isoformat(),
                "workflow_id": self.workflow_state.workflow_id,
                "phase": self.workflow_state.phase,
                "status": self.workflow_state.status,
                "senate_floor_vote_date": str(self.timeline_manager.senate_floor_vote_date),
                "active_position": self.workflow_state.active_position,
                "errors": self.workflow_state.errors
            }

            with open(status_file, 'w') as f:
                json.dump(status_data, f, indent=2)

            logger.info(f"Daily status logged to {status_file}")
        except Exception as e:
            logger.error(f"Daily status logging error: {e}")

    # ========================
    # PHASE 3: HOURLY EXECUTION
    # ========================

    def hourly_execution_phase(self) -> bool:
        """
        Execute hourly workflow

        Steps:
        1. Fetch current BTC/ETH prices
        2. Calculate ratio and moving average
        3. Generate entry/exit signals
        4. Update performance metrics
        5. Trigger entry or exit if needed
        """
        try:
            self.workflow_state.phase = "HOURLY_EXECUTION"

            # Step 1: Fetch prices
            logger.info("Fetching current BTC/ETH prices...")
            prices = self._fetch_prices()
            if not prices:
                logger.error("Failed to fetch prices")
                return False

            btc_price = prices.get("btc")
            eth_price = prices.get("eth")

            # Step 2: Calculate ratio and MA
            logger.info("Calculating ratio and moving average...")
            self.ratio_calculator.add_price_data(btc_price, eth_price)
            ma = self.ratio_calculator.calculate_ma()

            if ma:
                logger.info(f"BTC/ETH MA: {ma:.4f}")

            # Step 3: Generate signals
            logger.info("Generating entry/exit signals...")
            entry_signal, entry_reason = self.signal_generator.entry_signal(btc_price, eth_price, ma)
            exit_signal, exit_reason = self.signal_generator.exit_signal(btc_price, eth_price)

            logger.info(f"Entry signal: {entry_signal} - {entry_reason}")
            logger.info(f"Exit signal: {exit_signal} - {exit_reason}")

            # Step 4: Update performance metrics
            if self.performance_analyzer:
                self.performance_analyzer.update_metrics(btc_price, eth_price)

            self.workflow_state.last_price_update = datetime.now()
            self.workflow_state.last_signal_generation = datetime.now()

            # Step 5: Trigger actions
            if exit_signal and self.workflow_state.active_position:
                logger.info("Exit signal detected - triggering exit phase")
                if not self.exit_management_phase(exit_reason):
                    logger.error("Exit management failed")

            if entry_signal:
                logger.info("Entry signal detected - triggering entry phase")
                if not self.entry_management_phase(btc_price, eth_price):
                    logger.error("Entry management failed")

            self.workflow_state.status = "HOURLY_EXECUTION_COMPLETE"
            return True

        except Exception as e:
            logger.error(f"Hourly execution phase error: {e}\n{traceback.format_exc()}")
            self.workflow_state.errors.append(f"Hourly execution error: {e}")
            return False

    def _fetch_prices(self) -> Optional[Dict[str, float]]:
        """Fetch current BTC/ETH prices from API"""
        try:
            # Using CoinGecko as fallback
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd"
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            return {
                "btc": data.get("bitcoin", {}).get("usd"),
                "eth": data.get("ethereum", {}).get("usd"),
                "timestamp": datetime.now()
            }
        except Exception as e:
            logger.error(f"Price fetch error: {e}")
            return None

    # ========================
    # PHASE 4: ENTRY MANAGEMENT
    # ========================

    def entry_management_phase(self, btc_price: float, eth_price: float) -> bool:
        """
        Handle entry phase when signal is generated

        Steps:
        1. Confirm entry signal
        2. Check available funds
        3. Calculate position size
        4. Execute entry order
        5. Log trade entry
        """
        try:
            self.workflow_state.phase = "ENTRY_MANAGEMENT"
            logger.info("Starting entry management phase...")

            # Step 1: Confirm entry signal (already done in hourly_execution)
            logger.info("Entry signal confirmed")

            # Step 2: Check available funds
            logger.info("Checking available funds...")
            available_balance = self._check_available_balance()
            if not available_balance or available_balance <= 0:
                logger.warning("Insufficient funds for entry")
                self._send_alert("Entry blocked: Insufficient funds", "WARNING")
                return False

            # Step 3: Calculate position size
            logger.info("Calculating position size...")
            params = self.config_manager.config.get("parameters", {})
            position_fraction = params.get("position_fraction", 0.50)
            position_size = available_balance * position_fraction

            logger.info(f"Position size: ${position_size:.2f} ({position_fraction*100:.1f}% of balance)")

            # Step 4: Execute entry order
            logger.info("Executing entry order on Hyperliquid...")
            entry_price = (btc_price + eth_price) / 2
            order_result = self._execute_entry_order(position_size, entry_price)

            if not order_result:
                logger.error("Entry order execution failed")
                self._send_alert("Entry order failed", "ERROR")
                return False

            # Step 5: Log trade entry
            logger.info("Logging trade entry...")
            self.workflow_state.active_position = {
                "entry_time": datetime.now().isoformat(),
                "entry_price": entry_price,
                "position_size": position_size,
                "btc_price": btc_price,
                "eth_price": eth_price,
                "order_id": order_result.get("order_id")
            }

            if self.trade_logger:
                self.trade_logger.log_entry(self.workflow_state.active_position)

            self._send_alert(f"Entry executed at {entry_price:.2f}", "INFO")
            self.workflow_state.status = "POSITION_ACTIVE"

            logger.info("Entry management phase completed successfully")
            return True

        except Exception as e:
            logger.error(f"Entry management phase error: {e}\n{traceback.format_exc()}")
            self.workflow_state.errors.append(f"Entry error: {e}")
            return False

    def _check_available_balance(self) -> Optional[float]:
        """Check available balance on Hyperliquid"""
        try:
            # Mock implementation - would call actual Hyperliquid API
            logger.info("Checking balance on Hyperliquid (mock)")
            return 10000.0  # Mock balance
        except Exception as e:
            logger.error(f"Balance check error: {e}")
            return None

    def _execute_entry_order(self, position_size: float, entry_price: float) -> Optional[Dict]:
        """Execute entry order on Hyperliquid"""
        try:
            # Mock implementation - would call actual Hyperliquid API
            logger.info(f"Executing order: size={position_size}, price={entry_price} (mock)")
            return {
                "order_id": f"order_{datetime.now().timestamp()}",
                "status": "filled",
                "position_size": position_size,
                "entry_price": entry_price
            }
        except Exception as e:
            logger.error(f"Order execution error: {e}")
            return None

    # ========================
    # PHASE 5: EXIT MANAGEMENT
    # ========================

    def exit_management_phase(self, exit_reason: str) -> bool:
        """
        Handle exit phase when exit signal is generated

        Steps:
        1. Confirm exit signal
        2. Check stop-loss conditions
        3. Execute exit order
        4. Log trade exit
        5. Update performance metrics
        """
        try:
            self.workflow_state.phase = "EXIT_MANAGEMENT"
            logger.info(f"Starting exit management phase... Reason: {exit_reason}")

            if not self.workflow_state.active_position:
                logger.warning("No active position to exit")
                return False

            # Step 1: Confirm exit signal
            logger.info("Exit signal confirmed")

            # Step 2: Check stop-loss conditions
            # Already handled in signal generation
            logger.info(f"Exit reason: {exit_reason}")

            # Step 3: Execute exit order
            logger.info("Executing exit order on Hyperliquid...")
            exit_result = self._execute_exit_order()

            if not exit_result:
                logger.error("Exit order execution failed")
                self._send_alert("Exit order failed", "ERROR")
                return False

            # Step 4: Log trade exit
            logger.info("Logging trade exit...")
            exit_data = {
                **self.workflow_state.active_position,
                "exit_time": datetime.now().isoformat(),
                "exit_price": exit_result.get("exit_price"),
                "exit_reason": exit_reason,
                "pnl": exit_result.get("pnl"),
                "pnl_percent": exit_result.get("pnl_percent")
            }

            if self.trade_logger:
                self.trade_logger.log_exit(exit_data)

            # Step 5: Update performance metrics
            if self.performance_analyzer:
                self.performance_analyzer.record_trade(exit_data)

            self._send_alert(f"Exit executed. P&L: {exit_result.get('pnl_percent'):.2f}%", "INFO")

            self.workflow_state.active_position = None
            self.workflow_state.status = "POSITION_CLOSED"

            logger.info("Exit management phase completed successfully")
            return True

        except Exception as e:
            logger.error(f"Exit management phase error: {e}\n{traceback.format_exc()}")
            self.workflow_state.errors.append(f"Exit error: {e}")
            return False

    def _execute_exit_order(self) -> Optional[Dict]:
        """Execute exit order on Hyperliquid"""
        try:
            if not self.workflow_state.active_position:
                return None

            # Mock implementation
            entry_price = self.workflow_state.active_position.get("entry_price", 0)
            exit_price = entry_price * 1.01  # Mock: 1% profit
            position_size = self.workflow_state.active_position.get("position_size", 0)

            pnl = (exit_price - entry_price) * position_size
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100

            logger.info(f"Exit order executed (mock): price={exit_price}, P&L={pnl:.2f}, {pnl_percent:.2f}%")

            return {
                "order_id": f"exit_order_{datetime.now().timestamp()}",
                "status": "filled",
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_percent": pnl_percent
            }
        except Exception as e:
            logger.error(f"Exit order execution error: {e}")
            return None

    # ========================
    # PHASE 6: MONITORING
    # ========================

    def monitoring_phase(self) -> bool:
        """
        Continuous monitoring phase

        Steps:
        1. Update real-time dashboard
        2. Manage alerts
        3. Track performance
        4. Manage logs
        """
        try:
            self.workflow_state.phase = "MONITORING"

            # Step 1: Update dashboard
            logger.info("Updating real-time dashboard...")
            self._update_dashboard()

            # Step 2: Manage alerts
            logger.info("Managing alerts...")
            if self.alert_manager:
                self.alert_manager.process_alerts()

            # Step 3: Track performance
            if self.performance_analyzer:
                metrics = self.performance_analyzer.get_current_metrics()
                logger.info(f"Performance metrics: {metrics}")

            # Step 4: Manage logs
            logger.info("Managing logs...")
            self._manage_logs()

            return True

        except Exception as e:
            logger.error(f"Monitoring phase error: {e}")
            return False

    def _update_dashboard(self):
        """Update real-time dashboard"""
        try:
            dashboard_data = {
                "timestamp": datetime.now().isoformat(),
                "workflow_state": asdict(self.workflow_state),
                "active_position": self.workflow_state.active_position,
                "senate_floor_vote_date": str(self.timeline_manager.senate_floor_vote_date)
            }

            dashboard_file = Path('/Users/user/Desktop/trade/data/logs/dashboard.json')
            with open(dashboard_file, 'w') as f:
                json.dump(dashboard_data, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Dashboard update error: {e}")

    def _send_alert(self, message: str, level: str = "INFO"):
        """Send alert notification"""
        try:
            if self.alert_manager:
                self.alert_manager.send_alert(message, level)
            logger.log(getattr(logging, level, logging.INFO), f"ALERT: {message}")
        except Exception as e:
            logger.error(f"Alert sending error: {e}")

    def _manage_logs(self):
        """Manage log files"""
        try:
            logs_dir = Path('/Users/user/Desktop/trade/data/logs')
            log_files = sorted(logs_dir.glob('*.log'), key=lambda x: x.stat().st_mtime)

            # Keep only last 30 days of logs
            cutoff_time = datetime.now() - timedelta(days=30)
            for log_file in log_files:
                if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_time:
                    log_file.unlink()
                    logger.info(f"Deleted old log: {log_file}")
        except Exception as e:
            logger.error(f"Log management error: {e}")

    # ========================
    # MAIN EXECUTION LOOP
    # ========================

    def run_continuous(self):
        """
        Run the workflow continuously
        Coordinates all phases in a production-ready manner
        """
        logger.info("=== Starting Continuous Workflow ===")

        # Phase 1: Initialization
        if not self.initialization_phase():
            logger.error("Initialization failed - cannot continue")
            return False

        # Check if we can trade
        can_trade, reason = self.timeline_manager.get_entry_trigger_status()
        if can_trade:
            logger.info(f"Ready for trading: {reason}")
        else:
            logger.info(f"Not ready for trading yet: {reason}")

        # Main execution loop
        daily_check_time = datetime.now().replace(hour=0, minute=30, second=0, microsecond=0)
        if daily_check_time < datetime.now():
            daily_check_time += timedelta(days=1)

        cycle = 0
        while True:
            try:
                cycle += 1
                current_time = datetime.now()

                logger.info(f"\n=== Cycle {cycle} at {current_time.isoformat()} ===")

                # Daily execution check
                if current_time >= daily_check_time:
                    logger.info("Executing daily phase...")
                    if not self.daily_execution_phase():
                        logger.warning("Daily execution returned False")
                    daily_check_time += timedelta(days=1)

                # Hourly execution
                logger.info("Executing hourly phase...")
                if not self.hourly_execution_phase():
                    logger.warning("Hourly execution returned False")

                # Monitoring
                if not self.monitoring_phase():
                    logger.warning("Monitoring returned False")

                # Sleep for 60 minutes until next hourly cycle
                logger.info("Sleeping for 3600 seconds until next cycle...")
                time.sleep(3600)

            except KeyboardInterrupt:
                logger.info("Workflow interrupted by user")
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}\n{traceback.format_exc()}")
                self.workflow_state.errors.append(f"Main loop error: {e}")

                # Attempt error recovery
                if self.error_recovery:
                    logger.info("Attempting error recovery...")
                    self.error_recovery.recover()

                # Wait before retrying
                time.sleep(300)

        logger.info("=== Workflow terminated ===")
        return True


if __name__ == "__main__":
    import sys

    try:
        workflow = MainWorkflowHyperliquid()
        success = workflow.run_continuous()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Fatal error: {e}\n{traceback.format_exc()}")
        sys.exit(1)
