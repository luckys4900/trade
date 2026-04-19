import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from token_manager import TokenManager, TokenQuota, ModelSelector


def test_token_quota_initialization():
    quota = TokenQuota(
        model="glm-5-1",
        daily_limit=100000,
        monthly_limit=1000000
    )
    assert quota.model == "glm-5-1"
    assert quota.daily_limit == 100000
    assert quota.monthly_limit == 1000000
    assert quota.daily_used == 0
    assert quota.monthly_used == 0


def test_token_manager_initialization():
    config = {
        "models": {
            "glm-5-1": {"daily_limit": 100000, "monthly_limit": 1000000},
            "glm-5-turbo": {"daily_limit": 150000, "monthly_limit": 1500000},
            "qwen3:8b": {"daily_limit": float('inf'), "monthly_limit": float('inf')}
        },
        "rtk_enabled": True,
        "quota_monitoring": True,
        "token_savings_target": 0.9
    }
    manager = TokenManager(config)
    assert manager.rtk_enabled == True
    assert len(manager.quotas) == 3


def test_add_token_usage():
    config = {
        "models": {
            "glm-5-1": {"daily_limit": 100000, "monthly_limit": 1000000}
        },
        "rtk_enabled": True,
        "quota_monitoring": True,
        "token_savings_target": 0.9
    }
    manager = TokenManager(config)
    manager.add_usage("glm-5-1", 5000)
    assert manager.quotas["glm-5-1"].daily_used == 5000


def test_token_quota_percentage():
    config = {
        "models": {
            "glm-5-1": {"daily_limit": 100000, "monthly_limit": 1000000}
        },
        "rtk_enabled": True,
        "quota_monitoring": True,
        "token_savings_target": 0.9
    }
    manager = TokenManager(config)
    manager.add_usage("glm-5-1", 80000)
    usage_percent = manager.get_daily_usage_percent("glm-5-1")
    assert usage_percent == 80.0


def test_model_selection_by_quota():
    config = {
        "models": {
            "glm-5-1": {"daily_limit": 1000, "monthly_limit": 10000},
            "glm-5-turbo": {"daily_limit": 2000, "monthly_limit": 20000},
            "qwen3:8b": {"daily_limit": float('inf'), "monthly_limit": float('inf')}
        },
        "rtk_enabled": True,
        "quota_monitoring": True,
        "token_savings_target": 0.9
    }
    manager = TokenManager(config)
    manager.add_usage("glm-5-1", 950)
    selector = ModelSelector(manager)
    selected = selector.select_for_task(
        task_type="high_priority",
        task_tokens_estimate=100
    )
    assert selected in ["glm-5-1", "glm-5-turbo", "qwen3:8b"]


def test_fallback_to_local_model():
    config = {
        "models": {
            "glm-5-1": {"daily_limit": 1000, "monthly_limit": 10000},
            "glm-5-turbo": {"daily_limit": 1000, "monthly_limit": 10000},
            "qwen3:8b": {"daily_limit": float('inf'), "monthly_limit": float('inf')}
        },
        "rtk_enabled": True,
        "quota_monitoring": True,
        "token_savings_target": 0.9
    }
    manager = TokenManager(config)
    manager.add_usage("glm-5-1", 990)
    manager.add_usage("glm-5-turbo", 990)
    selector = ModelSelector(manager)
    selected = selector.select_for_task(
        task_type="high_priority",
        task_tokens_estimate=500
    )
    assert selected == "qwen3:8b"


def test_daily_quota_reset():
    config = {
        "models": {
            "glm-5-1": {"daily_limit": 100000, "monthly_limit": 1000000}
        },
        "rtk_enabled": True,
        "quota_monitoring": True,
        "token_savings_target": 0.9
    }
    manager = TokenManager(config)
    manager.add_usage("glm-5-1", 50000)
    yesterday = datetime.now() - timedelta(days=1)
    manager.quotas["glm-5-1"].last_reset = yesterday
    manager.reset_daily_quota_if_needed("glm-5-1")
    assert manager.quotas["glm-5-1"].daily_used == 0
    assert manager.quotas["glm-5-1"].monthly_used == 50000
