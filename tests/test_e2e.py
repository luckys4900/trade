import pytest
from btc_whale_system import MasterAgent

def test_full_daily_cycle():
    agent = MasterAgent()
    result = agent.run_daily_cycle()
    assert result['status'] in ['success', 'error']
    assert 'timestamp' in result

def test_module_imports():
    from btc_whale_system import WhaleDatabase, WhaleAnalyzer, WhaleBacktester
    assert WhaleDatabase is not None
    assert WhaleAnalyzer is not None
    assert WhaleBacktester is not None
