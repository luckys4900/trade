"""
Comprehensive Test Suite for Hyperliquid Live Trading Engine
Tests all 4 core modules: executor, position_manager, risk_manager, capital_manager
Author: Claude Code
Date: 2026-05-14
"""

import unittest
import json
import tempfile
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Mock ccxt before importing our modules
sys.modules['ccxt'] = MagicMock()

# Import modules under test
from hyperliquid_executor import HyperliquidExecutor
from position_manager import PositionManager, Position, PositionStatus
from risk_manager import RiskManager, RiskLevel
from capital_manager import CapitalManager, CapitalAllocation


class TestHyperliquidExecutor(unittest.TestCase):
    """Test HyperliquidExecutor class"""

    def setUp(self):
        """Set up test fixtures"""
        self.executor = HyperliquidExecutor(
            api_key="test_key",
            api_secret="test_secret",
            paper_trade=True,
            kelly_fraction=0.55
        )
        self.initial_balance = 10000

    def test_initialization(self):
        """Test executor initialization"""
        self.assertTrue(self.executor.paper_trade)
        self.assertEqual(self.executor.kelly_fraction, 0.55)
        self.assertEqual(self.executor.account_balance, 0)

    def test_position_size_calculation(self):
        """Test Kelly Criterion position sizing"""
        position_size = self.executor.calculate_position_size(
            account_balance=10000,
            expected_return=1.0,
            win_rate=0.60,
            stop_loss_percent=-2.5
        )

        self.assertGreater(position_size, 0)
        self.assertLess(position_size, 10000)

    def test_position_size_invalid_inputs(self):
        """Test position sizing with invalid inputs"""
        # Invalid win rate
        size1 = self.executor.calculate_position_size(
            account_balance=10000,
            expected_return=1.0,
            win_rate=0,
            stop_loss_percent=-2.5
        )
        self.assertGreater(size1, 0)

        # Invalid expected return
        size2 = self.executor.calculate_position_size(
            account_balance=10000,
            expected_return=0,
            win_rate=0.60,
            stop_loss_percent=-2.5
        )
        self.assertGreater(size2, 0)

    def test_market_order_execution_paper(self):
        """Test paper trading market order"""
        result = self.executor.execute_market_order(
            symbol='BTC/USDC',
            side='buy',
            position_size_usd=1000,
            current_price=50000
        )

        self.assertTrue(result['success'])
        self.assertIn('BTC/USDC', self.executor.open_positions)
        self.assertEqual(result['quantity'], 1000 / 50000)

    def test_close_position(self):
        """Test position closing"""
        # Open position
        self.executor.execute_market_order(
            symbol='BTC/USDC',
            side='buy',
            position_size_usd=1000,
            current_price=50000
        )

        # Close position
        result = self.executor.close_position(
            symbol='BTC/USDC',
            current_price=51000
        )

        self.assertTrue(result['success'])
        self.assertNotIn('BTC/USDC', self.executor.open_positions)
        self.assertGreater(result['pnl'], 0)

    def test_trailing_stop(self):
        """Test trailing stop functionality"""
        # Open position
        self.executor.execute_market_order(
            symbol='BTC/USDC',
            side='buy',
            position_size_usd=1000,
            current_price=50000
        )

        # Price goes up to 51000 - trailing stop should not trigger
        result1 = self.executor.apply_trailing_stop(
            symbol='BTC/USDC',
            current_price=51000,
            trailing_stop_percent=0.75
        )
        # Either None or False, but position should still be open
        self.assertIn('BTC/USDC', self.executor.open_positions)

        # Test that trailing stop logic exists and position management works
        status = self.executor.get_position_status('BTC/USDC')
        self.assertIsNotNone(status)
        self.assertEqual(status['side'], 'buy')

    def test_get_position_status(self):
        """Test getting position status"""
        self.executor.execute_market_order(
            symbol='BTC/USDC',
            side='buy',
            position_size_usd=1000,
            current_price=50000
        )

        status = self.executor.get_position_status('BTC/USDC')
        self.assertIsNotNone(status)
        self.assertEqual(status['side'], 'buy')

    def test_trade_history(self):
        """Test trade history tracking"""
        self.executor.execute_market_order(
            symbol='BTC/USDC',
            side='buy',
            position_size_usd=1000,
            current_price=50000
        )

        history = self.executor.get_trade_history()
        self.assertEqual(len(history), 1)

    def test_validate_trading_pair(self):
        """Test trading pair validation"""
        # Paper trading should return True
        result = self.executor.validate_trading_pair('BTC/USDC')
        self.assertTrue(result)


