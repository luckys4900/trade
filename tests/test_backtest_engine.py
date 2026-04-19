import pytest
import numpy as np
import pandas as pd
from stat_arbitrage.backtest_engine import BacktestEngine, BacktestResult


@pytest.fixture
def sample_pair_data():
    """Generate synthetic cointegrated price series"""
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=500, freq='D')

    # Create mean-reverting spread
    base_price1 = 100
    base_price2 = 50
    spread = np.cumsum(np.random.normal(-0.01, 0.5, 500))
    spread = spread - np.mean(spread)

    price1 = base_price1 + np.cumsum(np.random.normal(0, 0.3, 500)) + spread * 0.3
    price2 = base_price2 + np.cumsum(np.random.normal(0, 0.3, 500)) - spread * 0.6

    df1 = pd.DataFrame({'close': price1}, index=dates)
    df2 = pd.DataFrame({'close': price2}, index=dates)

    return df1, df2


def test_backtest_engine_initialization():
    """Test BacktestEngine initializes with parameters"""
    engine = BacktestEngine(
        z_score_threshold=2.0,
        position_size=0.02,
        entry_threshold=2.0,
        exit_threshold=0.5
    )
    assert engine.z_score_threshold == 2.0
    assert engine.position_size == 0.02
    assert engine.entry_threshold == 2.0
    assert engine.exit_threshold == 0.5


def test_backtest_run_basic(sample_pair_data):
    """Test backtest runs and returns results"""
    df1, df2 = sample_pair_data
    engine = BacktestEngine(z_score_threshold=2.0, position_size=0.02)

    result = engine.run(df1, df2, pair_name='BTC/ETH', initial_capital=100000)

    assert isinstance(result, BacktestResult)
    assert result.pair_name == 'BTC/ETH'
    assert result.initial_capital == 100000
    assert result.total_trades >= 0
    assert 0 <= result.win_rate <= 1.0


def test_backtest_walk_forward(sample_pair_data):
    """Test walk-forward backtesting"""
    df1, df2 = sample_pair_data
    engine = BacktestEngine(z_score_threshold=2.0)

    result = engine.walk_forward(
        df1, df2,
        pair_name='ETH/LTC',
        train_window=200,
        test_window=100,
        step=50
    )

    assert isinstance(result, BacktestResult)
    assert result.pair_name == 'ETH/LTC'
    assert len(result.trades) >= 0


def test_backtest_result_sharpe_ratio(sample_pair_data):
    """Test Sharpe ratio calculation in results"""
    df1, df2 = sample_pair_data
    engine = BacktestEngine()

    result = engine.run(df1, df2, pair_name='TEST/PAIR', initial_capital=50000)

    assert isinstance(result.sharpe_ratio, float)
    assert np.isfinite(result.sharpe_ratio)


def test_backtest_result_max_drawdown(sample_pair_data):
    """Test max drawdown calculation"""
    df1, df2 = sample_pair_data
    engine = BacktestEngine()

    result = engine.run(df1, df2, pair_name='TEST/PAIR', initial_capital=100000)

    assert isinstance(result.max_drawdown, float)
    assert result.max_drawdown <= 0  # Drawdown is non-positive


def test_backtest_result_pnl(sample_pair_data):
    """Test PnL and return calculation"""
    df1, df2 = sample_pair_data
    engine = BacktestEngine()

    result = engine.run(df1, df2, pair_name='TEST/PAIR', initial_capital=100000)

    assert isinstance(result.total_pnl, float)
    assert isinstance(result.total_return_pct, float)
    assert result.final_capital == result.initial_capital + result.total_pnl
