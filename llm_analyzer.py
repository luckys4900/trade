#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Grid Trading Bot - LLM Sentiment Analyzer with Ollama Fallback
Analyzes market sentiment and regime (trend vs range-bound)
"""

import json
import logging
import requests
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """
    LLMを使用したセンチメント分析
    - プライマリモデル（Cloud）がタイムアウト→フォールバック（ローカル）
    - 強いトレンド検出でグリッドをスキップ（リスク管理）
    - 極端なセンチメントで自動的にポジションサイズ縮小
    """

    def __init__(self, config: Dict):
        self.primary_model = config.get('primary_model', 'gpt-oss:120b-cloud')
        self.fallback_model = config.get('fallback_model', 'qwen3:8b')
        self.ollama_url = config.get('ollama_url', 'http://localhost:11434/api/generate')
        self.timeout = config.get('timeout', 30)
        self.use_sentiment = config.get('use_sentiment', True)
        self.strong_trend_threshold = config.get('strong_trend_threshold', 0.7)
        self.extreme_sentiment_threshold = config.get('extreme_sentiment_threshold', 0.8)

        logger.info(
            f"LLMAnalyzer initialized: "
            f"primary={self.primary_model}, "
            f"fallback={self.fallback_model}, "
            f"sentiment_enabled={self.use_sentiment}"
        )

    def _call_ollama(self, model: str, prompt: str) -> Optional[str]:
        """
        Olamaエンドポイントを呼び出してレスポンス生成
        """
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.3  # 低温度で一貫性の高い応答
            }
            resp = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get('response', '').strip()
            else:
                logger.warning(f"Ollama returned {resp.status_code}: {resp.text}")
                return None
        except requests.Timeout:
            logger.warning(f"Ollama {model} timeout after {self.timeout}s")
            return None
        except Exception as e:
            logger.warning(f"Ollama {model} error: {e}")
            return None

    def analyze_sentiment(
        self,
        price: float,
        rsi: float,
        atr: float,
        recent_returns: float,
        market_context: str = ""
    ) -> Dict:
        """
        市場センチメントを分析（Cloud→ローカルのフォールバック付き）

        Args:
            price: 現在価格
            rsi: RSI値
            atr: ATR値
            recent_returns: 直近リターン率（例: 0.05 = 5%）
            market_context: 追加の市場コンテキスト

        Returns:
            {
                'sentiment': 'bullish'|'neutral'|'bearish',
                'confidence': 0.0-1.0,
                'reason': 説明文,
                'model_used': 使用モデル,
            }
        """
        if not self.use_sentiment:
            return {
                'sentiment': 'neutral',
                'confidence': 0.5,
                'reason': 'Sentiment analysis disabled',
                'model_used': 'disabled'
            }

        prompt = f"""
Analyze the following BTC market data and provide a brief sentiment assessment.
Price: ${price:.2f}
RSI (14): {rsi:.1f}
ATR (14): {atr:.2f}
Recent Returns (24h): {recent_returns*100:.2f}%
Market Context: {market_context if market_context else 'No additional context'}

Respond with ONLY a JSON object (no markdown, no extra text):
{{
    "sentiment": "bullish" | "neutral" | "bearish",
    "confidence": 0.0-1.0,
    "reason": "Brief one-line reason"
}}

Focus on: RSI extremes (>70 overbought, <30 oversold), recent momentum, ATR volatility.
"""

        # Try primary model first
        response = self._call_ollama(self.primary_model, prompt)

        # Fallback to local model if primary fails
        if not response:
            logger.info(f"Falling back to {self.fallback_model}")
            response = self._call_ollama(self.fallback_model, prompt)

        # Parse response
        if response:
            try:
                data = json.loads(response)
                return {
                    'sentiment': data.get('sentiment', 'neutral'),
                    'confidence': float(data.get('confidence', 0.5)),
                    'reason': data.get('reason', 'Unknown'),
                    'model_used': self.fallback_model if not response else self.primary_model
                }
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse LLM response: {response}")

        # Fallback to technical analysis if LLM unavailable
        return self._technical_sentiment_fallback(rsi, recent_returns)

    def get_market_regime(
        self,
        price_change_pct: float,
        atr: float,
        recent_volatility: float
    ) -> Tuple[str, float]:
        """
        市場が「トレンド」か「レンジ」かを判定

        Args:
            price_change_pct: 直近の価格変化率（例: 0.03 = 3%）
            atr: ATR値
            recent_volatility: 直近のボラティリティ

        Returns:
            ('trend', confidence) or ('range', confidence)
        """
        if not self.use_sentiment:
            return 'range', 0.5

        prompt = f"""
