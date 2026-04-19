import pytest
import pandas as pd
import numpy as np
from stat_arbitrage.cointegration_analyzer import CointegrationAnalyzer


@pytest.fixture
def analyzer():
    return CointegrationAnalyzer()


@pytest.fixture
def sample_data():
    """Create synthetic cointegrated price series"""
    np.random.seed(42)
    t = np.arange(100)
    z1 = np.random.normal(0, 1, 100).cumsum()
    z2 = z1 + np.random.normal(0, 0.5, 100)

    df1 = pd.DataFrame({'timestamp': t, 'close': 100 + z1}, index=t)
    df2 = pd.DataFrame({'timestamp': t, 'close': 100 + z2}, index=t)

    return df1, df2


def test_johansen_test(analyzer, sample_data):
    """Test Johansen cointegration test"""
    df1, df2 = sample_data

    result = analyzer.johansen_test(df1['close'], df2['close'])

    assert 'eigenvalue' in result
    assert 'trace_stat' in result
    assert 'p_value' in result


def test_adf_test(analyzer, sample_data):
    """Test ADF stationarity test"""
    df1, df2 = sample_data
    spread = df1['close'] - df2['close']

    result = analyzer.adf_test(spread)

    assert 'adf_stat' in result
    assert 'p_value' in result


def test_hurst_exponent(analyzer, sample_data):
    """Test Hurst exponent calculation"""
    df1, df2 = sample_data

    hurst = analyzer.hurst_exponent(df1['close'].values)

    assert 0 < hurst < 1
    assert hurst < 0.6


def test_analyze_pair(analyzer, sample_data):
    """Test comprehensive pair analysis"""
    df1, df2 = sample_data

    result = analyzer.analyze_pair(df1, df2)

    assert 'johansen_p_value' in result
    assert 'adf_p_value' in result
    assert 'hurst' in result
    assert 'is_cointegrated' in result
    assert 'is_stationary' in result
    assert 'is_mean_reverting' in result
