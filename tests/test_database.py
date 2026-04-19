import pytest
import tempfile
import json
import os
from datetime import datetime
from stat_arbitrage.database import TradeDatabase


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test_trades.db')
        db = TradeDatabase(db_path)
        yield db
        db.close()


def test_database_initialization(temp_db):
    """Test database initializes with correct tables"""
    assert temp_db.db_path is not None
    assert os.path.exists(temp_db.db_path)


def test_save_trade(temp_db):
    """Test saving a trade to database"""
    trade_data = {
        'pair': 'BTC/USDT',
        'entry_time': datetime.now().isoformat(),
        'entry_price': 40000.0,
        'quantity': 0.5,
        'side': 'long',
        'pnl': 500.0
    }
    
    trade_id = temp_db.save_trade(trade_data)
    assert trade_id is not None


def test_get_trade(temp_db):
    """Test retrieving a trade"""
    trade_data = {
        'pair': 'ETH/USDT',
        'entry_time': datetime.now().isoformat(),
        'entry_price': 2000.0,
        'quantity': 1.0,
        'side': 'long',
        'pnl': 50.0
    }
    
    trade_id = temp_db.save_trade(trade_data)
    retrieved = temp_db.get_trade(trade_id)
    
    assert retrieved is not None
    assert retrieved['pair'] == 'ETH/USDT'


def test_get_all_trades(temp_db):
    """Test retrieving all trades"""
    trades = [
        {
            'pair': 'BTC/USDT',
            'entry_time': datetime.now().isoformat(),
            'entry_price': 40000.0,
            'quantity': 0.1,
            'side': 'long',
            'pnl': 100.0
        },
        {
            'pair': 'ETH/USDT',
            'entry_time': datetime.now().isoformat(),
            'entry_price': 2000.0,
            'quantity': 0.5,
            'side': 'short',
            'pnl': -50.0
        }
    ]
    
    for trade in trades:
        temp_db.save_trade(trade)
    
    all_trades = temp_db.get_all_trades()
    assert len(all_trades) >= 2


def test_save_parameters(temp_db):
    """Test saving strategy parameters"""
    params = {
        'z_score_threshold': 2.0,
        'position_size': 0.02,
        'entry_threshold': 2.0,
        'exit_threshold': 0.5
    }
    
    temp_db.save_parameters('strategy_v1', params)
    retrieved = temp_db.get_parameters('strategy_v1')
    
    assert retrieved is not None
    assert retrieved['z_score_threshold'] == 2.0


def test_save_session_log(temp_db):
    """Test saving session execution logs"""
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'event': 'SESSION_START',
        'message': 'Starting live trading session',
        'details': {'pairs': ['BTC/USDT', 'ETH/USDT']}
    }
    
    temp_db.save_session_log(log_data)
    
    logs = temp_db.get_session_logs(limit=10)
    assert len(logs) > 0


def test_get_trades_by_pair(temp_db):
    """Test filtering trades by pair"""
    trades = [
        {
            'pair': 'BTC/USDT',
            'entry_time': datetime.now().isoformat(),
            'entry_price': 40000.0,
            'quantity': 0.1,
            'side': 'long',
            'pnl': 100.0
        },
        {
            'pair': 'BTC/USDT',
            'entry_time': datetime.now().isoformat(),
            'entry_price': 41000.0,
            'quantity': 0.05,
            'side': 'short',
            'pnl': 50.0
        },
        {
            'pair': 'ETH/USDT',
            'entry_time': datetime.now().isoformat(),
            'entry_price': 2000.0,
            'quantity': 1.0,
            'side': 'long',
            'pnl': 100.0
        }
    ]
    
    for trade in trades:
        temp_db.save_trade(trade)
    
    btc_trades = temp_db.get_trades_by_pair('BTC/USDT')
    assert len(btc_trades) >= 2


def test_backtest_results_logging(temp_db):
    """Test saving backtest results"""
    results = {
        'pair': 'BTC/ETH',
        'total_trades': 45,
        'win_rate': 0.58,
        'sharpe_ratio': 1.65,
        'max_drawdown': -0.12,
        'total_return_pct': 28.5
    }
    
    temp_db.save_backtest_results('test_backtest', results)
    retrieved = temp_db.get_backtest_results('test_backtest')
    
    assert retrieved is not None
    assert retrieved['win_rate'] == 0.58


def test_database_statistics(temp_db):
    """Test calculating statistics"""
    trades = [
        {'pair': 'BTC/USDT', 'entry_time': datetime.now().isoformat(),
         'entry_price': 40000.0, 'quantity': 0.1, 'side': 'long', 'pnl': 100.0, 'exit_price': 40100.0},
        {'pair': 'BTC/USDT', 'entry_time': datetime.now().isoformat(),
         'entry_price': 41000.0, 'quantity': 0.05, 'side': 'short', 'pnl': -50.0, 'exit_price': 40900.0},
    ]
    
    for trade in trades:
        temp_db.save_trade(trade)
    
    stats = temp_db.get_statistics()
    
    assert stats is not None
    assert 'total_trades' in stats
    assert stats['total_pnl'] == 50.0
