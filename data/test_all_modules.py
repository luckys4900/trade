"""
Comprehensive Test Suite for Clarity Act Pair Trading v3.0
Tests all modules for functionality, error handling, and integration
"""

import sys
import os
import json
import traceback
from datetime import datetime, timedelta
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_results.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TestRunner:
    """
    Comprehensive test runner for all modules
    """

    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "passed": 0,
            "failed": 0,
            "errors": []
        }
        self.separator = "=" * 80

    def print_header(self, title):
        """Print test section header"""
        print(f"\n{self.separator}")
        print(f"  {title}")
        print(self.separator)
        logger.info(f"\n{title}")

    def test_imports(self):
        """Test 1: Verify all modules can be imported"""
        self.print_header("TEST 1: Module Imports")

        modules_to_test = [
            ("clarity_act_core", [
                "DynamicTimelineManager",
                "RatioCalculator",
                "SignalGenerator",
                "ConfigurationManager"
            ]),
            ("committee_vote_monitor", [
                "CongressGovMonitor",
                "PolymarketMonitor",
                "VoteResultAnalyzer"
            ]),
            ("daily_workflow", [
                "DailyWorkflow",
                "WorkflowCoordinator"
            ]),
            ("realtime_monitor_dashboard", [
                "RealtimeMonitorDashboard"
            ])
        ]

        test_name = "Import Test"
        try:
            for module_name, classes in modules_to_test:
                try:
                    module = __import__(module_name)
                    logger.info(f"✅ Module '{module_name}' imported successfully")

                    for class_name in classes:
                        if hasattr(module, class_name):
                            logger.info(f"  ✅ Class '{class_name}' found")
                        else:
                            raise ImportError(f"Class '{class_name}' not found in {module_name}")

                except ImportError as e:
                    logger.error(f"❌ Failed to import {module_name}: {e}")
                    self.results["errors"].append(str(e))
                    self.results["failed"] += 1
                    return False

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ All imports successful\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ Import test failed: {e}\n")
            return False

    def test_dynamic_timeline_manager(self):
        """Test 2: DynamicTimelineManager functionality"""
        self.print_header("TEST 2: DynamicTimelineManager")

        test_name = "DynamicTimelineManager"
        try:
            from clarity_act_core import DynamicTimelineManager

            # Initialize
            dtm = DynamicTimelineManager()
            logger.info("✅ DynamicTimelineManager initialized")

            # Test get_default_params
            default_params = dtm._get_default_params()
            assert "ma_window" in default_params
            assert "stop_loss_percent" in default_params
            logger.info(f"✅ Default params: {default_params}")

            # Test calculate_optimal_params (with no vote date yet)
            params_no_date = dtm.calculate_optimal_params()
            assert params_no_date["ma_window"] == 10  # default
            logger.info("✅ Default params returned when vote date unknown")

            # Simulate vote date detection (Duration = 45 days)
            vote_date = datetime(2026, 6, 28)
            dtm.senate_floor_vote_date = vote_date
            params_with_date = dtm.calculate_optimal_params()
            assert params_with_date["ma_window"] == 10  # medium duration
            assert params_with_date["stop_loss_percent"] == -2.5
            logger.info(f"✅ Medium duration params (Duration={45}): {params_with_date}")

            # Test entry trigger status
            can_trade, reason = dtm.get_entry_trigger_status()
            assert can_trade == True
            logger.info(f"✅ Entry trigger status: {reason}")

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ DynamicTimelineManager test passed\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ DynamicTimelineManager test failed: {e}\n")
            return False

    def test_ratio_calculator(self):
        """Test 3: RatioCalculator functionality"""
        self.print_header("TEST 3: RatioCalculator")

        test_name = "RatioCalculator"
        try:
            from clarity_act_core import RatioCalculator

            # Initialize
            rc = RatioCalculator(ma_window=5)
            logger.info("✅ RatioCalculator initialized with MA window=5")

            # Test ratio calculation
            btc_price = 65000
            eth_price = 3500
            ratio = rc.calculate_ratio(btc_price, eth_price)
            expected_ratio = btc_price / eth_price
            assert abs(ratio - expected_ratio) < 0.0001
            logger.info(f"✅ Ratio calculation: {btc_price}/{eth_price} = {ratio:.4f}")

            # Test adding price data
            for i in range(10):
                btc = 65000 + i * 100
                eth = 3500 + i * 50
                rc.add_price_data(btc, eth)
            logger.info(f"✅ Added 10 price data points")

            # Test MA calculation
            ma = rc.calculate_ma()
            assert ma is not None
            assert isinstance(ma, float)
            logger.info(f"✅ Moving average (window=5): {ma:.4f}")

            # Test uptrend detection
            current_ratio = rc.ratio_history[-1]["ratio"]
            is_uptrend = rc.detect_uptrend(ma)
            logger.info(f"✅ Current ratio: {current_ratio:.4f}, MA: {ma:.4f}, Uptrend: {is_uptrend}")

            # Test with less data than window
            rc_small = RatioCalculator(ma_window=100)
            rc_small.add_price_data(65000, 3500)
            ma_small = rc_small.calculate_ma()
            assert ma_small is None
            logger.info("✅ MA returns None when insufficient data")

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ RatioCalculator test passed\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ RatioCalculator test failed: {e}\n")
            return False

    def test_signal_generator(self):
        """Test 4: SignalGenerator functionality"""
        self.print_header("TEST 4: SignalGenerator")

        test_name = "SignalGenerator"
        try:
            from clarity_act_core import SignalGenerator

            # Initialize
            sg = SignalGenerator(ma_window=5, stop_loss_percent=-2.5)
            logger.info("✅ SignalGenerator initialized")

            # Test entry signal (no position, uptrend expected)
            btc = 65000
            eth = 3500
            ma = 18.5  # expected MA
            entry, entry_reason = sg.entry_signal(btc, eth, ma)
            logger.info(f"✅ Entry signal test (uptrend): {entry} - {entry_reason}")

            # Test that position is now active
            assert sg.position_active == True
            assert sg.entry_price is not None
            logger.info(f"✅ Position active: {sg.position_active}, Entry price: {sg.entry_price:.2f}")

            # Test exit signal (no loss yet)
            exit_sig, exit_reason = sg.exit_signal(btc, eth)
            assert exit_sig == False
            logger.info(f"✅ Exit signal (no loss): {exit_sig} - {exit_reason}")

            # Test stop loss hit
            btc_loss = btc * 0.97  # 3% loss
            exit_sig_loss, exit_reason_loss = sg.exit_signal(btc_loss, eth)
            assert exit_sig_loss == True
            logger.info(f"✅ Exit signal (stop loss -3%): {exit_sig_loss} - {exit_reason_loss}")

            # Verify position closed
            assert sg.position_active == False
            logger.info("✅ Position closed after stop loss")

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ SignalGenerator test passed\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ SignalGenerator test failed: {e}\n")
            return False

    def test_configuration_manager(self):
        """Test 5: ConfigurationManager functionality"""
        self.print_header("TEST 5: ConfigurationManager")

        test_name = "ConfigurationManager"
        try:
            from clarity_act_core import ConfigurationManager

            # Initialize (should create default if not exists)
            cm = ConfigurationManager(config_file="test_config.json")
            logger.info("✅ ConfigurationManager initialized")

            # Check default config structure
            assert "strategy" in cm.config
            assert "parameters" in cm.config
            logger.info(f"✅ Config structure valid: {list(cm.config.keys())}")

            # Test update params
            new_params = {
                "ma_window": 14,
                "stop_loss_percent": -3.0
            }
            cm.update_params(new_params)
            assert cm.config["parameters"]["ma_window"] == 14
            logger.info(f"✅ Parameters updated: {new_params}")

            # Verify save
            import os
            assert os.path.exists("test_config.json")
            logger.info("✅ Config saved to file")

            # Load and verify
            cm2 = ConfigurationManager(config_file="test_config.json")
            assert cm2.config["parameters"]["ma_window"] == 14
            logger.info("✅ Config reloaded correctly")

            # Cleanup
            os.remove("test_config.json")
            logger.info("✅ Test config cleaned up")

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ ConfigurationManager test passed\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ ConfigurationManager test failed: {e}\n")
            return False

    def test_congress_gov_monitor(self):
        """Test 6: CongressGovMonitor functionality"""
        self.print_header("TEST 6: CongressGovMonitor")

        test_name = "CongressGovMonitor"
        try:
            from committee_vote_monitor import CongressGovMonitor

            # Initialize
            cgm = CongressGovMonitor()
            logger.info("✅ CongressGovMonitor initialized")

            # Test status check (may return pending if API is unavailable)
            status = cgm.check_committee_status()
            assert "status" in status
            assert "timestamp" in status
            logger.info(f"✅ Committee status check: {status['status']}")

            # Test vote details
            vote_details = cgm.get_vote_details()
            assert "republican_votes" in vote_details
            logger.info(f"✅ Vote details structure valid: {list(vote_details.keys())}")

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ CongressGovMonitor test passed\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ CongressGovMonitor test failed: {e}\n")
            return False

    def test_realtime_dashboard(self):
        """Test 7: RealtimeMonitorDashboard functionality"""
        self.print_header("TEST 7: RealtimeMonitorDashboard")

        test_name = "RealtimeMonitorDashboard"
        try:
            from realtime_monitor_dashboard import RealtimeMonitorDashboard
            import os

            # Initialize
            dashboard = RealtimeMonitorDashboard()
            logger.info("✅ RealtimeMonitorDashboard initialized")

            # Test dashboard file creation
            assert os.path.exists("dashboard.json")
            logger.info("✅ Dashboard file created")

            # Test load dashboard
            dash_data = dashboard.load_dashboard()
            assert dash_data is not None
            logger.info(f"✅ Dashboard loaded: {list(dash_data.keys())}")

            # Test update committee vote status
            dashboard.update_committee_vote_status("pending")
            dash_updated = dashboard.load_dashboard()
            assert dash_updated["committee_vote"]["status"] == "pending"
            logger.info("✅ Committee vote status updated")

            # Test update market data
            dashboard.update_market_data(65000, 3500, 18.57, 18.50)
            dash_market = dashboard.load_dashboard()
            assert dash_market["market_data"]["btc_price"] == 65000
            logger.info("✅ Market data updated")

            # Test add alert
            dashboard.add_alert("INFO", "Test alert message")
            dash_alerts = dashboard.load_dashboard()
            assert len(dash_alerts["alerts"]) > 0
            logger.info("✅ Alert added successfully")

            # Test summary generation
            summary = dashboard.get_summary()
            assert "CLARITY ACT" in summary
            assert "DASHBOARD" in summary
            logger.info("✅ Summary text generated")

            # Cleanup
            os.remove("dashboard.json")
            logger.info("✅ Test dashboard cleaned up")

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ RealtimeMonitorDashboard test passed\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ RealtimeMonitorDashboard test failed: {e}\n")
            return False

    def test_integration(self):
        """Test 8: Module integration"""
        self.print_header("TEST 8: Integration Test")

        test_name = "Integration"
        try:
            from clarity_act_core import (
                DynamicTimelineManager,
                RatioCalculator,
                SignalGenerator,
                ConfigurationManager
            )

            logger.info("✅ All core modules imported")

            # Simulate workflow
            dtm = DynamicTimelineManager()
            rc = RatioCalculator(ma_window=10)
            sg = SignalGenerator(ma_window=10, stop_loss_percent=-2.5)
            cm = ConfigurationManager()

            # Add market data
            for i in range(15):
                btc = 65000 + i * 100
                eth = 3500 + i * 50
                rc.add_price_data(btc, eth)

            # Calculate MA
            ma = rc.calculate_ma()
            assert ma is not None
            logger.info(f"✅ MA calculated: {ma:.4f}")

            # Get parameters
            params = dtm.calculate_optimal_params()
            logger.info(f"✅ Parameters calculated: MA={params['ma_window']}")

            # Generate signals
            entry, entry_reason = sg.entry_signal(65000, 3500, ma)
            logger.info(f"✅ Entry signal: {entry}")

            # Update config
            cm.update_params(params)
            logger.info(f"✅ Config updated with parameters")

            self.results["tests"][test_name] = "PASS"
            self.results["passed"] += 1
            logger.info("✅ Integration test passed\n")
            return True

        except Exception as e:
            self.results["tests"][test_name] = f"FAIL: {str(e)}"
            self.results["errors"].append(traceback.format_exc())
            self.results["failed"] += 1
            logger.error(f"❌ Integration test failed: {e}\n")
            return False

    def run_all_tests(self):
        """Run all tests in sequence"""
        print(f"\n{self.separator}")
        print("  CLARITY ACT PAIR TRADING v3.0 - COMPREHENSIVE TEST SUITE")
        print(f"{self.separator}\n")

        tests = [
            self.test_imports,
            self.test_dynamic_timeline_manager,
            self.test_ratio_calculator,
            self.test_signal_generator,
            self.test_configuration_manager,
            self.test_congress_gov_monitor,
            self.test_realtime_dashboard,
            self.test_integration
        ]

        for test_func in tests:
            try:
                test_func()
            except Exception as e:
                logger.error(f"Unexpected error in {test_func.__name__}: {e}")
                self.results["failed"] += 1
                self.results["errors"].append(str(e))

        # Final report
        self.print_summary()

    def print_summary(self):
        """Print final test summary"""
        print(f"\n{self.separator}")
        print("  FINAL TEST SUMMARY")
        print(f"{self.separator}\n")

        passed = self.results["passed"]
        failed = self.results["failed"]
        total = passed + failed

        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%\n")

        if failed == 0:
            print("🎉 ALL TESTS PASSED! System is fully functional.\n")
        else:
            print(f"⚠️  {failed} test(s) failed. See details above.\n")

        # Save results
        with open("test_results.json", "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        logger.info(f"Test results saved to test_results.json")

        return failed == 0


def main():
    """Main test execution"""
    runner = TestRunner()
    success = runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
