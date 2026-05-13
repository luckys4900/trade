#!/usr/bin/env python3
"""
Quick Start Script - Clarity Act Pair Trading v3.0 Daily Workflow
本番運用スクリプトの簡単実行ガイド

Usage:
    python3 START_WORKFLOW.py          # Run main workflow
    python3 START_WORKFLOW.py --test   # Run integration tests
    python3 START_WORKFLOW.py --dry    # Dry run (no real trading)
    python3 START_WORKFLOW.py --report # Generate reports
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Clarity Act Pair Trading v3.0 - Daily Workflow"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run integration tests"
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Dry run (no real trading)"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate reports"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check system status"
    )

    args = parser.parse_args()

    # Ensure logs directory exists
    logs_dir = Path('/Users/user/Desktop/trade/data/logs')
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Clarity Act Pair Trading v3.0 ===")
    logger.info(f"Started at {datetime.now().isoformat()}")

    if args.test:
        return run_tests()
    elif args.dry:
        return run_dry()
    elif args.report:
        return generate_reports()
    elif args.status:
        return check_status()
    else:
        return run_main_workflow()


def run_tests():
    """Run integration tests"""
    logger.info("\n=== Running Integration Tests ===\n")
    try:
        from test_daily_workflow import WorkflowTestSuite

        suite = WorkflowTestSuite()
        passed, failed = suite.run_all_tests()

        if failed == 0:
            logger.info("\n✓ All tests passed!")
            return 0
        else:
            logger.error(f"\n✗ {failed} test(s) failed")
            return 1

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        return 1


def run_dry():
    """Dry run without real trading"""
    logger.info("\n=== DRY RUN (No Real Trading) ===\n")
    try:
        from main_workflow_hyperliquid import MainWorkflowHyperliquid

        workflow = MainWorkflowHyperliquid()

        logger.info("Running initialization phase...")
        result = workflow.initialization_phase()
        if not result:
            logger.error("Initialization failed")
            return 1

        logger.info("Running daily execution phase...")
        result = workflow.daily_execution_phase()
        if not result:
            logger.error("Daily execution failed")
            return 1

        logger.info("Running hourly execution phase...")
        result = workflow.hourly_execution_phase()
        if not result:
            logger.error("Hourly execution failed")
            return 1

        logger.info("Running monitoring phase...")
        result = workflow.monitoring_phase()
        if not result:
            logger.error("Monitoring failed")
            return 1

        logger.info("\n✓ Dry run completed successfully!")
        return 0

    except Exception as e:
        logger.error(f"Dry run failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def generate_reports():
    """Generate current reports"""
    logger.info("\n=== Generating Reports ===\n")
    try:
        from trade_logger import TradeLogger
        from alert_manager import AlertManager
        from error_recovery import ErrorRecovery

        # Trade reports
        logger.info("Generating trade reports...")
        trade_logger = TradeLogger()
        daily = trade_logger.generate_daily_report()
        trade_logger.save_report(daily, "daily")

        weekly = trade_logger.generate_weekly_report()
        trade_logger.save_report(weekly, "weekly")

        monthly = trade_logger.generate_monthly_report()
        trade_logger.save_report(monthly, "monthly")

        # Alert reports
        logger.info("Generating alert reports...")
        alert_mgr = AlertManager()
        alert_mgr.export_alerts_report()

        # Error reports
        logger.info("Generating error reports...")
        error_recovery = ErrorRecovery()
        error_recovery.export_error_report()

        logger.info("\n✓ Reports generated successfully!")
        logger.info(f"Reports saved to: /Users/user/Desktop/trade/data/logs/")
        return 0

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def check_status():
    """Check system status"""
    logger.info("\n=== System Status ===\n")
    try:
        from trade_logger import TradeLogger
        from performance_analyzer import PerformanceAnalyzer
        from alert_manager import AlertManager
        from error_recovery import ErrorRecovery

        # Trade status
        trade_logger = TradeLogger()
        open_trades = trade_logger.get_open_trades()
        closed_trades = trade_logger.get_closed_trades()
        logger.info(f"Open trades: {len(open_trades)}")
        logger.info(f"Closed trades: {len(closed_trades)}")

        # Performance status
        analyzer = PerformanceAnalyzer()
        metrics = analyzer.get_current_metrics()
        if metrics:
            logger.info(f"Win rate: {metrics.win_rate*100:.1f}%")
            logger.info(f"Sharpe ratio: {metrics.sharpe_ratio:.2f}")
            logger.info(f"Max drawdown: {metrics.max_drawdown_percent:.2f}%")
        else:
            logger.info("No performance metrics yet")

        # Alert status
        alert_mgr = AlertManager()
        summary = alert_mgr.get_alert_summary()
        logger.info(f"Total alerts: {summary.get('total_alerts', 0)}")
        logger.info(f"Pending alerts: {summary.get('pending', 0)}")

        # Error status
        error_recovery = ErrorRecovery()
        error_summary = error_recovery.get_error_summary()
        logger.info(f"Total errors: {error_summary.get('total_errors', 0)}")
        logger.info(f"System healthy: {error_summary.get('system_healthy', True)}")

        logger.info("\n✓ Status check completed!")
        return 0

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def run_main_workflow():
    """Run main continuous workflow"""
    logger.info("\n=== Starting Main Workflow ===\n")
    logger.info("This will run continuously. Press Ctrl+C to stop.")
    logger.info("\n")

    try:
        from main_workflow_hyperliquid import MainWorkflowHyperliquid

        workflow = MainWorkflowHyperliquid()
        success = workflow.run_continuous()

        if success:
            logger.info("\n✓ Workflow completed successfully")
            return 0
        else:
            logger.error("\n✗ Workflow failed")
            return 1

    except KeyboardInterrupt:
        logger.info("\n\nWorkflow interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
