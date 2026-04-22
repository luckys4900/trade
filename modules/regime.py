from __future__ import annotations

REGIME_RULES: dict[tuple[str, str], str] = {
    ("RISK_ON", "BULLISH"): "BULL_CONFIRMED",
    ("RISK_ON", "NEUTRAL"): "BULL_DRIFT",
    ("RISK_ON", "BEARISH"): "BULL_FADING",
    ("RISK_OFF", "BULLISH"): "BEAR_FADING",
    ("RISK_OFF", "NEUTRAL"): "BEAR_DRIFT",
    ("RISK_OFF", "BEARISH"): "BEAR_CONFIRMED",
    ("NEUTRAL", "BULLISH"): "ROTATION_UP",
    ("NEUTRAL", "NEUTRAL"): "RANGE",
    ("NEUTRAL", "BEARISH"): "ROTATION_DOWN",
}

ACTION_BIAS: dict[str, dict[str, float]] = {
    "BULL_CONFIRMED": {"long_bias": 0.7, "size_mult": 1.0},
    "BULL_DRIFT": {"long_bias": 0.6, "size_mult": 0.8},
    "BULL_FADING": {"long_bias": 0.5, "size_mult": 0.5},
    "BEAR_FADING": {"long_bias": 0.5, "size_mult": 0.5},
    "BEAR_DRIFT": {"long_bias": 0.4, "size_mult": 0.8},
    "BEAR_CONFIRMED": {"long_bias": 0.3, "size_mult": 1.0},
    "RANGE": {"long_bias": 0.5, "size_mult": 0.6},
    "ROTATION_UP": {"long_bias": 0.55, "size_mult": 0.7},
    "ROTATION_DOWN": {"long_bias": 0.45, "size_mult": 0.7},
}


def determine_regime(macro_sentiment: str, news_bias: str) -> str:
    key = (macro_sentiment.upper(), news_bias.upper())
    return REGIME_RULES.get(key, "RANGE")

