import pytest
import numpy as np
from stat_arbitrage.pair_selector import PairSelector


@pytest.fixture
def sample_analysis_results():
    """Generate realistic cointegration analysis results"""
    return {
        'BTC/USDT_ETH/USDT': {
            'johansen_p_value': 0.02,
            'adf_p_value': 0.01,
            'hurst_exponent': 0.35,
            'is_cointegrated': True,
            'pair': ('BTC/USDT', 'ETH/USDT'),
            'correlation': 0.85
        },
        'BTC/USDT_XRP/USDT': {
            'johansen_p_value': 0.08,
            'adf_p_value': 0.05,
            'hurst_exponent': 0.45,
            'is_cointegrated': False,
            'pair': ('BTC/USDT', 'XRP/USDT'),
            'correlation': 0.52
        },
        'ETH/USDT_LTC/USDT': {
            'johansen_p_value': 0.03,
            'adf_p_value': 0.02,
            'hurst_exponent': 0.42,
            'is_cointegrated': True,
            'pair': ('ETH/USDT', 'LTC/USDT'),
            'correlation': 0.78
        },
        'ADA/USDT_DOT/USDT': {
            'johansen_p_value': 0.01,
            'adf_p_value': 0.005,
            'hurst_exponent': 0.38,
            'is_cointegrated': True,
            'pair': ('ADA/USDT', 'DOT/USDT'),
            'correlation': 0.71
        },
        'XRP/USDT_DOGE/USDT': {
            'johansen_p_value': 0.12,
            'adf_p_value': 0.1,
            'hurst_exponent': 0.55,
            'is_cointegrated': False,
            'pair': ('XRP/USDT', 'DOGE/USDT'),
            'correlation': 0.43
        }
    }


def test_pair_selector_initialization():
    """Test PairSelector initializes with correct parameters"""
    selector = PairSelector(min_p_value=0.05, max_hurst=0.5, exclude_patterns=['BTC/USD'])
    assert selector.min_p_value == 0.05
    assert selector.max_hurst == 0.5
    assert selector.exclude_patterns == ['BTC/USD']


def test_filter_pairs_valid_input(sample_analysis_results):
    """Test filter_pairs returns only statistically significant pairs"""
    selector = PairSelector(min_p_value=0.05, max_hurst=0.5)
    filtered = selector.filter_pairs(sample_analysis_results)

    assert len(filtered) > 0
    for pair in filtered:
        assert pair['johansen_p_value'] < selector.min_p_value
        assert pair['hurst_exponent'] < selector.max_hurst


def test_filter_pairs_excludes_invalid(sample_analysis_results):
    """Test filter_pairs excludes patterns"""
    selector = PairSelector(
        min_p_value=0.05,
        max_hurst=0.5,
        exclude_patterns=['BTC/USDT', 'XRP/USDT']
    )
    filtered = selector.filter_pairs(sample_analysis_results)

    for pair in filtered:
        symbol1, symbol2 = pair['pair']
        for pattern in selector.exclude_patterns:
            assert pattern != symbol1
            assert pattern != symbol2


def test_score_pair_calculation(sample_analysis_results):
    """Test pair scoring formula"""
    selector = PairSelector()

    pair = sample_analysis_results['BTC/USDT_ETH/USDT']
    score = selector.score_pair(pair)

    assert isinstance(score, float)
    assert 0 <= score <= 100


def test_get_top_pairs_sorting(sample_analysis_results):
    """Test get_top_pairs returns N highest-scoring pairs"""
    selector = PairSelector(min_p_value=0.1, max_hurst=0.6)
    top_pairs = selector.get_top_pairs(sample_analysis_results, n=2)

    assert len(top_pairs) <= 2
    if len(top_pairs) > 1:
        assert top_pairs[0]['score'] >= top_pairs[1]['score']
