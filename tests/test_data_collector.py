import pytest
from datetime import datetime, timedelta
from stat_arbitrage.data_collector import DataCollector


@pytest.fixture
def collector():
    return DataCollector(exchanges=["binance"])


def test_fetch_ohlcv_basic(collector):
    """Test fetching OHLCV data"""
    symbol = "BTC/USDT"
    timeframe = "1d"
    
    data = collector.fetch_ohlcv(symbol, timeframe, limit=30)
    
    assert len(data) > 0
    assert data[0][0] > 0  # Timestamp
    assert data[0][1] > 0  # Open
    assert data[0][2] > 0  # High
    assert data[0][3] > 0  # Low
    assert data[0][4] > 0  # Close
    assert data[0][5] > 0  # Volume


def test_fetch_multiple_symbols(collector):
    """Test fetching data for multiple symbols"""
    symbols = ["BTC/USDT", "ETH/USDT", "XRP/USDT"]
    timeframe = "1d"
    
    prices = collector.fetch_multiple(symbols, timeframe, limit=10)
    
    assert len(prices) == len(symbols)
    for symbol in symbols:
        assert symbol in prices
        assert len(prices[symbol]) > 0


def test_save_to_csv(collector, tmp_path):
    """Test saving data to CSV"""
    symbol = "BTC/USDT"
    data = collector.fetch_ohlcv(symbol, "1d", limit=10)
    
    csv_file = tmp_path / "test_data.csv"
    collector.save_csv(str(csv_file), data, symbol)
    
    assert csv_file.exists()
