from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order execution status"""
    PENDING = 'PENDING'
    OPEN = 'OPEN'
    FILLED = 'FILLED'
    CANCELLED = 'CANCELLED'
    FAILED = 'FAILED'


@dataclass
class OrderRecord:
    """Record of a placed order"""
    order_id: str
    pair: str
    side: str
    order_type: str
    price: float
    quantity: float
    status: str = OrderStatus.PENDING.value
    filled_quantity: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            'order_id': self.order_id,
            'pair': self.pair,
            'side': self.side,
            'order_type': self.order_type,
            'price': self.price,
            'quantity': self.quantity,
            'status': self.status,
            'filled_quantity': self.filled_quantity,
            'timestamp': self.timestamp
        }


class LiveTradingClient:
    """Live trading client for Binance Futures"""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True,
                 max_position_size: float = 0.05, assumed_capital: float = 100000):
        """
        Initialize live trading client.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet (True) or mainnet (False)
            max_position_size: Max position as fraction of capital
            assumed_capital: Assumed trading capital
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.max_position_size = max_position_size
        self.assumed_capital = assumed_capital

        self.open_orders: Dict[str, Dict] = {}
        self.positions: Dict[str, Dict] = {}
        self.order_history: List[Dict] = []

    def _create_order(self, pair: str, side: str, order_type: str,
                     price: float, quantity: float, 
                     time_in_force: str = 'GTC') -> Dict:
        """Create order object"""
        order_id = str(uuid.uuid4())[:8]
        
        order = {
            'order_id': order_id,
            'pair': pair,
            'side': side,
            'order_type': order_type,
            'price': price,
            'quantity': quantity,
            'time_in_force': time_in_force,
            'status': OrderStatus.PENDING.value,
            'timestamp': datetime.now()
        }
        
        return order

    def _check_trading_safety(self, pair: str, side: str, 
                             quantity: float, price: float) -> bool:
        """Verify trade is safe before execution"""
        notional = quantity * price
        max_notional = self.assumed_capital * self.max_position_size
        
        if notional > max_notional:
            logger.warning(f"Position {notional} exceeds max {max_notional}")
            return False
        
        # Check for duplicate position
        if pair in self.positions and side == 'BUY':
            logger.warning(f"Already have position in {pair}")
            return False
        
        return True

    def _update_position(self, position: Dict) -> None:
        """Update position tracking"""
        pair = position['pair']
        self.positions[pair] = position

    def _update_order_status(self, order_id: str, status: str) -> None:
        """Update order status"""
        if order_id in self.open_orders:
            self.open_orders[order_id]['status'] = status

    def place_order(self, pair: str, side: str, order_type: str,
                   price: float, quantity: float,
                   time_in_force: str = 'GTC') -> Optional[str]:
        """
        Place a new order.
        
        Args:
            pair: Trading pair (e.g. 'BTC/USDT')
            side: 'BUY' or 'SELL'
            order_type: 'LIMIT' or 'MARKET'
            price: Limit price
            quantity: Order quantity
            time_in_force: 'GTC' (Good-Till-Cancel), 'IOC', 'FOK'
            
        Returns:
            Order ID if successful, None otherwise
        """
        if not self._check_trading_safety(pair, side, quantity, price):
            return None
        
        order = self._create_order(pair, side, order_type, price, quantity,
                                   time_in_force)
        order_id = order['order_id']
        
        self.open_orders[order_id] = order
        logger.info(f"Order placed: {order_id} {side} {quantity} {pair} @ {price}")
        
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            True if cancelled, False if not found
        """
        if order_id not in self.open_orders:
            return False
        
        order = self.open_orders[order_id]
        order['status'] = OrderStatus.CANCELLED.value
        
        self.order_history.append(order)
        del self.open_orders[order_id]
        
        logger.info(f"Order cancelled: {order_id}")
        return True

    def get_order_status(self, order_id: str) -> Optional[str]:
        """Get status of an order"""
        if order_id not in self.open_orders:
            return None
        return self.open_orders[order_id]['status']

    def get_position(self, pair: str) -> Optional[Dict]:
        """Get current position details"""
        return self.positions.get(pair)

    def close_position(self, pair: str, close_price: float) -> bool:
        """
        Close an open position.
        
        Args:
            pair: Trading pair
            close_price: Price to close at
            
        Returns:
            True if closed successfully
        """
        if pair not in self.positions:
            return False
        
        position = self.positions[pair]
        side = 'SELL' if position['quantity'] > 0 else 'BUY'
        
        order_id = self.place_order(
            pair=pair,
            side=side,
            order_type='MARKET',
            price=close_price,
            quantity=abs(position['quantity'])
        )
        
        if order_id:
            del self.positions[pair]
            return True
        return False

    def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
        return list(self.open_orders.values())

    def get_positions(self) -> Dict[str, Dict]:
        """Get all open positions"""
        return self.positions.copy()

    def get_account_info(self) -> Dict:
        """Get account information"""
        total_position_value = sum(
            p['quantity'] * p['entry_price'] 
            for p in self.positions.values()
        )
        
        return {
            'api_key': self.api_key[:10] + '...',
            'testnet': self.testnet,
            'assumed_capital': self.assumed_capital,
            'open_orders_count': len(self.open_orders),
            'open_positions_count': len(self.positions),
            'total_position_value': total_position_value,
            'available_capital': self.assumed_capital - total_position_value
        }
