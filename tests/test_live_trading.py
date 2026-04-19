import pytest
from datetime import datetime
from stat_arbitrage.live_trading import LiveTradingClient, OrderStatus


def test_live_trading_client_init():
    """Test LiveTradingClient initialization"""
    client = LiveTradingClient(
        api_key='test_key',
        api_secret='test_secret',
        testnet=True,
        max_position_size=0.05
    )
    assert client.api_key == 'test_key'
    assert client.api_secret == 'test_secret'
    assert client.testnet == True
    assert client.max_position_size == 0.05
    assert len(client.open_orders) == 0


def test_order_status_enum():
    """Test OrderStatus enum"""
    assert OrderStatus.PENDING.value == 'PENDING'
    assert OrderStatus.OPEN.value == 'OPEN'
    assert OrderStatus.FILLED.value == 'FILLED'
    assert OrderStatus.CANCELLED.value == 'CANCELLED'
    assert OrderStatus.FAILED.value == 'FAILED'


def test_live_trading_order_creation():
    """Test creating order object"""
    client = LiveTradingClient('key', 'secret', testnet=True)
    
    order = client._create_order(
        pair='BTC/USDT',
        side='BUY',
        order_type='LIMIT',
        price=40000.0,
        quantity=0.1,
        time_in_force='GTC'
    )
    
    assert order['pair'] == 'BTC/USDT'
    assert order['side'] == 'BUY'
    assert order['price'] == 40000.0
    assert order['quantity'] == 0.1
    assert order['status'] == OrderStatus.PENDING.value


def test_live_trading_risk_limits():
    """Test safety checks reject oversized positions"""
    client = LiveTradingClient('key', 'secret', testnet=True, 
                              max_position_size=0.02)
    
    # Requested 10 BTC at $40k each = $400k, exceeds 2% of 100k capital
    order_id = client.place_order(
        pair='BTC/USDT',
        side='BUY',
        order_type='LIMIT',
        price=40000.0,
        quantity=10,
        time_in_force='GTC'
    )
    
    # Order should be rejected
    assert order_id is None


def test_live_trading_order_placement():
    """Test order placement flow"""
    client = LiveTradingClient('key', 'secret', testnet=True)
    
    order_id = client.place_order(
        pair='ETH/USDT',
        side='BUY',
        order_type='LIMIT',
        price=2000.0,
        quantity=1.0
    )
    
    assert order_id is not None
    assert order_id in client.open_orders


def test_live_trading_order_cancellation():
    """Test order cancellation"""
    client = LiveTradingClient('key', 'secret', testnet=True)
    
    order_id = client.place_order(
        pair='ETH/USDT',
        side='BUY',
        order_type='LIMIT',
        price=2000.0,
        quantity=1.0
    )
    
    result = client.cancel_order(order_id)
    assert result == True
    assert order_id not in client.open_orders


def test_live_trading_position_tracking():
    """Test open positions are tracked"""
    client = LiveTradingClient('key', 'secret', testnet=True)
    
    # Simulate position update
    position = {
        'pair': 'BTC/USDT',
        'quantity': 0.5,
        'entry_price': 40000.0,
        'unrealized_pnl': 500.0
    }
    
    client._update_position(position)
    
    assert 'BTC/USDT' in client.positions
    assert client.positions['BTC/USDT']['quantity'] == 0.5


def test_live_trading_safety_checks():
    """Test safety checks before order execution"""
    client = LiveTradingClient('key', 'secret', testnet=True)
    
    # Max position size exceeded
    can_trade = client._check_trading_safety(
        pair='BTC/USDT',
        side='BUY',
        quantity=100,
        price=40000.0
    )
    
    assert can_trade == False


def test_live_trading_order_status_tracking():
    """Test order status updates"""
    client = LiveTradingClient('key', 'secret', testnet=True)
    
    order_id = client.place_order(
        pair='ETH/USDT',
        side='BUY',
        order_type='LIMIT',
        price=2000.0,
        quantity=1.0
    )
    
    # Update status to filled
    client._update_order_status(order_id, OrderStatus.FILLED.value)
    
    assert client.open_orders[order_id]['status'] == OrderStatus.FILLED.value


def test_live_trading_get_account_info():
    """Test account info retrieval"""
    client = LiveTradingClient('key', 'secret', testnet=True)
    
    info = client.get_account_info()
    
    assert 'api_key' in info
    assert info['testnet'] == True
    assert info['assumed_capital'] == 100000
    assert info['open_orders_count'] == 0
