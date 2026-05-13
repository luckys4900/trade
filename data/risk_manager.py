"""
Risk Manager - Clarity Act v3.0
Manages trading risks, stop-loss, and position limits
Author: Claude Code
Date: 2026-05-14
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level enumeration"""
    SAFE = "safe"
    CAUTION = "caution"
    WARNING = "warning"
    CRITICAL = "critical"


class RiskManager:
    """
    Manages trading risks including:
    - Daily maximum loss limit
    - Stop-loss management
    - Position sizing limits
    - Risk alerts and position reduction
    """

    def __init__(
        self,
        initial_capital: float,
        max_daily_loss_percent: float = -5.0,
        max_position_loss_percent: float = -2.5,
        max_position_size_percent: float = 0.25,
        emergency_loss_limit_percent: float = -10.0
    ):
        """
        Initialize risk manager

        Args:
            initial_capital: Initial account capital
            max_daily_loss_percent: Maximum daily loss allowed (%)
            max_position_loss_percent: Maximum loss per position (%)
            max_position_size_percent: Maximum position size as % of capital
            emergency_loss_limit_percent: Emergency stop loss (%)
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_position_loss_percent = max_position_loss_percent
        self.max_position_size_percent = max_position_size_percent
        self.emergency_loss_limit_percent = emergency_loss_limit_percent

        self.daily_loss = 0
        self.daily_trades = 0
        self.daily_start_time = datetime.now()

        self.risk_events = []
        self.positions_at_risk = {}

    def reset_daily_stats(self) -> None:
        """Reset daily statistics"""
        self.daily_loss = 0
        self.daily_trades = 0
        self.daily_start_time = datetime.now()
        logger.info("Daily statistics reset")

    def update_capital(self, new_capital: float) -> None:
        """Update current capital level"""
        previous_capital = self.current_capital
        self.current_capital = new_capital

        # Calculate daily loss
        daily_change = new_capital - previous_capital
        if daily_change < 0:
            self.daily_loss += daily_change

        logger.info(f"Capital updated: ${previous_capital:,.2f} -> ${new_capital:,.2f}")

    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """
        Check if daily loss limit exceeded

        Returns:
            (limit_exceeded, reason)
        """
        max_loss = self.initial_capital * (self.max_daily_loss_percent / 100)
        percent = (self.daily_loss / self.initial_capital) * 100 if self.initial_capital > 0 else 0

        # max_loss is negative (e.g., -500 for -5%)
        # daily_loss becomes more negative as losses increase
        # If daily_loss < max_loss (e.g., -600 < -500), then limit is exceeded
        if self.daily_loss >= max_loss:  # Use >= for negative values
            return False, f"Daily loss within limit: {percent:.2f}%"

        return True, f"Daily loss limit exceeded: {percent:.2f}% > {self.max_daily_loss_percent:.2f}%"

    def check_emergency_stop(self) -> Tuple[bool, str]:
        """
        Check if emergency stop loss triggered

        Returns:
            (stop_triggered, reason)
        """
        total_loss = self.current_capital - self.initial_capital
        loss_percent = (total_loss / self.initial_capital) * 100 if self.initial_capital > 0 else 0

        # emergency_loss_limit_percent is negative (e.g., -10%)
        # loss_percent becomes more negative as losses increase
        # If loss_percent < emergency_limit (e.g., -11% < -10%), then stop is triggered
        if loss_percent <= self.emergency_loss_limit_percent:
            return True, f"EMERGENCY STOP: Loss {loss_percent:.2f}% exceeds {self.emergency_loss_limit_percent:.2f}%"

        return False, f"Capital safe: {loss_percent:.2f}%"

    def assess_risk_level(self) -> RiskLevel:
        """
        Assess current risk level

        Returns:
            RiskLevel enum
        """
        loss_percent = ((self.current_capital - self.initial_capital) / self.initial_capital) * 100

        if loss_percent <= self.emergency_loss_limit_percent:
            return RiskLevel.CRITICAL

        if loss_percent <= (self.max_daily_loss_percent * 0.5):
            return RiskLevel.WARNING

        if loss_percent <= (self.max_daily_loss_percent * 0.25):
            return RiskLevel.CAUTION

        return RiskLevel.SAFE

    def validate_position_size(
        self,
        symbol: str,
        position_size_usd: float
    ) -> Tuple[bool, str]:
        """
        Validate position size against limits

        Args:
            symbol: Trading pair
            position_size_usd: Proposed position size

        Returns:
            (valid, reason)
        """
        max_position = self.current_capital * self.max_position_size_percent

        if position_size_usd > max_position:
            return False, (
                f"Position size ${position_size_usd:,.2f} exceeds limit ${max_position:,.2f}"
            )

        return True, f"Position size valid: ${position_size_usd:,.2f}"

    def set_stop_loss(
        self,
        symbol: str,
        entry_price: float,
        side: str = 'buy'
    ) -> float:
        """
        Calculate stop-loss price for position

        Args:
            symbol: Trading pair
            entry_price: Entry price
            side: 'buy' or 'sell'

        Returns:
            Stop-loss price
        """
        loss_percent = self.max_position_loss_percent / 100

        if side == 'buy':
            stop_price = entry_price * (1 + loss_percent)
        else:
            stop_price = entry_price * (1 - loss_percent)

        logger.info(
            f"Stop-loss set for {symbol}: Entry ${entry_price:.2f}, Stop ${stop_price:.2f}"
        )

        return stop_price

    def check_position_stop_loss(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        side: str = 'buy'
    ) -> Tuple[bool, str]:
        """
        Check if position stop-loss is triggered

        Args:
            symbol: Trading pair
            entry_price: Entry price
            current_price: Current price
            side: 'buy' or 'sell'

        Returns:
            (stop_triggered, reason)
        """
        stop_price = self.set_stop_loss(symbol, entry_price, side)

        if side == 'buy':
            if current_price <= stop_price:
                return True, f"Stop-loss triggered for {symbol}: {current_price:.2f} <= {stop_price:.2f}"
        else:
            if current_price >= stop_price:
                return True, f"Stop-loss triggered for {symbol}: {current_price:.2f} >= {stop_price:.2f}"

        return False, "Position safe"

    def monitor_position_risk(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_size_usd: float,
        side: str = 'buy'
    ) -> Dict:
        """
        Monitor position risk metrics

        Args:
            symbol: Trading pair
            entry_price: Entry price
            current_price: Current price
            position_size_usd: Position size
            side: 'buy' or 'sell'

        Returns:
            Risk metrics dictionary
        """
        if side == 'buy':
            pnl = (current_price - entry_price) * (position_size_usd / entry_price)
        else:
            pnl = (entry_price - current_price) * (position_size_usd / entry_price)

        pnl_percent = (pnl / position_size_usd) * 100

        stop_price = self.set_stop_loss(symbol, entry_price, side)
        stop_triggered, stop_msg = self.check_position_stop_loss(
            symbol, entry_price, current_price, side
        )

        metrics = {
            'symbol': symbol,
            'entry_price': entry_price,
            'current_price': current_price,
            'side': side,
            'position_size_usd': position_size_usd,
            'unrealized_pnl': pnl,
            'unrealized_pnl_percent': pnl_percent,
            'stop_loss_price': stop_price,
            'stop_loss_triggered': stop_triggered,
            'distance_to_stop': abs(current_price - stop_price),
            'distance_to_stop_percent': (abs(current_price - stop_price) / entry_price) * 100
        }

        self.positions_at_risk[symbol] = metrics

        return metrics

    def get_portfolio_risk_summary(self) -> Dict:
        """Get overall portfolio risk summary"""
        current_loss_percent = ((self.current_capital - self.initial_capital) / self.initial_capital) * 100
        daily_loss_percent = (self.daily_loss / self.initial_capital) * 100

        risk_level = self.assess_risk_level()
        daily_limit_exceeded, daily_msg = self.check_daily_loss_limit()
        emergency_triggered, emergency_msg = self.check_emergency_stop()

        return {
            'timestamp': datetime.now().isoformat(),
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'total_loss': self.current_capital - self.initial_capital,
            'total_loss_percent': current_loss_percent,
            'daily_loss': self.daily_loss,
            'daily_loss_percent': daily_loss_percent,
            'daily_trades': self.daily_trades,
            'risk_level': risk_level.value,
            'daily_limit_exceeded': daily_limit_exceeded,
            'emergency_stop_triggered': emergency_triggered,
            'positions_at_risk_count': len(self.positions_at_risk),
            'positions_at_risk': self.positions_at_risk
        }

    def get_risk_alerts(self) -> List[Dict]:
        """Get all active risk alerts"""
        alerts = []

        # Check daily loss limit
        daily_limit_exceeded, daily_msg = self.check_daily_loss_limit()
        if daily_limit_exceeded:
            alerts.append({
                'severity': 'warning',
                'type': 'daily_loss_limit',
                'message': daily_msg,
                'timestamp': datetime.now().isoformat()
            })

        # Check emergency stop
        emergency_triggered, emergency_msg = self.check_emergency_stop()
        if emergency_triggered:
            alerts.append({
                'severity': 'critical',
                'type': 'emergency_stop',
                'message': emergency_msg,
                'timestamp': datetime.now().isoformat()
            })

        # Check risk level
        risk_level = self.assess_risk_level()
        if risk_level in [RiskLevel.WARNING, RiskLevel.CRITICAL]:
            alerts.append({
                'severity': 'warning' if risk_level == RiskLevel.WARNING else 'critical',
                'type': 'risk_level',
                'message': f"Risk level: {risk_level.value}",
                'timestamp': datetime.now().isoformat()
            })

        # Check positions at risk
        for symbol, metrics in self.positions_at_risk.items():
            if metrics['stop_loss_triggered']:
                alerts.append({
                    'severity': 'critical',
                    'type': 'position_stop_loss',
                    'symbol': symbol,
                    'message': f"Stop-loss triggered for {symbol}",
                    'timestamp': datetime.now().isoformat()
                })

        self.risk_events = alerts
        return alerts

    def reduce_position_size(
        self,
        current_position_usd: float,
        reduction_percent: float = 0.50
    ) -> float:
        """
        Calculate reduced position size

        Args:
            current_position_usd: Current position size
            reduction_percent: Reduction percentage (0-1)

        Returns:
            New position size
        """
        new_size = current_position_usd * (1 - reduction_percent)
        logger.warning(
            f"Position reduced: ${current_position_usd:,.2f} -> ${new_size:,.2f}"
        )
        return new_size

    def get_leverage_limit(self) -> float:
        """
        Get maximum leverage allowed based on risk profile

        Returns:
            Maximum leverage multiplier
        """
        risk_level = self.assess_risk_level()

        if risk_level == RiskLevel.SAFE:
            return 3.0
        elif risk_level == RiskLevel.CAUTION:
            return 2.0
        elif risk_level == RiskLevel.WARNING:
            return 1.0
        else:  # CRITICAL
            return 0.0

    def validate_entry(
        self,
        symbol: str,
        position_size_usd: float,
        side: str = 'buy'
    ) -> Tuple[bool, str]:
        """
        Validate if new entry is allowed

        Args:
            symbol: Trading pair
            position_size_usd: Proposed position size
            side: 'buy' or 'sell'

        Returns:
            (allowed, reason)
        """
        # Check emergency stop
        emergency_triggered, emergency_msg = self.check_emergency_stop()
        if emergency_triggered:
            return False, emergency_msg

        # Check daily loss limit
        daily_limit_exceeded, daily_msg = self.check_daily_loss_limit()
        if daily_limit_exceeded:
            return False, f"Daily loss limit exceeded: {daily_msg}"

        # Check position size
        valid_size, size_msg = self.validate_position_size(symbol, position_size_usd)
        if not valid_size:
            return False, size_msg

        return True, "Entry allowed"

    def log_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        position_size_usd: float
    ) -> None:
        """Log trade execution"""
        self.daily_trades += 1
        logger.info(
            f"Trade logged: {symbol} {side.upper()} ${position_size_usd:,.2f} @ ${entry_price:.2f}"
        )