class TestPositionManager(unittest.TestCase):
    """Test PositionManager class"""

    def setUp(self):
        """Set up test fixtures"""
        self.manager = PositionManager()

    def test_position_initialization(self):
        """Test Position object initialization"""
        pos = Position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        self.assertEqual(pos.symbol, 'BTC/USDC')
        self.assertEqual(pos.side, 'buy')
        self.assertEqual(pos.status, PositionStatus.OPEN)

    def test_position_price_update(self):
        """Test position price updates"""
        pos = Position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        pos.update_price(51000)
        self.assertEqual(pos.current_price, 51000)
        self.assertGreater(pos.get_unrealized_pnl(), 0)

    def test_position_pnl_calculation(self):
        """Test P&L calculation"""
        pos = Position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        pos.update_price(51000)
        pnl = pos.get_unrealized_pnl()
        pnl_percent = pos.get_unrealized_pnl_percent()

        self.assertAlmostEqual(pnl, 20, places=2)
        self.assertAlmostEqual(pnl_percent, 2.0, places=2)

    def test_trailing_stop_calculation(self):
        """Test trailing stop price calculation"""
        pos = Position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000,
            trailing_stop_percent=0.75
        )

        pos.update_price(51000)
        stop_price = pos.get_trailing_stop_price()
        expected_stop = 51000 * (1 - 0.0075)

        self.assertAlmostEqual(stop_price, expected_stop, places=2)

    def test_open_position(self):
        """Test opening position via manager"""
        pos = self.manager.open_position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        self.assertIn('BTC/USDC', self.manager.open_positions)
        self.assertEqual(len(self.manager.open_positions), 1)

    def test_close_position(self):
        """Test closing position via manager"""
        self.manager.open_position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        pnl, pnl_percent = self.manager.close_position(
            symbol='BTC/USDC',
            exit_price=51000,
            exit_reason="Stop loss"
        )

        self.assertEqual(len(self.manager.open_positions), 0)
        self.assertEqual(len(self.manager.closed_positions), 1)
        self.assertGreater(pnl, 0)

    def test_update_position_price(self):
        """Test updating position price"""
        self.manager.open_position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        self.manager.update_position_price('BTC/USDC', 51000)
        pos = self.manager.get_position('BTC/USDC')

        self.assertEqual(pos.current_price, 51000)

    def test_multiple_positions(self):
        """Test managing multiple positions"""
        self.manager.open_position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        self.manager.open_position(
            symbol='ETH/USDC',
            side='sell',
            entry_price=3000,
            quantity=0.5,
            position_size_usd=1500
        )

        self.assertEqual(self.manager.get_position_count(), 2)
        self.assertEqual(self.manager.get_total_exposure(), 2500)

    def test_position_history(self):
        """Test position history tracking"""
        self.manager.open_position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        self.manager.close_position('BTC/USDC', 51000)

        history = self.manager.get_position_history()
        self.assertEqual(len(history), 1)


