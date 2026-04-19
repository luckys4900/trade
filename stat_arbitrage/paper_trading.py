from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass
class PaperTrade:
    """Record of a paper trading transaction"""
    pair: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    quantity: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0


class PaperTradingEngine:
    """Simulate live trading without real capital"""

    def __init__(self, initial_capital=100000, maker_fee=0.001,
                 taker_fee=0.002, slippage_bps=5, max_leverage=1.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_bps = slippage_bps
        self.max_leverage = max_leverage

        self.open_positions: Dict[str, PaperTrade] = {}
        self.closed_trades: List[PaperTrade] = []

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to price"""
        slippage_multiplier = self.slippage_bps / 10000
        if side == 'long':
            return price * (1 + slippage_multiplier)
        else:
            return price * (1 - slippage_multiplier)

    def _calculate_fees(self, notional: float, is_maker: bool = False) -> float:
        """Calculate trading fees"""
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        return notional * fee_rate

    def open_position(self, pair: str, side: str, entry_price: float,
                     quantity: float, timestamp: pd.Timestamp) -> Optional[PaperTrade]:
        """Open a new position"""
        if pair in self.open_positions:
            return None  # Position already open

        slipped_price = self._apply_slippage(entry_price, side)
        notional = slipped_price * quantity
        fees = self._calculate_fees(notional)
        total_cost = notional + fees

        if total_cost > self.cash:
            # Limit position to available capital
            max_quantity = (self.cash * 0.95) / (slipped_price * (1 + self.taker_fee))
            if max_quantity <= 0:
                return None
            quantity = max_quantity

        self.cash -= total_cost

        trade = PaperTrade(
            pair=pair,
            side=side,
            entry_time=timestamp,
            entry_price=slipped_price,
            quantity=quantity,
            fees=fees
        )

        self.open_positions[pair] = trade
        return trade

    def close_position(self, pair: str, exit_price: float,
                     timestamp: pd.Timestamp) -> Optional[PaperTrade]:
        """Close an open position"""
        if pair not in self.open_positions:
            return None

        trade = self.open_positions[pair]
        slipped_price = self._apply_slippage(exit_price, 'close')

        gross_proceeds = slipped_price * trade.quantity
        exit_fees = self._calculate_fees(gross_proceeds)
        net_proceeds = gross_proceeds - exit_fees

        if trade.side == 'long':
            pnl = net_proceeds - (trade.entry_price * trade.quantity + trade.fees)
        else:
            pnl = (trade.entry_price * trade.quantity) - net_proceeds - trade.fees

        pnl_pct = pnl / (trade.entry_price * trade.quantity)

        trade.exit_time = timestamp
        trade.exit_price = slipped_price
        trade.pnl = pnl
        trade.pnl_pct = pnl_pct
        trade.fees += exit_fees

        self.cash += net_proceeds
        self.closed_trades.append(trade)
        del self.open_positions[pair]

        return trade

    def get_unrealized_pnl(self, pair: str, current_price: float) -> float:
        """Calculate unrealized P&L for open position"""
        if pair not in self.open_positions:
            return 0.0

        trade = self.open_positions[pair]

        if trade.side == 'long':
            return (current_price - trade.entry_price) * trade.quantity
        else:
            return (trade.entry_price - current_price) * trade.quantity

    def get_portfolio_value(self, pair: str, current_price: float) -> float:
        """Get total portfolio value"""
        total = self.cash

        for p, trade in self.open_positions.items():
            if p == pair:
                unrealized = self.get_unrealized_pnl(p, current_price)
            else:
                unrealized = 0
            total += (trade.quantity * trade.entry_price) + unrealized

        return total

    def get_performance_metrics(self) -> Dict:
        """Calculate overall performance metrics"""
        if len(self.closed_trades) == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'total_fees': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
            }

        winning = [t for t in self.closed_trades if t.pnl > 0]
        losing = [t for t in self.closed_trades if t.pnl <= 0]

        total_pnl = sum(t.pnl for t in self.closed_trades)
        total_fees = sum(t.fees for t in self.closed_trades)

        return {
            'total_trades': len(self.closed_trades),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': len(winning) / len(self.closed_trades),
            'total_pnl': total_pnl,
            'total_fees': total_fees,
            'avg_win': sum(t.pnl for t in winning) / len(winning) if winning else 0,
            'avg_loss': sum(t.pnl for t in losing) / len(losing) if losing else 0,
        }
