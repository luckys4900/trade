"""
Capital Manager - Clarity Act v3.0
Manages available capital, leverage, and position sizing
Author: Claude Code
Date: 2026-05-14
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CapitalAllocation(Enum):
    """Capital allocation strategy"""
    KELLY = "kelly"
    FIXED_PERCENT = "fixed_percent"
    DYNAMIC = "dynamic"


class CapitalManager:
    """
    Manages available capital, leverage, and position sizing
    """

    def __init__(
        self,
        initial_capital: float,
        max_leverage: float = 3.0,
        allocation_strategy: CapitalAllocation = CapitalAllocation.KELLY,
        kelly_fraction: float = 0.55
    ):
        """
        Initialize capital manager

        Args:
            initial_capital: Starting capital
            max_leverage: Maximum leverage allowed (1.0-3.0)
            allocation_strategy: Capital allocation strategy
            kelly_fraction: Kelly Criterion fraction
        """
        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self.allocated_capital = 0
        self.max_leverage = min(max(max_leverage, 1.0), 3.0)
        self.allocation_strategy = allocation_strategy
        self.kelly_fraction = kelly_fraction

        self.realized_pnl = 0
        self.unrealized_pnl = 0
        self.total_capital = initial_capital

        self.capital_history = [{
            'timestamp': datetime.now().isoformat(),
            'available': self.available_capital,
            'allocated': self.allocated_capital,
            'total': self.total_capital,
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': self.unrealized_pnl
        }]

    def allocate_capital(
        self,
        amount: float,
        purpose: str = "position"
    ) -> Tuple[bool, float, str]:
        """
        Allocate capital for trading

        Args:
            amount: Amount to allocate
            purpose: Purpose of allocation (position, risk_reserve, etc.)

        Returns:
            (success, allocated_amount, reason)
        """
        if amount <= 0:
            return False, 0, "Allocation amount must be positive"

        if amount > self.available_capital:
            return False, 0, (
                f"Insufficient capital: {amount:.2f} > {self.available_capital:.2f}"
            )

        self.available_capital -= amount
        self.allocated_capital += amount

        logger.info(f"Capital allocated: ${amount:.2f} for {purpose}")
        logger.info(
            f"Capital status: Available ${self.available_capital:.2f}, "
            f"Allocated ${self.allocated_capital:.2f}"
        )

        return True, amount, "Capital allocated successfully"

    def release_capital(
        self,
        amount: float,
        reason: str = "position_closed"
    ) -> Tuple[bool, float, str]:
        """
        Release allocated capital back to available pool

        Args:
            amount: Amount to release
            reason: Reason for release

        Returns:
            (success, released_amount, reason)
        """
        if amount <= 0:
            return False, 0, "Release amount must be positive"

        if amount > self.allocated_capital:
            return False, 0, (
                f"Cannot release ${amount:.2f}, only ${self.allocated_capital:.2f} allocated"
            )

        self.available_capital += amount
        self.allocated_capital -= amount

        logger.info(f"Capital released: ${amount:.2f} - {reason}")

        return True, amount, "Capital released successfully"

    def calculate_max_position_size(
        self,
        entry_price: float,
        expected_return_percent: float,
        win_rate: float = 0.60,
        stop_loss_percent: float = -2.5
    ) -> float:
        """
        Calculate maximum position size based on Kelly Criterion

        Args:
            entry_price: Entry price
            expected_return_percent: Expected return (%)
            win_rate: Win rate (0-1)
            stop_loss_percent: Stop loss (%)

        Returns:
            Maximum position size in USD
        """
        if win_rate <= 0 or win_rate >= 1:
            # Conservative fallback
            return self.available_capital * 0.05

        p = win_rate
        q = 1 - p

        # Calculate b (loss/win ratio)
        if expected_return_percent == 0:
            return self.available_capital * 0.05

        win_amount = abs(expected_return_percent)
        loss_amount = abs(stop_loss_percent)
        b = loss_amount / win_amount if win_amount > 0 else 1

        # Kelly calculation
        kelly_pct = (b * p + p - q) / b

        # Apply Kelly fraction
        fractional_kelly = kelly_pct * self.kelly_fraction

        # Bound between 1% and max leverage
        fractional_kelly = max(0.01, min(fractional_kelly, self.max_leverage / 10))

        max_position = self.available_capital * fractional_kelly

        logger.info(
            f"Max position size: ${max_position:,.2f} "
            f"(Kelly {kelly_pct:.2%}, Fractional {fractional_kelly:.2%})"
        )

        return max_position

    def calculate_required_margin(
        self,
        position_size_usd: float,
        leverage: float = 1.0
    ) -> float:
        """
        Calculate required margin for position

        Args:
            position_size_usd: Position size in USD
            leverage: Leverage multiplier

        Returns:
            Required margin in USD
        """
        if leverage < 1.0 or leverage > self.max_leverage:
            logger.warning(
                f"Leverage {leverage} outside allowed range [1.0, {self.max_leverage}]"
            )
            leverage = min(max(leverage, 1.0), self.max_leverage)

        required_margin = position_size_usd / leverage

        logger.info(
            f"Required margin: ${required_margin:,.2f} "
            f"(Position ${position_size_usd:,.2f} at {leverage}x leverage)"
        )

        return required_margin

    def calculate_risk_per_trade(
        self,
        position_size_usd: float,
        stop_loss_percent: float = -2.5
    ) -> float:
        """
        Calculate dollar risk per trade

        Args:
            position_size_usd: Position size in USD
            stop_loss_percent: Stop loss level (%)

        Returns:
            Risk amount in USD
        """
        risk = position_size_usd * (abs(stop_loss_percent) / 100)

        logger.info(
            f"Risk per trade: ${risk:,.2f} "
            f"(Position ${position_size_usd:,.2f} with {stop_loss_percent:.2f}% stop)"
        )

        return risk

    def update_pnl(
        self,
        realized_change: float = 0,
        unrealized_change: float = 0
    ) -> None:
        """
        Update P&L tracking

        Args:
            realized_change: Change in realized P&L
            unrealized_change: Change in unrealized P&L
        """
        self.realized_pnl += realized_change
        self.unrealized_pnl += unrealized_change

        self.total_capital = (
            self.initial_capital + self.realized_pnl + self.unrealized_pnl
        )

        logger.info(
            f"P&L updated: Realized ${self.realized_pnl:,.2f}, "
            f"Unrealized ${self.unrealized_pnl:,.2f}, "
            f"Total ${self.total_capital:,.2f}"
        )

    def get_profit_available_for_withdrawal(
        self,
        min_operating_capital_percent: float = 0.20
    ) -> float:
        """
        Calculate profit available for withdrawal

        Args:
            min_operating_capital_percent: Minimum operating capital as % of initial

        Returns:
            Withdrawable profit in USD
        """
        min_operating = self.initial_capital * min_operating_capital_percent
        available_for_withdrawal = max(0, self.total_capital - min_operating)

        logger.info(
            f"Profit available for withdrawal: ${available_for_withdrawal:,.2f} "
            f"(Min operating capital: ${min_operating:,.2f})"
        )

        return available_for_withdrawal

    def check_capital_adequacy(
        self,
        proposed_allocation: float
    ) -> Tuple[bool, str]:
        """
        Check if sufficient capital available

        Args:
            proposed_allocation: Proposed allocation amount

        Returns:
            (adequate, reason)
        """
        if proposed_allocation <= 0:
            return True, "No allocation needed"

        if proposed_allocation > self.available_capital:
            return False, (
                f"Insufficient capital: ${proposed_allocation:,.2f} > "
                f"${self.available_capital:,.2f} available"
            )

        # Check leverage constraint
        current_leverage = self.allocated_capital / self.total_capital if self.total_capital > 0 else 0
        new_leverage = (self.allocated_capital + proposed_allocation) / self.total_capital

        if new_leverage > self.max_leverage:
            return False, (
                f"Leverage would exceed limit: {new_leverage:.2f}x > {self.max_leverage:.2f}x"
            )

        return True, "Sufficient capital available"

    def get_capital_status(self) -> Dict:
        """Get comprehensive capital status"""
        return {
            'timestamp': datetime.now().isoformat(),
            'initial_capital': self.initial_capital,
            'available_capital': self.available_capital,
            'allocated_capital': self.allocated_capital,
            'total_capital': self.total_capital,
            'realized_pnl': self.realized_pnl,
            'realized_pnl_percent': (self.realized_pnl / self.initial_capital) * 100,
            'unrealized_pnl': self.unrealized_pnl,
            'unrealized_pnl_percent': (self.unrealized_pnl / self.initial_capital) * 100,
            'total_return_percent': ((self.total_capital - self.initial_capital) / self.initial_capital) * 100,
            'current_leverage': (
                (self.allocated_capital / self.total_capital)
                if self.total_capital > 0 else 0
            ),
            'max_leverage': self.max_leverage,
            'allocation_strategy': self.allocation_strategy.value,
            'kelly_fraction': self.kelly_fraction
        }

    def get_capital_allocation_breakdown(self) -> Dict:
        """Get breakdown of capital allocation"""
        utilization_percent = (
            (self.allocated_capital / self.total_capital) * 100
            if self.total_capital > 0 else 0
        )

        return {
            'timestamp': datetime.now().isoformat(),
            'available_capital': self.available_capital,
            'available_percent': (
                (self.available_capital / self.total_capital) * 100
                if self.total_capital > 0 else 0
            ),
            'allocated_capital': self.allocated_capital,
            'allocated_percent': utilization_percent,
            'total_capital': self.total_capital,
            'allocation_efficiency': utilization_percent
        }

    def record_capital_snapshot(self) -> None:
        """Record capital status snapshot"""
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'available': self.available_capital,
            'allocated': self.allocated_capital,
            'total': self.total_capital,
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': self.unrealized_pnl
        }

        self.capital_history.append(snapshot)

        # Limit history to last 1000 snapshots
        if len(self.capital_history) > 1000:
            self.capital_history = self.capital_history[-1000:]

    def get_capital_evolution(self, limit: int = None) -> list:
        """
        Get capital evolution over time

        Args:
            limit: Maximum number of snapshots to return

        Returns:
            Capital history snapshots
        """
        if limit:
            return self.capital_history[-limit:]
        return self.capital_history.copy()

    def estimate_drawdown(self) -> float:
        """
        Estimate current drawdown from peak

        Returns:
            Drawdown percentage
        """
        peak_capital = max(
            [snapshot['total'] for snapshot in self.capital_history]
        ) if self.capital_history else self.initial_capital

        current_drawdown = ((self.total_capital - peak_capital) / peak_capital) * 100

        return current_drawdown

    def get_capital_risk_metrics(self) -> Dict:
        """Get risk metrics based on capital"""
        return {
            'timestamp': datetime.now().isoformat(),
            'total_capital': self.total_capital,
            'peak_capital': max(
                [snapshot['total'] for snapshot in self.capital_history]
            ) if self.capital_history else self.initial_capital,
            'current_drawdown_percent': self.estimate_drawdown(),
            'capital_efficiency': (
                (self.total_capital / self.initial_capital)
                if self.initial_capital > 0 else 0
            ),
            'available_capital_percent': (
                (self.available_capital / self.total_capital) * 100
                if self.total_capital > 0 else 0
            ),
            'allocated_capital_percent': (
                (self.allocated_capital / self.total_capital) * 100
                if self.total_capital > 0 else 0
            ),
            'current_leverage': (
                (self.allocated_capital / self.total_capital)
                if self.total_capital > 0 else 0
            ),
            'max_leverage': self.max_leverage
        }
