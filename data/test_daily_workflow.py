"""
Integration Test Suite - Clarity Act Pair Trading v3.0 Daily Workflow
Comprehensive testing of all workflow components
Author: Claude Code
Date: 2026-05-14
"""

import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkflowTestSuite:
    """Comprehensive test suite for daily workflow"""

    def __init__(self):
        """Initialize test suite"""
        self.logs_dir = Path('/Users/user/Desktop/trade/data/logs')
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.test_results = []
        logger.info("=== Workflow Test Suite Initialized ===")

    def run_all_tests(self) -> Tuple[int, int]:
        """
        Run all integration tests

        Returns:
            (passed_tests, failed_tests)
        """
        logger.info("Starting comprehensive integration tests...")

        # Test imports
        if not self._test_imports():
            logger.error("Import tests failed - cannot continue")
            return 0, 1

        # Test components
        self._test_clarity_act_core()
        self._test_trade_logger()
        self._test_performance_analyzer()
        self._test_alert_manager()
        self._test_error_recovery()
        self._test_main_workflow()

        # Generate report
        self._generate_test_report()

        # Count results
        passed = len([r for r in self.test_results if r["status"] == "PASSED"])
        failed = len([r for r in self.test_results if r["status"] == "FAILED"])

        logger.info(f"\n=== Test Results: {passed} PASSED, {failed} FAILED ===")
        return passed, failed

    # ========================
    # IMPORT TESTS
    # ========================

    def _test_imports(self) -> bool:
        """Test that all modules can be imported"""
        test_name = "Test Module Imports"
        logger.info(f"\nRunning: {test_name}")

        try:
            import clarity_act_core
            logger.info("✓ clarity_act_core imported")

            import trade_logger
            logger.info("✓ trade_logger imported")

            import performance_analyzer
            logger.info("✓ performance_analyzer imported")

            import alert_manager
            logger.info("✓ alert_manager imported")

            import error_recovery
            logger.info("✓ error_recovery imported")

            import main_workflow_hyperliquid
            logger.info("✓ main_workflow_hyperliquid imported")

            self._record_test(test_name, "PASSED", "All modules imported successfully")
            return True

        except ImportError as e:
            logger.error(f"✗ Import failed: {e}")
            self._record_test(test_name, "FAILED", f"Import error: {e}")
            return False
        except Exception as e:
            logger.error(f"✗ Unexpected error: {e}")
            self._record_test(test_name, "FAILED", f"Error: {e}")
            return False

    # ========================
    # CLARITY ACT CORE TESTS
    # ========================

    def _test_clarity_act_core(self):
        """Test clarity_act_core module"""
        from clarity_act_core import (
            DynamicTimelineManager,
            RatioCalculator,
            SignalGenerator,
            ConfigurationManager
        )

        # Test 1: DynamicTimelineManager
        test_name = "DynamicTimelineManager Initialization"
        logger.info(f"\nRunning: {test_name}")
        try:
            timeline_mgr = DynamicTimelineManager()
            assert timeline_mgr.config_file == "config.json"
            assert timeline_mgr.committee_vote_date is not None
            self._record_test(test_name, "PASSED", "Timeline manager initialized correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 2: RatioCalculator
        test_name = "RatioCalculator Ratio Calculation"
        logger.info(f"Running: {test_name}")
        try:
            calc = RatioCalculator(ma_window=10)
            ratio = calc.calculate_ratio(45000, 2500)
            assert ratio == 18.0
            calc.add_price_data(45000, 2500)
            assert len(calc.ratio_history) == 1
            self._record_test(test_name, "PASSED", "Ratio calculation works correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 3: SignalGenerator
        test_name = "SignalGenerator Entry/Exit Signals"
        logger.info(f"Running: {test_name}")
        try:
            sig_gen = SignalGenerator(ma_window=10)
            entry_sig, entry_reason = sig_gen.entry_signal(45000, 2500, 18.0)
            assert isinstance(entry_sig, bool)
            exit_sig, exit_reason = sig_gen.exit_signal(45000, 2500)
            assert isinstance(exit_sig, bool)
            self._record_test(test_name, "PASSED", "Signal generation works correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 4: ConfigurationManager
        test_name = "ConfigurationManager Config Load/Save"
        logger.info(f"Running: {test_name}")
        try:
            config_mgr = ConfigurationManager()
            config = config_mgr.config
            assert "strategy" in config
            assert "version" in config
            assert "parameters" in config
            self._record_test(test_name, "PASSED", "Configuration management works correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

    # ========================
    # TRADE LOGGER TESTS
    # ========================

    def _test_trade_logger(self):
        """Test trade_logger module"""
        from trade_logger import TradeLogger
        from datetime import datetime, timedelta

        # Test 1: TradeLogger Initialization
        test_name = "TradeLogger Initialization"
        logger.info(f"\nRunning: {test_name}")
        try:
            logger_inst = TradeLogger()
            assert logger_inst.logs_dir == Path('/Users/user/Desktop/trade/data/logs')
            self._record_test(test_name, "PASSED", "Trade logger initialized correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 2: Log Entry
        test_name = "TradeLogger Entry Logging"
        logger.info(f"Running: {test_name}")
        try:
            logger_inst = TradeLogger()
            entry_data = {
                "entry_time": datetime.now(),
                "entry_price": 45000.0,
                "position_size": 500.0,
                "btc_price": 45000.0,
                "eth_price": 2500.0,
                "order_id": "test_order_001"
            }
            entry_id = logger_inst.log_entry(entry_data)
            assert entry_id is not None
            self._record_test(test_name, "PASSED", f"Entry logged with ID: {entry_id}")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 3: Log Exit
        test_name = "TradeLogger Exit Logging"
        logger.info(f"Running: {test_name}")
        try:
            logger_inst = TradeLogger()
            open_trades = logger_inst.get_open_trades()
            if open_trades:
                entry_id = open_trades[-1].entry_id
                exit_data = {
                    "entry_id": entry_id,
                    "exit_time": datetime.now(),
                    "exit_price": 45500.0,
                    "exit_reason": "Test exit",
                    "pnl": 250.0,
                    "pnl_percent": 1.11
                }
                result = logger_inst.log_exit(exit_data)
                assert result is not None
                self._record_test(test_name, "PASSED", "Exit logged successfully")
            else:
                self._record_test(test_name, "SKIPPED", "No open trades to test exit")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 4: Daily Report Generation
        test_name = "TradeLogger Daily Report Generation"
        logger.info(f"Running: {test_name}")
        try:
            logger_inst = TradeLogger()
            report = logger_inst.generate_daily_report()
            assert report is not None
            assert "title" in report
            assert "metrics" in report
            self._record_test(test_name, "PASSED", "Daily report generated successfully")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

    # ========================
    # PERFORMANCE ANALYZER TESTS
    # ========================

    def _test_performance_analyzer(self):
        """Test performance_analyzer module"""
        from performance_analyzer import PerformanceAnalyzer
        from datetime import datetime, timedelta

        # Test 1: PerformanceAnalyzer Initialization
        test_name = "PerformanceAnalyzer Initialization"
        logger.info(f"\nRunning: {test_name}")
        try:
            analyzer = PerformanceAnalyzer(window_size=50)
            assert analyzer.window_size == 50
            self._record_test(test_name, "PASSED", "Performance analyzer initialized correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 2: Trade Recording and Metrics Calculation
        test_name = "PerformanceAnalyzer Trade Recording"
        logger.info(f"Running: {test_name}")
        try:
            analyzer = PerformanceAnalyzer(window_size=50)
            trade_data = {
                "entry_time": datetime.now() - timedelta(hours=2),
                "entry_price": 45000.0,
                "exit_time": datetime.now(),
                "exit_price": 45500.0,
                "position_size": 500.0,
                "pnl": 250.0,
                "pnl_percent": 1.11
            }
            analyzer.record_trade(trade_data)
            metrics = analyzer.get_current_metrics()
            assert metrics is not None
            assert metrics.total_trades >= 1
            self._record_test(test_name, "PASSED", "Trade recording and metrics work correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 3: Expected Value Calculation
        test_name = "PerformanceAnalyzer EV Calculation"
        logger.info(f"Running: {test_name}")
        try:
            analyzer = PerformanceAnalyzer(window_size=50)
            ev = analyzer.calculate_expected_value()
            # EV can be None if no trades
            self._record_test(test_name, "PASSED", f"EV calculation works (result: {ev})")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

    # ========================
    # ALERT MANAGER TESTS
    # ========================

    def _test_alert_manager(self):
        """Test alert_manager module"""
        from alert_manager import AlertManager

        # Test 1: AlertManager Initialization
        test_name = "AlertManager Initialization"
        logger.info(f"\nRunning: {test_name}")
        try:
            manager = AlertManager()
            assert manager.logs_dir == Path('/Users/user/Desktop/trade/data/logs')
            self._record_test(test_name, "PASSED", "Alert manager initialized correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 2: Send Alert
        test_name = "AlertManager Send Alert"
        logger.info(f"Running: {test_name}")
        try:
            manager = AlertManager()
            alert_id = manager.send_alert("Test alert message", "INFO")
            assert alert_id is not None
            self._record_test(test_name, "PASSED", f"Alert sent with ID: {alert_id}")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 3: Get Alert Summary
        test_name = "AlertManager Get Summary"
        logger.info(f"Running: {test_name}")
        try:
            manager = AlertManager()
            summary = manager.get_alert_summary()
            assert summary is not None
            assert "total_alerts" in summary
            self._record_test(test_name, "PASSED", "Alert summary retrieved successfully")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

    # ========================
    # ERROR RECOVERY TESTS
    # ========================

    def _test_error_recovery(self):
        """Test error_recovery module"""
        from error_recovery import ErrorRecovery, ErrorSeverity

        # Test 1: ErrorRecovery Initialization
        test_name = "ErrorRecovery Initialization"
        logger.info(f"\nRunning: {test_name}")
        try:
            recovery = ErrorRecovery()
            assert recovery.max_retries == 3
            self._record_test(test_name, "PASSED", "Error recovery initialized correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 2: Record Error
        test_name = "ErrorRecovery Record Error"
        logger.info(f"Running: {test_name}")
        try:
            recovery = ErrorRecovery()
            try:
                raise ValueError("Test error")
            except Exception as e:
                error_id = recovery.record_error(e, "TEST_COMPONENT", "MEDIUM")
                assert error_id is not None
            self._record_test(test_name, "PASSED", f"Error recorded with ID: {error_id}")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 3: System Health Check
        test_name = "ErrorRecovery System Health"
        logger.info(f"Running: {test_name}")
        try:
            recovery = ErrorRecovery()
            health = recovery.is_system_healthy()
            assert isinstance(health, bool)
            self._record_test(test_name, "PASSED", f"System health: {health}")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

    # ========================
    # MAIN WORKFLOW TESTS
    # ========================

    def _test_main_workflow(self):
        """Test main_workflow_hyperliquid module"""
        from main_workflow_hyperliquid import MainWorkflowHyperliquid

        # Test 1: MainWorkflowHyperliquid Initialization
        test_name = "MainWorkflowHyperliquid Initialization"
        logger.info(f"\nRunning: {test_name}")
        try:
            workflow = MainWorkflowHyperliquid()
            assert workflow.config_file == "config.json"
            assert workflow.workflow_state is not None
            self._record_test(test_name, "PASSED", "Workflow initialized correctly")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 2: Initialization Phase
        test_name = "MainWorkflowHyperliquid Initialization Phase"
        logger.info(f"Running: {test_name}")
        try:
            workflow = MainWorkflowHyperliquid()
            result = workflow.initialization_phase()
            assert isinstance(result, bool)
            self._record_test(test_name, "PASSED", f"Initialization phase completed: {result}")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 3: Daily Execution Phase
        test_name = "MainWorkflowHyperliquid Daily Execution Phase"
        logger.info(f"Running: {test_name}")
        try:
            workflow = MainWorkflowHyperliquid()
            workflow.initialization_phase()
            result = workflow.daily_execution_phase()
            assert isinstance(result, bool)
            self._record_test(test_name, "PASSED", f"Daily execution phase completed: {result}")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 4: Hourly Execution Phase
        test_name = "MainWorkflowHyperliquid Hourly Execution Phase"
        logger.info(f"Running: {test_name}")
        try:
            workflow = MainWorkflowHyperliquid()
            workflow.initialization_phase()
            result = workflow.hourly_execution_phase()
            assert isinstance(result, bool)
            self._record_test(test_name, "PASSED", f"Hourly execution phase completed: {result}")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

        # Test 5: Price Fetching
        test_name = "MainWorkflowHyperliquid Price Fetching"
        logger.info(f"Running: {test_name}")
        try:
            workflow = MainWorkflowHyperliquid()
            prices = workflow._fetch_prices()
            if prices:
                assert "btc" in prices
                assert "eth" in prices
                self._record_test(test_name, "PASSED", f"Prices fetched: BTC=${prices['btc']}, ETH=${prices['eth']}")
            else:
                self._record_test(test_name, "FAILED", "Price fetching returned None")
        except Exception as e:
            self._record_test(test_name, "FAILED", str(e))

    # ========================
    # UTILITY METHODS
    # ========================

    def _record_test(self, test_name: str, status: str, message: str = ""):
        """Record test result"""
        self.test_results.append({
            "test_name": test_name,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "message": message
        })
        logger.info(f"  [{status}] {message}")

    def _generate_test_report(self):
        """Generate test report"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_tests": len(self.test_results),
            "passed": len([r for r in self.test_results if r["status"] == "PASSED"]),
            "failed": len([r for r in self.test_results if r["status"] == "FAILED"]),
            "skipped": len([r for r in self.test_results if r["status"] == "SKIPPED"]),
            "results": self.test_results
        }

        report_file = self.logs_dir / "test_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"\nTest report saved to: {report_file}")


if __name__ == "__main__":
    # Change to data directory for imports
    import os
    os.chdir('/Users/user/Desktop/trade/data')
    sys.path.insert(0, '/Users/user/Desktop/trade/data')

    # Run test suite
    suite = WorkflowTestSuite()
    passed, failed = suite.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)