class TestRiskManager(unittest.TestCase):
    """Test RiskManager class"""

    def setUp(self):
        """Set up test fixtures"""
        self.manager = RiskManager(
            initial_capital=10000,
            max_daily_loss_percent=-5.0,
            max_position_loss_percent=-2.5,
            max_position_size_percent=0.25
        )

    def test_initialization(self):
        """Test risk manager initialization"""
        self.assertEqual(self.manager.initial_capital, 10000)
        self.assertEqual(self.manager.current_capital, 10000)

    def test_daily_loss_limit_check(self):
        """Test daily loss limit checking"""
        # No loss - reset first
        self.manager.daily_loss = 0
        exceeded, msg = self.manager.check_daily_loss_limit()
        self.assertFalse(exceeded)

        # Exceed limit
        self.manager.daily_loss = -600
        exceeded, msg = self.manager.check_daily_loss_limit()
        self.assertTrue(exceeded)

    def test_emergency_stop(self):
        """Test emergency stop loss"""
        # Simulate 10% loss
        self.manager.current_capital = 9000

        triggered, msg = self.manager.check_emergency_stop()
        self.assertTrue(triggered)

    def test_risk_level_assessment(self):
        """Test risk level assessment"""
        self.manager.current_capital = 10000
        level = self.manager.assess_risk_level()
        self.assertEqual(level, RiskLevel.SAFE)

        self.manager.current_capital = 9500  # 5% loss
        level = self.manager.assess_risk_level()
        self.assertIn(level, [RiskLevel.CAUTION, RiskLevel.WARNING])

    def test_position_size_validation(self):
        """Test position size validation"""
        valid, msg = self.manager.validate_position_size('BTC/USDC', 2500)
        self.assertTrue(valid)

        valid, msg = self.manager.validate_position_size('BTC/USDC', 3000)
        self.assertFalse(valid)

    def test_stop_loss_calculation(self):
        """Test stop loss price calculation"""
        stop_price = self.manager.set_stop_loss('BTC/USDC', 50000, side='buy')
        expected_stop = 50000 * (1 - 0.025)

        self.assertAlmostEqual(stop_price, expected_stop, places=2)

    def test_position_risk_monitoring(self):
        """Test position risk monitoring"""
        metrics = self.manager.monitor_position_risk(
            symbol='BTC/USDC',
            entry_price=50000,
            current_price=51000,
            position_size_usd=1000,
            side='buy'
        )

        self.assertIn('unrealized_pnl', metrics)
        self.assertGreater(metrics['unrealized_pnl'], 0)
        self.assertEqual(metrics['stop_loss_triggered'], False)

    def test_portfolio_risk_summary(self):
        """Test portfolio risk summary"""
        summary = self.manager.get_portfolio_risk_summary()

        self.assertIn('risk_level', summary)
        self.assertIn('total_loss_percent', summary)
        self.assertIn('positions_at_risk_count', summary)

    def test_position_reduction(self):
        """Test position reduction calculation"""
        new_size = self.manager.reduce_position_size(1000, reduction_percent=0.50)
        self.assertEqual(new_size, 500)

    def test_leverage_limit(self):
        """Test leverage limit based on risk level"""
        self.manager.current_capital = 10000
        leverage = self.manager.get_leverage_limit()
        self.assertEqual(leverage, 3.0)

        self.manager.current_capital = 9500
        leverage = self.manager.get_leverage_limit()
        self.assertLessEqual(leverage, 3.0)


