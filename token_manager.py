"""Token Manager System - RTK proxy support and token quota management."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class QuotaStatus(Enum):
    """Enum for quota status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"


@dataclass
class TokenQuota:
    """Per-model token quota tracking."""
    model: str
    daily_limit: float
    monthly_limit: float
    daily_used: int = 0
    monthly_used: int = 0
    last_reset: datetime = field(default_factory=datetime.now)

    def get_daily_remaining(self) -> float:
        if self.daily_limit == float('inf'):
            return float('inf')
        return max(0, self.daily_limit - self.daily_used)

    def get_monthly_remaining(self) -> float:
        if self.monthly_limit == float('inf'):
            return float('inf')
        return max(0, self.monthly_limit - self.monthly_used)

    def get_daily_usage_percent(self) -> float:
        if self.daily_limit == float('inf') or self.daily_limit == 0:
            return 0.0
        return (self.daily_used / self.daily_limit) * 100

    def get_status(self):
        daily_percent = self.get_daily_usage_percent()
        if daily_percent >= 100:
            return QuotaStatus.EXCEEDED
        elif daily_percent >= 80:
            return QuotaStatus.CRITICAL
        elif daily_percent >= 60:
            return QuotaStatus.WARNING
        else:
            return QuotaStatus.HEALTHY


class TokenManager:
    def __init__(self, config):
        self.rtk_enabled = config.get("rtk_enabled", True)
        self.quota_monitoring = config.get("quota_monitoring", True)
        self.token_savings_target = config.get("token_savings_target", 0.9)
        self.usage_tracking = config.get("usage_tracking", True)
        self.quotas = {}
        self._initialize_quotas(config)
        logger.info(f"TokenManager initialized with {len(self.quotas)} models")

    def _initialize_quotas(self, config):
        models_config = config.get("models", {})
        for model_name, limits in models_config.items():
            quota = TokenQuota(
                model=model_name,
                daily_limit=limits.get("daily_limit", float('inf')),
                monthly_limit=limits.get("monthly_limit", float('inf')),
                last_reset=datetime.now()
            )
            self.quotas[model_name] = quota
            logger.debug(f"Initialized quota for {model_name}")

    def add_usage(self, model, tokens):
        if model not in self.quotas:
            logger.warning(f"Model {model} not found in quotas")
            return
        self.quotas[model].daily_used += tokens
        self.quotas[model].monthly_used += tokens
        if self.usage_tracking:
            logger.debug(f"Added {tokens} tokens to {model}")

    def reset_daily_quota_if_needed(self, model):
        if model not in self.quotas:
            logger.warning(f"Model {model} not found in quotas")
            return
        quota = self.quotas[model]
        now = datetime.now()
        time_since_reset = now - quota.last_reset
        if time_since_reset >= timedelta(days=1):
            quota.monthly_used += quota.daily_used
            quota.daily_used = 0
            quota.last_reset = now
            logger.info(f"Reset daily quota for {model}")

    def get_daily_usage_percent(self, model):
        if model not in self.quotas:
            logger.warning(f"Model {model} not found in quotas")
            return 0.0
        return self.quotas[model].get_daily_usage_percent()

    def get_status(self, model):
        if model not in self.quotas:
            logger.warning(f"Model {model} not found in quotas")
            return QuotaStatus.HEALTHY
        return self.quotas[model].get_status()

    def can_use_model(self, model, estimated_tokens):
        if model not in self.quotas:
            logger.warning(f"Model {model} not found in quotas")
            return False
        quota = self.quotas[model]
        return (quota.get_daily_remaining() >= estimated_tokens and
                quota.get_monthly_remaining() >= estimated_tokens)


class ModelSelector:
    def __init__(self, token_manager):
        self.token_manager = token_manager
        logger.info("ModelSelector initialized")

    def select_for_task(self, task_type, task_tokens_estimate):
        logger.info(f"Selecting model for {task_type} task ({task_tokens_estimate} tokens)")
        models = list(self.token_manager.quotas.keys())
        available_models = [
            m for m in models
            if self.token_manager.can_use_model(m, task_tokens_estimate)
        ]
        if not available_models:
            for model in models:
                if self.token_manager.quotas[model].daily_limit == float('inf'):
                    logger.warning(f"Using fallback model {model}")
                    return model
            return models[0] if models else "qwen3:8b"
        if task_type == "high_priority":
            selected = max(
                available_models,
                key=lambda m: self.token_manager.quotas[m].get_daily_remaining()
            )
        elif task_type == "medium_priority":
            selected = available_models[0]
        elif task_type == "low_priority":
            selected = min(
                available_models,
                key=lambda m: self.token_manager.quotas[m].daily_limit
            )
        elif task_type == "emergency":
            for model in models:
                if self.token_manager.quotas[model].daily_limit == float('inf'):
                    return model
            selected = available_models[0]
        else:
            selected = max(
                available_models,
                key=lambda m: self.token_manager.quotas[m].get_daily_remaining()
            )
        logger.info(f"Selected model: {selected}")
        return selected


class RTKProxyClient:
    def __init__(self, config):
        self.config = config
        self.cache = {}
        logger.info("RTKProxyClient initialized")

    def estimate_token_savings(self, original_tokens):
        savings_ratio = self.config.get("savings_ratio", 0.75)
        saved = int(original_tokens * savings_ratio)
        logger.debug(f"Estimated {saved} tokens saved from {original_tokens}")
        return saved

    def get_cached_response(self, cache_key):
        return self.cache.get(cache_key)

    def set_cached_response(self, cache_key, response):
        self.cache[cache_key] = response
        logger.debug(f"Cached response for key: {cache_key}")
