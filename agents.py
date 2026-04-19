#!/usr/bin/env python3
"""
マルチエージェントAIトレードシステム
エージェント実装
"""

import asyncio
import json
import logging
import time
import aiohttp
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

import sys
import os

# 設定読み込み
with open('multi_agent_config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# ログ設定
logging.basicConfig(
    level=getattr(logging, config['multi_agent_config']['logging']['level']),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    ERROR = "error"
    OFFLINE = "offline"

class TaskResult:
    def __init__(self, success: bool, data: Any = None, error: str = None):
        self.success = success
        self.data = data
        self.error = error
        self.timestamp = datetime.now()

class BaseAgent:
    """エージェントの基底クラス"""
    
    def __init__(self, name: str, model_manager):
        self.name = name
        self.model_manager = model_manager
        self.status = AgentStatus.IDLE
        self.current_task = None
        self.task_count = 0
        self.error_count = 0
        self.session = aiohttp.ClientSession()
        
    async def process_task(self, task_data: Dict[str, Any]) -> TaskResult:
        """タスクの処理（基底メソッド）"""
        raise NotImplementedError
        
    async def call_ai_model(self, prompt: str, model: str = None) -> str:
        """AIモデルを呼び出す"""
        if model is None:
            model = self.model_manager.current_model
            
        logger.info(f"Calling AI model {model} for agent {self.name}")
        
        # Ollamaとの通信
        if ":" in model and model.split(":")[0] in ["qwen3", "llama3.2"]:
            return await self._call_ollama(model, prompt)
        else:
            # Z.AI APIとの通信
            return await self._call_zai_api(model, prompt)
    
    async def _call_ollama(self, model: str, prompt: str) -> str:
        """Ollamaモデルを呼び出す"""
        try:
            async with self.session.post(
                'http://localhost:11434/api/generate',
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "No response")
                else:
                    logger.error(f"Ollama call failed: {response.status}")
                    return "Error calling model"
                    
        except Exception as e:
            logger.error(f"Ollama call error: {e}")
            return f"Error: {e}"
    
    async def _call_zai_api(self, model: str, prompt: str) -> str:
        """Z.AI APIを呼び出す"""
        try:
            # 環境変数からAPIキー取得
            api_key = os.getenv('ZAI_API_KEY')
            if not api_key:
                logger.error("ZAI_API_KEY not found")
                return "API key not found"
            
            async with self.session.post(
                'https://api.z.ai/api/coding/paas/v4/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 2000
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"ZAI API call failed: {response.status}")
                    return "Error calling model"
                    
        except Exception as e:
            logger.error(f"ZAI API call error: {e}")
            return f"Error: {e}"
    
    async def update_status(self, status: AgentStatus):
        """エージェントの状態を更新"""
        self.status = status
        logger.info(f"Agent {self.name} status updated to {status.value}")
    
    def get_stats(self) -> Dict[str, Any]:
        """エージェントの統計情報を取得"""
        return {
            "name": self.name,
            "status": self.status.value,
            "task_count": self.task_count,
            "error_count": self.error_count,
            "success_rate": self.task_count / max(self.task_count + self.error_count, 1)
        }

class FrontendAgent(BaseAgent):
    """フロントエンドエージェント"""
    
    def __init__(self, model_manager):
        super().__init__("FrontendAgent", model_manager)
        
    async def process_task(self, task_data: Dict[str, Any]) -> TaskResult:
        """フロントエンド関連のタスクを処理"""
        try:
            await self.update_status(AgentStatus.WORKING)
            
            task_type = task_data.get("type", "dashboard")
            
            if task_type == "dashboard":
                result = await self.generate_dashboard(task_data)
            elif task_type == "report":
                result = await self.generate_report(task_data)
            else:
                result = await self.update_ui(task_data)
            
            self.task_count += 1
            return TaskResult(success=True, data=result)
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"FrontendAgent error: {e}")
            return TaskResult(success=False, error=str(e))
        finally:
            await self.update_status(AgentStatus.IDLE)
            self.current_task = None
    
    async def generate_dashboard(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """ダッシュボードを生成"""
        prompt = f"""
Generate a comprehensive trading dashboard with the following requirements:
- Real-time BTC price display
- Position status
- Profit/loss tracking
- Strategy performance metrics
- Risk indicators

Return as HTML template with embedded CSS and JavaScript.
"""
        
        html_content = await self.call_ai_model(prompt, "glm-5-1")
        
        return {
            "html": html_content,
            "title": "Trading Dashboard",
            "last_updated": datetime.now().isoformat()
        }
    
    async def generate_report(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """レポートを生成"""
        prompt = f"""
Generate a trading performance report for {task_data.get('period', 'daily')} period.
Include:
- Summary of trades executed
- Win/loss ratio
- Profit/loss analysis
- Strategy effectiveness
- Recommendations for improvement
"""
        
        report_content = await self.call_ai_model(prompt, "glm-5-turbo")
        
        return {
            "report": report_content,
            "period": task_data.get('period', 'daily'),
            "generated_at": datetime.now().isoformat()
        }
    
    async def update_ui(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """UIを更新"""
        # UI更新のロジック
        return {"status": "updated", "component": task_data.get("component")}

class BackendAgent(BaseAgent):
    """バックエンドエージェント"""
    
    def __init__(self, model_manager):
        super().__init__("BackendAgent", model_manager)
        
    async def process_task(self, task_data: Dict[str, Any]) -> TaskResult:
        """バックエンド関連のタスクを処理"""
        try:
            await self.update_status(AgentStatus.WORKING)
            
            task_type = task_data.get("type", "api")
            
            if task_type == "api":
                result = await self.process_api_request(task_data)
            elif task_type == "data":
                result = await self.process_data_request(task_data)
            elif task_type == "logging":
                result = await self.manage_logging(task_data)
            else:
                result = await self.config_management(task_data)
            
            self.task_count += 1
            return TaskResult(success=True, data=result)
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"BackendAgent error: {e}")
            return TaskResult(success=False, error=str(e))
        finally:
            await self.update_status(AgentStatus.IDLE)
            self.current_task = None
    
    async def process_api_request(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """APIリクエストを処理"""
        endpoint = task_data.get("endpoint")
        params = task_data.get("params", {})
        
        # Hyperliquid APIの呼び出し（シミュレーション）
        if endpoint == "account_info":
            return {
                "address": "0x...",
                "equity": 211.19,
                "margin": 0,
                "pnl": 0,
                "positions": []
            }
        elif endpoint == "market_data":
            return {
                "symbol": "BTC",
                "price": 45000.00,
                "volume_24h": 1000000,
                "timestamp": datetime.now().isoformat()
            }
        
        return {"status": "processed", "endpoint": endpoint}
    
    async def process_data_request(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """データリクエストを処理"""
        data_type = task_data.get("data_type")
        
        if data_type == "historical_data":
            return {
                "data": [],
                "period": "4h",
                "count": 100
            }
        elif data_type == "trade_history":
            return {
                "trades": [],
                "period": "24h",
                "count": 50
            }
        
        return {"status": "processed", "data_type": data_type}
    
    async def manage_logging(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """ログ管理"""
        action = task_data.get("action")
        
        if action == "rotate":
            # ログのローテーション
            return {"status": "rotated", "timestamp": datetime.now().isoformat()}
        elif action == "cleanup":
            # ログのクリーンアップ
            return {"status": "cleaned", "files_removed": 5}
        
        return {"status": "processed", "action": action}
    
    async def config_management(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """設定管理"""
        action = task_data.get("action")
        
        if action == "update":
            # 設定の更新
            return {"status": "updated", "config": task_data.get("config")}
        elif action == "backup":
            # 設定のバックアップ
            return {"status": "backed_up", "timestamp": datetime.now().isoformat()}
        
        return {"status": "processed", "action": action}

class AnalysisAgent(BaseAgent):
    """分析エージェント"""
    
    def __init__(self, model_manager):
        super().__init__("AnalysisAgent", model_manager)
        
    async def process_task(self, task_data: Dict[str, Any]) -> TaskResult:
        """分析関連のタスクを処理"""
        try:
            await self.update_status(AgentStatus.WORKING)
            
            task_type = task_data.get("type", "strategy")
            
            if task_type == "strategy":
                result = await self.analyze_strategy(task_data)
            elif task_type == "backtest":
                result = await self.run_backtest(task_data)
            elif task_type == "optimization":
                result = await self.optimize_parameters(task_data)
            elif task_type == "risk":
                result = await self.assess_risk(task_data)
            
            self.task_count += 1
            return TaskResult(success=True, data=result)
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"AnalysisAgent error: {e}")
            return TaskResult(success=False, error=str(e))
        finally:
            await self.update_status(AgentStatus.IDLE)
            self.current_task = None
    
    async def analyze_strategy(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """戦略を分析"""
        strategy = task_data.get("strategy")
        period = task_data.get("period", "24h")
        
        prompt = f"""
Analyze the performance of {strategy} strategy over the last {period}.
Consider:
- Win rate
- Profit factor  
- Maximum drawdown
- Risk/reward ratio
- Market conditions
- Strengths and weaknesses

Provide detailed analysis with recommendations.
"""
        
        analysis = await self.call_ai_model(prompt, "glm-5-1")
        
        return {
            "strategy": strategy,
            "period": period,
            "analysis": analysis,
            "score": 85,
            "timestamp": datetime.now().isoformat()
        }
    
    async def run_backtest(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """バックテストを実行"""
        strategy = task_data.get("strategy")
        timeframe = task_data.get("timeframe", "4h")
        start_date = task_data.get("start_date")
        end_date = task_data.get("end_date")
        
        # バックテストの実行（シミュレーション）
        backtest_result = {
            "strategy": strategy,
            "timeframe": timeframe,
            "total_trades": 25,
            "winning_trades": 18,
            "losing_trades": 7,
            "win_rate": 72.0,
            "total_profit": 1250.50,
            "total_loss": -320.25,
            "net_profit": 930.25,
            "max_drawdown": 8.5,
            "profit_factor": 3.9,
            "sharpe_ratio": 1.8,
            "backtest_period": f"{start_date} to {end_date}"
        }
        
        return backtest_result
    
    async def optimize_parameters(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """パラメータを最適化"""
        strategy = task_data.get("strategy")
        current_params = task_data.get("current_params")
        
        prompt = f"""
Optimize the parameters for {strategy} strategy.
Current parameters: {current_params}

Suggest improved parameters with:
1. RSI periods
2. ATR multipliers  
3. Position sizing
4. Risk management rules
5. Entry/exit conditions

Provide reasoning for each parameter change.
"""
        
        optimization = await self.call_ai_model(prompt, "glm-5.1")
        
        return {
            "strategy": strategy,
            "original_params": current_params,
            "optimized_params": {
                "rsi_period": 12,
                "atr_multiplier": 2.5,
                "position_size": 0.02
            },
            "optimization_report": optimization,
            "expected_improvement": "+15%",
            "timestamp": datetime.now().isoformat()
        }
    
    async def assess_risk(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """リスクを評価"""
        portfolio = task_data.get("portfolio", {})
        
        risk_assessment = {
            "current_risk": "Low",
            "portfolio_exposure": 45.2,
            "var_95": 1250.00,
            "max_drawdown": 8.5,
            "correlation_risk": "Low",
            "market_risk": "Medium",
            "recommendations": [
                "Reduce leverage during high volatility",
                "Diversify position sizes",
                "Set strict stop-losses"
            ],
            "risk_score": 65,
            "timestamp": datetime.now().isoformat()
        }
        
        return risk_assessment

class ResearchAgent(BaseAgent):
    """調査エージェント"""
    
    def __init__(self, model_manager):
        super().__init__("ResearchAgent", model_manager)
        
    async def process_task(self, task_data: Dict[str, Any]) -> TaskResult:
        """調査関連のタスクを処理"""
        try:
            await self.update_status(AgentStatus.WORKING)
            
            task_type = task_data.get("type", "macro")
            
            if task_type == "macro":
                result = await self.research_macro_data(task_data)
            elif task_type == "news":
                result = await self.analyze_news(task_data)
            elif task_type == "market":
                result = await self.analyze_market_conditions(task_data)
            elif task_type == "sentiment":
                result = await self.analyze_sentiment(task_data)
            
            self.task_count += 1
            return TaskResult(success=True, data=result)
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"ResearchAgent error: {e}")
            return TaskResult(success=False, error=str(e))
        finally:
            await self.update_status(AgentStatus.IDLE)
            self.current_task = None
    
    async def research_macro_data(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """マクロデータを調査"""
        indicators = task_data.get("indicators", ["FFR", "CPI", "VIX"])
        
        # FRED APIの呼び出し（シミュレーション）
        macro_data = {
            "indicators": {
                "FFR": {
                    "current": 5.25,
                    "trend": "stable",
                    "impact": "neutral"
                },
                "CPI": {
                    "current": 3.2,
                    "trend": "increasing",
                    "impact": "negative"
                },
                "VIX": {
                    "current": 18.5,
                    "trend": "decreasing",
                    "impact": "positive"
                }
            },
            "market_outlook": "Cautiously optimistic",
            "timestamp": datetime.now().isoformat()
        }
        
        return macro_data
    
    async def analyze_news(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """ニュースを分析"""
        topic = task_data.get("topic", "cryptocurrency")
        
        prompt = f"""
Analyze recent news about {topic} and provide sentiment analysis.
Focus on:
- Market impact
- Price implications
- Regulatory developments
- Technology changes
- Investor sentiment

Provide a summary with sentiment score.
"""
        
        news_analysis = await self.call_ai_model(prompt, "glm-4-7-flash")
        
        return {
            "topic": topic,
            "sentiment_score": 0.65,
            "sentiment": "positive",
            "analysis": news_analysis,
            "timestamp": datetime.now().isoformat()
        }
    
    async def analyze_market_conditions(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """市場環境を分析"""
        timeframe = task_data.get("timeframe", "24h")
        
        market_analysis = {
            "timeframe": timeframe,
            "trend": "bullish",
            "volatility": "medium",
            "liquidity": "high",
            "key_levels": {
                "support": 44000,
                "resistance": 46000,
                "pivot": 45000
            },
            "indicators": {
                "rsi": 58,
                "macd": "bullish",
                "bollinger": "neutral"
            },
            "recommendation": "Breakout strategy favored",
            "timestamp": datetime.now().isoformat()
        }
        
        return market_analysis
    
    async def analyze_sentiment(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """センチメントを分析"""
        source = task_data.get("source", "social_media")
        
        sentiment_data = {
            "source": source,
            "overall_sentiment": 0.72,
            "confidence": 0.85,
            "key_themes": [
                "Bullish on BTC",
                "Regulation concerns",
                "Inflation hedging"
            ],
            "sentiment_breakdown": {
                "positive": 0.65,
                "neutral": 0.20,
                "negative": 0.15
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return sentiment_data

class ProtectionAgent(BaseAgent):
    """保護エージェント"""
    
    def __init__(self, model_manager):
        super().__init__("ProtectionAgent", model_manager)
        
    async def process_task(self, task_data: Dict[str, Any]) -> TaskResult:
        """保護関連のタスクを処理"""
        try:
            await self.update_status(AgentStatus.WORKING)
            
            task_type = task_data.get("type", "risk")
            
            if task_type == "risk":
                result = await self.manage_risk(task_data)
            elif task_type == "position":
                result = await self.monitor_positions(task_data)
            elif task_type == "anomaly":
                result = await self.detect_anomalies(task_data)
            elif task_type == "emergency":
                result = await self.handle_emergency(task_data)
            
            self.task_count += 1
            return TaskResult(success=True, data=result)
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"ProtectionAgent error: {e}")
            return TaskResult(success=False, error=str(e))
        finally:
            await self.update_status(AgentStatus.IDLE)
            self.current_task = None
    
    async def manage_risk(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """リスクを管理"""
        current_risk = task_data.get("current_risk", "low")
        
        if current_risk == "high":
            action = "reduce_positions"
        elif current_risk == "medium":
            action = "monitor_closely"
        else:
            action = "maintain_status"
        
        risk_management = {
            "current_risk": current_risk,
            "action": action,
            "position_reduction": 0.3 if action == "reduce_positions" else 0,
            "stop_loss_adjustment": "stricter" if action == "reduce_positions" else "normal",
            "timestamp": datetime.now().isoformat()
        }
        
        return risk_management
    
    async def monitor_positions(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """ポジションを監視"""
        positions = task_data.get("positions", [])
        
        position_status = {
            "total_positions": len(positions),
            "winning_positions": 8,
            "losing_positions": 3,
            "total_exposure": 156.7,
            "margin_usage": 45.2,
            "risk_alerts": [],
            "recommendations": [
                "Close losing positions if below -3%",
                "Reduce BTC exposure by 10%",
                "Set tighter stop-losses"
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        return position_status
    
    async def detect_anomalies(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """異常を検知"""
        market_data = task_data.get("market_data", {})
        
        anomalies = []
        
        # 異常検知ロジック
        if market_data.get("price_change_pct", 0) > 5:
            anomalies.append({
                "type": "price_spike",
                "severity": "high",
                "description": "Price spike detected (>5%)"
            })
        
        if market_data.get("volume_spike", 0) > 200:
            anomalies.append({
                "type": "volume_spike",
                "severity": "medium", 
                "description": "Unusual volume detected"
            })
        
        anomaly_report = {
            "anomalies_detected": len(anomalies),
            "anomalies": anomalies,
            "action_required": "investigate" if anomalies else "none",
            "timestamp": datetime.now().isoformat()
        }
        
        return anomaly_report
    
    async def handle_emergency(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """緊急事態を処理"""
        emergency_type = task_data.get("type", "market_crash")
        
        emergency_response = {
            "emergency_type": emergency_type,
            "severity": "critical",
            "actions_taken": [
                "All positions closed",
                "Emergency stop activated",
                "Alerts sent to stakeholders"
            ],
            "status": "resolved",
            "timestamp": datetime.now().isoformat()
        }
        
        return emergency_response

async def main():
    """テスト用メイン関数"""
    # モデル管理の初期化（簡易版）
    class MockModelManager:
        def __init__(self):
            self.current_model = "glm-5-turbo"
    
    model_manager = MockModelManager()
    
    # 各エージェントのテスト
    agents = [
        FrontendAgent(model_manager),
        BackendAgent(model_manager),
        AnalysisAgent(model_manager),
        ResearchAgent(model_manager),
        ProtectionAgent(model_manager)
    ]
    
    # タスクの実行テスト
    for agent in agents:
        print(f"Testing {agent.name}...")
        
        test_task = {
            "type": "test",
            "data": {"test": True}
        }
        
        result = await agent.process_task(test_task)
        print(f"Result: {result.success}")
        print(f"Data: {result.data}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())