class TestCapitalManager(unittest.TestCase):
    """Test CapitalManager class"""

    def setUp(self):
        """Set up test fixtures"""
        self.manager = CapitalManager(
            initial_capital=10000,
            max_leverage=3.0,
            allocation_strategy=CapitalAllocation.KELLY,
            kelly_fraction=0.55
        )

    def test_initialization(self):
        """Test capital manager initialization"""
        self.assertEqual(self.manager.initial_capital, 10000)
        self.assertEqual(self.manager.available_capital, 10000)
        self.assertEqual(self.manager.allocated_capital, 0)

    def test_capital_allocation(self):
        """Test capital allocation"""
        success, amount, msg = self.manager.allocate_capital(1000, purpose="position")

        self.assertTrue(success)
        self.assertEqual(self.manager.available_capital, 9000)
        self.assertEqual(self.manager.allocated_capital, 1000)

    def test_capital_allocation_insufficient(self):
        """Test allocation with insufficient capital"""
        success, amount, msg = self.manager.allocate_capital(15000)

        self.assertFalse(success)
        self.assertEqual(self.manager.available_capital, 10000)

    def test_capital_release(self):
        """Test capital release"""
        self.manager.allocate_capital(1000)

        success, amount, msg = self.manager.release_capital(1000)

        self.assertTrue(success)
        self.assertEqual(self.manager.available_capital, 10000)
        self.assertEqual(self.manager.allocated_capital, 0)

    def test_max_position_size(self):
        """Test maximum position size calculation"""
        max_size = self.manager.calculate_max_position_size(
            entry_price=50000,
            expected_return_percent=1.0,
            win_rate=0.60,
            stop_loss_percent=-2.5
        )

        self.assertGreater(max_size, 0)
        self.assertLess(max_size, 10000)

    def test_required_margin(self):
        """Test required margin calculation"""
        margin = self.manager.calculate_required_margin(
            position_size_usd=1000,
            leverage=2.0
        )

        self.assertEqual(margin, 500)

    def test_risk_per_trade(self):
        """Test risk per trade calculation"""
        risk = self.manager.calculate_risk_per_trade(
            position_size_usd=1000,
            stop_loss_percent=-2.5
        )

        self.assertEqual(risk, 25)

    def test_pnl_update(self):
        """Test P&L update"""
        self.manager.update_pnl(realized_change=100, unrealized_change=50)

        self.assertEqual(self.manager.realized_pnl, 100)
        self.assertEqual(self.manager.unrealized_pnl, 50)
        self.assertEqual(self.manager.total_capital, 10150)

    def test_withdrawal_calculation(self):
        """Test profit available for withdrawal"""
        self.manager.update_pnl(realized_change=500)

        withdrawable = self.manager.get_profit_available_for_withdrawal(
            min_operating_capital_percent=0.20
        )

        self.assertGreater(withdrawable, 0)

    def test_capital_adequacy(self):
        """Test capital adequacy check"""
        adequate, msg = self.manager.check_capital_adequacy(2000)
        self.assertTrue(adequate)

        adequate, msg = self.manager.check_capital_adequacy(15000)
        self.assertFalse(adequate)

    def test_capital_status(self):
        """Test capital status report"""
        status = self.manager.get_capital_status()

        self.assertIn('available_capital', status)
        self.assertIn('allocated_capital', status)
        self.assertIn('total_capital', status)

    def test_capital_evolution(self):
        """Test capital history tracking"""
        self.manager.record_capital_snapshot()
        self.manager.update_pnl(realized_change=100)
        self.manager.record_capital_snapshot()

        history = self.manager.get_capital_evolution()
        self.assertGreaterEqual(len(history), 2)

    def test_drawdown_estimation(self):
        """Test drawdown estimation"""
        self.manager.record_capital_snapshot()
        self.manager.update_pnl(realized_change=-500)
        self.manager.record_capital_snapshot()

        drawdown = self.manager.estimate_drawdown()
        self.assertLess(drawdown, 0)


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple modules"""

    def setUp(self):
        """Set up test fixtures"""
        self.executor = HyperliquidExecutor(
            api_key="test",
            api_secret="test",
            paper_trade=True
        )
        self.position_mgr = PositionManager()
        self.risk_mgr = RiskManager(10000)
        self.capital_mgr = CapitalManager(10000)

    def test_complete_trading_flow(self):
        """Test complete trading flow"""
        # Ensure capital is initialized properly
        self.capital_mgr.current_capital = 10000

        # Check if we can enter
        can_enter, msg = self.risk_mgr.validate_entry(
            symbol='BTC/USDC',
            position_size_usd=1000
        )
        self.assertTrue(can_enter)

        # Allocate capital
        success, _, _ = self.capital_mgr.allocate_capital(1000)
        self.assertTrue(success)

        # Open position
        pos = self.position_mgr.open_position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )
        self.assertIsNotNone(pos)

        # Update price
        self.position_mgr.update_position_price('BTC/USDC', 51000)
        pos = self.position_mgr.get_position('BTC/USDC')
        self.assertEqual(pos.current_price, 51000)

        # Close position
        pnl, pnl_percent = self.position_mgr.close_position(
            'BTC/USDC', 51000
        )
        self.assertGreater(pnl, 0)

        # Release capital
        success, _, _ = self.capital_mgr.release_capital(1000)
        self.assertTrue(success)

    def test_risk_management_integration(self):
        """Test risk management integration"""
        # Open position
        self.position_mgr.open_position(
            symbol='BTC/USDC',
            side='buy',
            entry_price=50000,
            quantity=0.02,
            position_size_usd=1000
        )

        # Monitor risk
        metrics = self.risk_mgr.monitor_position_risk(
            symbol='BTC/USDC',
            entry_price=50000,
            current_price=48750,
            position_size_usd=1000,
            side='buy'
        )

        # Should trigger stop loss
        self.assertTrue(metrics['stop_loss_triggered'])

        # Get risk alerts
        alerts = self.risk_mgr.get_risk_alerts()
        self.assertGreater(len(alerts), 0)


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)
