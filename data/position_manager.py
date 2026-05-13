"""
Position Manager - Clarity Act v3.0
Manages open positions, entry/exit updates, and position history
Author: Claude Code
Date: 2026-05-14
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PositionStatus(Enum):
    """Position status enumeration"""
    OPEN = "open"
    CLOSED = "closed"
    PAUSED = "paused"


class Position:
    """Represents a single trading position"""

    def __init__(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        position_size_usd: float,
        entry_time: datetime = None,
        trailing_stop_percent: float = 0.75
    ):
        """
        Initialize position

        Args:
            symbol: Trading pair (e.g., 'BTC/USDC')
            side: 'buy' or 'sell'
            entry_price: Entry price
            quantity: Position quantity
            position_size_usd: Position size in USD
            entry_time: Entry timestamp
            trailing_stop_percent: Trailing stop percentage
        """
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.entry_quantity = quantity
        self.current_quantity = quantity
        self.position_size_usd = position_size_usd
        self.entry_time = entry_time or datetime.now()
        self.trailing_stop_percent = trailing_stop_percent

        self.exit_price = None
        self.exit_time = None
        self.exit_reason = None
        self.status = PositionStatus.OPEN

        self.current_price = entry_price
        self.highest_price = entry_price  # For short
        self.lowest_price = entry_price   # For long
        self.peak_profit = 0
        self.peak_loss = 0

        self.price_history = [{
            'timestamp': self.entry_time,
            'price': entry_price,
            'pnl': 0,
            'pnl_percent': 0
        }]

    def update_price(self, current_price: float) -> None:
        """Update current position price"""
        self.current_price = current_price

        if self.side == 'buy':
            self.highest_price = max(self.highest_price, current_price)
            self.lowest_price = min(self.lowest_price, current_price)
        else:
            self.highest_price = max(self.highest_price, current_price)
            self.lowest_price = min(self.lowest_price, current_price)

        # Update P&L
        self._calculate_pnl()

        # Record price history
        self.price_history.append({
            'timestamp': datetime.now(),
            'price': current_price,
            'pnl': self.get_unrealized_pnl(),
            'pnl_percent': self.get_unrealized_pnl_percent()
        })

    def _calculate_pnl(self) -> None:
        """Calculate current P&L"""
        if self.side == 'buy':
            pnl = (self.current_price - self.entry_price) * self.current_quantity
        else:
            pnl = (self.entry_price - self.current_price) * self.current_quantity

        # Update peak profit/loss
        if pnl > 0:
            self.peak_profit = max(self.peak_profit, pnl)
        else:
            self.peak_loss = min(self.peak_loss, pnl)

    def get_unrealized_pnl(self) -> float:
        """Get unrealized P&L in USD"""
        if self.side == 'buy':
            return (self.current_price - self.entry_price) * self.current_quantity
        else:
            return (self.entry_price - self.current_price) * self.current_quantity

    def get_unrealized_pnl_percent(self) -> float:
        """Get unrealized P&L percentage"""
        pnl = self.get_unrealized_pnl()
        if self.position_size_usd == 0:
            return 0
        return (pnl / self.position_size_usd) * 100

    def get_entry_duration_hours(self) -> float:
        """Get position duration in hours"""
        duration = datetime.now() - self.entry_time
        return duration.total_seconds() / 3600

    def get_trailing_stop_price(self) -> float:
        """Calculate trailing stop price"""
        if self.side == 'buy':
            return self.highest_price * (1 - self.trailing_stop_percent / 100)
        else:
            return self.lowest_price * (1 + self.trailing_stop_percent / 100)

    def is_trailing_stop_triggered(self) -> bool:
        """Check if trailing stop is triggered"""
        stop_price = self.get_trailing_stop_price()

        if self.side == 'buy':
            return self.current_price <= stop_price
        else:
            return self.current_price >= stop_price

    def close(self, exit_price: float, exit_reason: str = None) -> Tuple[float, float]:
        """
        Close position

        Args:
            exit_price: Exit price
            exit_reason: Reason for exit

        Returns:
            (realized_pnl, realized_pnl_percent)
        """
        self.exit_price = exit_price
        self.exit_time = datetime.now()
        self.exit_reason = exit_reason or "Manual close"
        self.status = PositionStatus.CLOSED

        # Calculate realized P&L
        if self.side == 'buy':
            realized_pnl = (exit_price - self.entry_price) * self.current_quantity
        else:
            realized_pnl = (self.entry_price - exit_price) * self.current_quantity

        realized_pnl_percent = (realized_pnl / self.position_size_usd) * 100

        logger.info(
            f"Position closed: {self.symbol} {self.side} "
            f"P&L: ${realized_pnl:,.2f} ({realized_pnl_percent:.2f}%)"
        )

        return realized_pnl, realized_pnl_percent

    def to_dict(self) -> Dict:
        """Convert position to dictionary"""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'status': self.status.value,
            'entry_price': self.entry_price,
            'entry_quantity': self.entry_quantity,
            'current_quantity': self.current_quantity,
            'position_size_usd': self.position_size_usd,
            'entry_time': self.entry_time.isoformat(),
            'current_price': self.current_price,
            'unrealized_pnl': self.get_unrealized_pnl(),
            'unrealized_pnl_percent': self.get_unrealized_pnl_percent(),
            'duration_hours': self.get_entry_duration_hours(),
            'exit_price': self.exit_price,
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'exit_reason': self.exit_reason,
            'peak_profit': self.peak_profit,
            'peak_loss': self.peak_loss,
            'trailing_stop_percent': self.trailing_stop_percent,
            'trailing_stop_price': self.get_trailing_stop_price()
        }


class PositionManager:
    """
    Manages all open positions and position history
    """

    def __init__(self):
        """Initialize position manager"""
        self.open_positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.position_history: List[Dict] = []

    def open_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        position_size_usd: float,
        trailing_stop_percent: float = 0.75
    ) -> Position:
        """
        Open new position

        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            entry_price: Entry price
            quantity: Position quantity
            position_size_usd: Position size in USD
            trailing_stop_percent: Trailing stop percentage

        Returns:
            New Position object
        """
        if symbol in self.open_positions:
            logger.warning(f"Position already exists for {symbol}, closing old position first")
            self.close_position(symbol, entry_price, "Replaced by new position")

        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            position_size_usd=position_size_usd,
            trailing_stop_percent=trailing_stop_percent
        )

        self.open_positions[symbol] = position
        logger.info(
            f"Position opened: {symbol} {side.upper()} "
            f"Qty: {quantity:.4f} @ ${entry_price:.2f}"
        )

        return position

    def update_position_price(self, symbol: str, current_price: float) -> Optional[Position]:
        """
        Update position with new price

        Args:
            symbol: Trading pair
            current_price: Current market price

        Returns:
            Updated Position or None
        """
        if symbol not in self.open_positions:
            logger.warning(f"No open position for {symbol}")
            return None

        position = self.open_positions[symbol]
        position.update_price(current_price)

        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str = None
    ) -> Optional[Tuple[float, float]]:
        """
        Close open position

        Args:
            symbol: Trading pair
            exit_price: Exit price
            exit_reason: Reason for exit

        Returns:
            (realized_pnl, realized_pnl_percent) or None
        """
        if symbol not in self.open_positions:
            logger.warning(f"No open position for {symbol}")
            return None

        position = self.open_positions.pop(symbol)
        realized_pnl, realized_pnl_percent = position.close(exit_price, exit_reason)

        # Record in history
        self.closed_positions.append(position)
        self.position_history.append({
            'symbol': symbol,
            'side': position.side,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'quantity': position.entry_quantity,
            'position_size_usd': position.position_size_usd,
            'entry_time': position.entry_time.isoformat(),
            'exit_time': position.exit_time.isoformat(),
            'duration_hours': position.get_entry_duration_hours(),
            'realized_pnl': realized_pnl,
            'realized_pnl_percent': realized_pnl_percent,
            'exit_reason': exit_reason,
            'peak_profit': position.peak_profit,
            'peak_loss': position.peak_loss
        })

        return realized_pnl, realized_pnl_percent

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get open position by symbol"""
        return self.open_positions.get(symbol)

    def get_all_open_positions(self) -> Dict[str, Position]:
        """Get all open positions"""
        return self.open_positions.copy()

    def get_position_count(self) -> int:
        """Get count of open positions"""
        return len(self.open_positions)

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized P&L across all positions"""
        return sum(pos.get_unrealized_pnl() for pos in self.open_positions.values())

    def get_total_unrealized_pnl_percent(self) -> float:
        """Get total unrealized P&L percentage"""
        total_size = sum(pos.position_size_usd for pos in self.open_positions.values())
        if total_size == 0:
            return 0
        return (self.get_total_unrealized_pnl() / total_size) * 100

    def get_position_exposure(self) -> Dict[str, float]:
        """Get position exposure by symbol"""
        return {
            symbol: pos.position_size_usd
            for symbol, pos in self.open_positions.items()
        }

    def get_total_exposure(self) -> float:
        """Get total position exposure in USD"""
        return sum(pos.position_size_usd for pos in self.open_positions.values())

    def check_trailing_stops(self) -> List[str]:
        """
        Check all positions for trailing stop triggers

        Returns:
            List of symbols where trailing stop was triggered
        """
        triggered = []

        for symbol, position in list(self.open_positions.items()):
            if position.is_trailing_stop_triggered():
                triggered.append(symbol)
                logger.info(
                    f"Trailing stop triggered for {symbol}: "
                    f"Price {position.current_price:.2f} "
                    f"<= Stop {position.get_trailing_stop_price():.2f}"
                )

        return triggered

    def get_position_status_report(self) -> Dict:
        """Get comprehensive position status report"""
        open_symbols = list(self.open_positions.keys())
        positions_data = [
            self.open_positions[symbol].to_dict()
            for symbol in open_symbols
        ]

        return {
            'timestamp': datetime.now().isoformat(),
            'open_positions_count': len(self.open_positions),
            'open_symbols': open_symbols,
            'total_exposure_usd': self.get_total_exposure(),
            'total_unrealized_pnl': self.get_total_unrealized_pnl(),
            'total_unrealized_pnl_percent': self.get_total_unrealized_pnl_percent(),
            'positions': positions_data
        }

    def get_closed_position_stats(self) -> Dict:
        """Get statistics on closed positions"""
        if not self.closed_positions:
            return {
                'total_closed': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_realized_pnl': 0,
                'average_pnl_percent': 0,
                'best_trade': None,
                'worst_trade': None
            }

        pnls = [pos.get_unrealized_pnl() for pos in self.closed_positions
                if pos.status == PositionStatus.CLOSED]

        if not pnls:
            return {
                'total_closed': len(self.closed_positions),
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_realized_pnl': 0,
                'average_pnl_percent': 0
            }

        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]

        return {
            'total_closed': len(self.closed_positions),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': len(winning) / len(pnls) if pnls else 0,
            'total_realized_pnl': sum(pnls),
            'average_pnl_percent': sum(p.get_unrealized_pnl_percent()
                                      for p in self.closed_positions) / len(self.closed_positions),
            'best_trade': max(pnls) if pnls else None,
            'worst_trade': min(pnls) if pnls else None
        }

    def get_position_history(self, limit: int = None) -> List[Dict]:
        """
        Get position history

        Args:
            limit: Limit number of records

        Returns:
            Position history records
        """
        if limit:
            return self.position_history[-limit:]
        return self.position_history.copy()

    def save_position_state(self, filepath: str) -> None:
        """Save position state to JSON"""
        try:
            state = {
                'timestamp': datetime.now().isoformat(),
                'open_positions': [
                    pos.to_dict() for pos in self.open_positions.values()
                ],
                'position_history': self.position_history,
                'stats': self.get_closed_position_stats()
            }

            with open(filepath, 'w') as f:
                json.dump(state, f, indent=2, default=str)

            logger.info(f"Position state saved to {filepath}")

        except Exception as e:
            logger.error(f"Failed to save position state: {e}")

    def load_position_state(self, filepath: str) -> None:
        """Load position state from JSON"""
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)

            self.position_history = state.get('position_history', [])
            logger.info(f"Position state loaded from {filepath}")

        except Exception as e:
            logger.error(f"Failed to load position state: {e}")
