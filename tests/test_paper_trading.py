import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from stat_arbitrage.paper_trading import PaperTradingEngine, PaperTrade


@pytest.fixture
def sample_market_data():
    """Generate sample OHLCV data for testing"""
    dates = pd.date_range('2024-01-01', periods=100, freq='h')
    base_price = 100
    prices = base_price + np.cumsum(np.random.randn(100) * 0.5)
    
    df = pd.DataFrame({
        'open': prices - np.abs(np.random.randn(100) * 0.2),
        'high': prices + np.abs(np.random.randn(100) * 0.2),
        'low': prices - np.abs(np.random.randn(100) * 0.2),
        'close': prices,
        'volume': 1000
    }, index=dates)
    return df


def test_paper_trading_initialization():
    """Test PaperTradingEngine initializes correctly"""
    engine = PaperTradingEngine(
        initial_capital=50000,
        maker_fee=0.001,
        taker_fee=0.002,
        slippage_bps=5
    )
    assert engine.initial_capital == 50000
    assert engine.maker_fee == 0.001
    assert engine.taker_fee == 0.002
    assert engine.cash == 50000


def test_paper_trading_long_entry(sample_market_data):
    """Test opening a long position"""
    engine = PaperTradingEngine(initial_capital=100000)
    
    trade = engine.open_position(
        pair='BTC/USDT',
        side='long',
        entry_price=sample_market_data['close'].iloc[0],
        quantity=1.0,
        timestamp=sample_market_data.index[0]
    )
    
    assert trade is not None
    assert trade.pair == 'BTC/USDT'
    assert trade.side == 'long'
    assert len(engine.open_positions) == 1


def test_paper_trading_close_position(sample_market_data):
    """Test closing a position with profit/loss"""
    engine = PaperTradingEngine(initial_capital=100000)
    
    entry_price = sample_market_data['close'].iloc[0]
    engine.open_position('BTC/USDT', 'long', entry_price, 1.0, 
                        sample_market_data.index[0])
    
    exit_price = entry_price * 1.05  # 5% profit
    closed = engine.close_position(
        pair='BTC/USDT',
        exit_price=exit_price,
        timestamp=sample_market_data.index[10]
    )
    
    assert closed is not None
    assert closed.pnl > 0


def test_paper_trading_fees(sample_market_data):
    """Test fee deduction on trades"""
    engine = PaperTradingEngine(initial_capital=100000, taker_fee=0.001)
    initial_cash = engine.cash
    
    entry_price = sample_market_data['close'].iloc[0]
    engine.open_position('ETH/USDT', 'long', entry_price, 10.0,
                        sample_market_data.index[0])
    
    # Cash should be reduced by trade cost + fees
    assert engine.cash < initial_cash


def test_paper_trading_position_limit(sample_market_data):
    """Test position is limited to available capital"""
    engine = PaperTradingEngine(initial_capital=1000)
    
    entry_price = sample_market_data['close'].iloc[0]
    
    # Try to buy 500 units at ~100 per unit = 50,000 cost, way over 1000 capital
    trade = engine.open_position(
        pair='BTC/USDT',
        side='long',
        entry_price=entry_price,
        quantity=500,
        timestamp=sample_market_data.index[0]
    )
    
    # Position should be created but limited
    if trade:
        assert trade.quantity <= 10  # Max ~10 units with 1000 capital


def test_paper_trading_unrealized_pnl(sample_market_data):
    """Test unrealized P&L calculation"""
    engine = PaperTradingEngine(initial_capital=100000)
    
    entry_price = sample_market_data['close'].iloc[0]
    engine.open_position('BTC/USDT', 'long', entry_price, 1.0,
                        sample_market_data.index[0])
    
    current_price = entry_price * 1.10  # 10% move
    unrealized = engine.get_unrealized_pnl('BTC/USDT', current_price)
    
    assert unrealized > 0


def test_paper_trading_portfolio_value(sample_market_data):
    """Test total portfolio value calculation"""
    engine = PaperTradingEngine(initial_capital=100000)
    
    entry_price = sample_market_data['close'].iloc[0]
    engine.open_position('BTC/USDT', 'long', entry_price, 1.0,
                        sample_market_data.index[0])
    
    current_price = entry_price * 1.05
    portfolio_value = engine.get_portfolio_value('BTC/USDT', current_price)
    
    assert portfolio_value > engine.initial_capital * 0.95


def test_paper_trading_closed_trades_history(sample_market_data):
    """Test closed trades are logged"""
    engine = PaperTradingEngine(initial_capital=100000)
    
    entry_price = sample_market_data['close'].iloc[0]
    engine.open_position('BTC/USDT', 'long', entry_price, 1.0,
                        sample_market_data.index[0])
    
    exit_price = entry_price * 1.02
    engine.close_position('BTC/USDT', exit_price,
                         sample_market_data.index[20])
    
    assert len(engine.closed_trades) == 1
    assert len(engine.open_positions) == 0