Determine if BTC is in a TREND or RANGE-BOUND market regime.

Price Change (24h): {price_change_pct*100:.2f}%
ATR: {atr:.2f}
Volatility: {recent_volatility:.4f}

Respond with ONLY:
trend
or
range

with a confidence (0.0-1.0) on the next line."""

        response = self._call_ollama(self.primary_model, prompt)
        if not response:
            response = self._call_ollama(self.fallback_model, prompt)

        if response:
            lines = response.strip().split('\n')
            if len(lines) >= 1:
                regime = lines[0].strip().lower()
                try:
                    confidence = float(lines[1]) if len(lines) > 1 else 0.6
                    if regime in ['trend', 'range']:
                        return regime, min(max(confidence, 0.0), 1.0)
                except (ValueError, IndexError):
                    pass

        # Technical fallback
        if abs(price_change_pct) > 0.05:  # >5% move = likely trending
            return 'trend', 0.7
        return 'range', 0.6

    def should_skip_trade(
        self,
        rsi: float,
        market_regime: str,
        recent_returns: float
    ) -> Tuple[bool, str]:
        """
        強いトレンド時またはリスク高時にトレードをスキップすべきか判定

        Args:
            rsi: RSI値
            market_regime: 市場レジーム ('trend' or 'range')
            recent_returns: 直近リターン率

        Returns:
            (should_skip, reason)
        """
        if not self.use_sentiment:
            return False, "Sentiment analysis disabled"

        # 極端なRSI = 強いトレンド → スキップ
        if rsi > 85 or rsi < 15:
            return True, f"Extreme RSI ({rsi:.1f}) - strong trend detected"

        # トレンド市場でのグリッド取引はリスク高 → スキップ
        if market_regime == 'trend' and abs(recent_returns) > 0.05:
            return True, f"Strong {recent_returns:+.2%} move in trend regime - grid inefficient"

        return False, "No skip conditions met"

    def _technical_sentiment_fallback(self, rsi: float, recent_returns: float) -> Dict:
        """
        LLM利用不可時の技術指標ベースフォールバック
        """
        if rsi > 70:
            sentiment = 'bearish' if recent_returns > 0.03 else 'neutral'
            confidence = 0.8 if recent_returns > 0.05 else 0.6
        elif rsi < 30:
            sentiment = 'bullish' if recent_returns < -0.03 else 'neutral'
            confidence = 0.8 if recent_returns < -0.05 else 0.6
        else:
            sentiment = 'neutral'
            confidence = 0.5

        return {
            'sentiment': sentiment,
            'confidence': confidence,
            'reason': f'Technical fallback: RSI={rsi:.1f}, returns={recent_returns:+.2%}',
            'model_used': 'technical_fallback'
        }


def test_llm_analyzer():
    """簡単なテスト"""
    from config import LLM_CONFIG

    analyzer = LLMAnalyzer(LLM_CONFIG)

    # テスト1: sentiment analysis
    result = analyzer.analyze_sentiment(
        price=45000,
        rsi=65,
        atr=500,
        recent_returns=0.02,
        market_context="Bitcoin above 200-day MA, volume increasing"
    )
    print(f"Sentiment Analysis: {result}")

    # テスト2: market regime
    regime, conf = analyzer.get_market_regime(
        price_change_pct=0.03,
        atr=500,
        recent_volatility=0.015
    )
    print(f"Market Regime: {regime} (confidence={conf:.2f})")

    # テスト3: skip logic
    skip, reason = analyzer.should_skip_trade(
        rsi=80,
        market_regime='trend',
        recent_returns=0.08
    )
    print(f"Skip Trade: {skip} ({reason})")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    test_llm_analyzer()
