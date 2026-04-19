#!/usr/bin/env python3
"""
マルチエージェントAIトレードシステム
マスター・オーケストレーター
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from enum import Enum
import aiohttp
import zmq
import redis
import numpy as np
from datetime import datetime

# 設定読み込み
with open('multi_agent_config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# ログ設定
logging.basicConfig(
    level=getattr(logging, config['multi_agent_config']['logging']['level']),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/multi_agent_orchestrator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TaskComplexity(Enum):
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"

class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    ERROR = "error"
    OFFLINE = "offline"

@dataclass
class Task:
    id: str
    type: str
    complexity: TaskComplexity
    priority: int
    data: Dict[str, Any]
    timeout: int = 300
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class AgentInfo:
    name: str
    status: AgentStatus
    model: str
    current_task: Optional[str] = None
    last_heartbeat: float = 0
    task_count: int = 0
    error_count: int = 0

class ModelManager:
    """モデル管理とトークン管理"""
    
    def __init__(self):
        self.current_model = config['multi_agent_config']['master_orchestrator']['primary_model']
        self.model_weights = {
            TaskComplexity.HIGH: 1.0,
            TaskComplexity.MEDIUM: 0.6,
            TaskComplexity.LOW: 0.3
        }
        
    def select_model(self, task: Task) -> str:
        """タスクの複雑度に基づいてモデルを選択"""
        if self._check_token_quota(task.complexity):
            # トークンに余裕がある場合はクラウドモデルを使用
            if task.complexity == TaskComplexity.HIGH:
                return "glm-5-1"
            elif task.complexity == TaskComplexity.MEDIUM:
                return "glm-5-turbo"
            else:
                return "glm-4-7-flash"
        else:
            # トークン不足はローカルモデルにフォールバック
            return "qwen3:8b"
    
    def _check_token_quota(self, complexity: TaskComplexity) -> bool:
        """トークン量のチェック（簡易版）"""
        # トークン量が70%以上あれば使用可能
        quota_threshold = 0.7
        return True  # 実装では実際のAPIコールでチェック
    
    def switch_to_fallback(self):
        """フォールバックモデルへの切り替え"""
        self.current_model = "qwen3:8b"
        logger.warning(f"Switched to fallback model: {self.current_model}")

class MasterOrchestrator:
    """マスター・オーケストレーター"""
    
    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[str, Task] = {}
        self.model_manager = ModelManager()
        self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        self.zmq_context = zmq.Context()
        self.setup_agents()
        
    def setup_agents(self):
        """エージェントの初期化"""
        for agent_name, agent_config in config['multi_agent_config']['agents'].items():
            self.agents[agent_name] = AgentInfo(
                name=agent_name,
                status=AgentStatus.IDLE,
                model=agent_config['primary_model']
            )
        logger.info(f"Initialized {len(self.agents)} agents")
    
    async def start(self):
        """オーケストレーターの開始"""
        logger.info("Starting Master Orchestrator")
        
        # 非同期タスクの起動
        tasks = [
            self.task_processor(),
            self.health_monitor(),
            self.performance_optimizer(),
            self.agent_heartbeat()
        ]
        
        await asyncio.gather(*tasks)
    
    async def task_processor(self):
        """タスク処理メインループ"""
        logger.info("Task processor started")
        
        while True:
            try:
                task = await self.task_queue.get()
                await self.process_task(task)
                self.task_queue.task_done()
            except Exception as e:
                logger.error(f"Task processing error: {e}")
                await asyncio.sleep(1)
    
    async def process_task(self, task: Task):
        """タスクの実行"""
        logger.info(f"Processing task {task.id}: {task.type}")
        
        # 適切なエージェントを選択
        selected_agent = self._select_agent_for_task(task)
        if not selected_agent:
            logger.error(f"No suitable agent for task {task.id}")
            return
        
        # モデルを選択
        selected_model = self.model_manager.select_model(task)
        
        # エージェントにタスクを割り当て
        await self.assign_task(selected_agent, task, selected_model)
    
    def _select_agent_for_task(self, task: Task) -> Optional[str]:
        """タスクに適したエージェントを選択"""
        task_agent_mapping = {
            'frontend': ['frontend'],
            'backend': ['backend'],
            'analysis': ['analysis'],
            'research': ['research'],
            'protection': ['protection'],
            'dashboard': ['frontend', 'backend'],
            'monitoring': ['backend', 'protection'],
            'optimization': ['analysis']
        }
        
        suitable_agents = task_agent_mapping.get(task.type, [])
        available_agents = [
            name for name in suitable_agents 
            if self.agents[name].status == AgentStatus.IDLE
        ]
        
        if available_agents:
            return available_agents[0]
        
        return None
    
    async def assign_task(self, agent_name: str, task: Task, model: str):
        """エージェントにタスクを割り当て"""
        agent = self.agents[agent_name]
        agent.status = AgentStatus.WORKING
        agent.current_task = task.id
        agent.task_count += 1
        
        logger.info(f"Assigned task {task.id} to agent {agent_name} using model {model}")
        
        # ここで実際のエージェントへのタスク送信処理を行う
        # 非同期でエージェントプロセスにタスクを送信
        
        try:
            # タスク実行（実際の実装では別プロセスへのRPC）
            await self.simulate_agent_work(agent_name, task, model)
            
            agent.status = AgentStatus.IDLE
            agent.current_task = None
            
        except Exception as e:
            logger.error(f"Agent {agent_name} failed on task {task.id}: {e}")
            agent.status = AgentStatus.ERROR
            agent.error_count += 1
            agent.current_task = None
            
            # リトライロジック
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                self.task_queue.put_nowait(task)
    
    async def simulate_agent_work(self, agent_name: str, task: Task, model: str):
        """エージェントの作業をシミュレート"""
        # 実際の実装では、エージェントプロセスにタスクを送信
        await asyncio.sleep(2)  # タスク実行のシミュレーション
        
        logger.info(f"Agent {agent_name} completed task {task.id}")
    
    async def health_monitor(self):
        """システムのヘルスモニタリング"""
        logger.info("Health monitor started")
        
        while True:
            try:
                # 各エージェントの状態をチェック
                for agent_name, agent in self.agents.items():
                    if time.time() - agent.last_heartbeat > 60:  # 60秒以内のハートビートが必要
                        agent.status = AgentStatus.OFFLINE
                        logger.warning(f"Agent {agent_name} is offline")
                
                # トークン量のチェック
                await self.check_token_usage()
                
                await asyncio.sleep(30)  # 30秒ごとにチェック
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(30)
    
    async def performance_optimizer(self):
        """パフォーマンス最適化"""
        logger.info("Performance optimizer started")
        
        while True:
            try:
                # システムパフォーマンスの分析
                await self.optimize_resource_allocation()
                
                # モデルの切り替え判断
                await self.check_model_performance()
                
                await asyncio.sleep(60)  # 1分ごとに最適化
                
            except Exception as e:
                logger.error(f"Performance optimizer error: {e}")
                await asyncio.sleep(60)
    
    async def agent_heartbeat(self):
        """エージェントのハートビート"""
        logger.info("Agent heartbeat started")
        
        while True:
            try:
                # 各エージェントにハートビートを送信
                for agent_name in self.agents:
                    # 実装ではZMQでハートビートを送信
                    self.agents[agent_name].last_heartbeat = time.time()
                
                await asyncio.sleep(10)  # 10秒ごと
                
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(10)
    
    async def check_token_usage(self):
        """トークン使用量のチェック"""
        # 実装ではAPI使用量を監視
        pass
    
    async def optimize_resource_allocation(self):
        """リソース割り当ての最適化"""
        # エージェントの負荷分散やリソース割り当てを最適化
        pass
    
    async def check_model_performance(self):
        """モデルパフォーマンスのチェック"""
        # モデルの応答時間や精度に基づいて最適なモデルを選択
        pass
    
    def add_task(self, task: Task):
        """タスクの追加"""
        self.task_queue.put_nowait(task)
        logger.info(f"Added task {task.id} to queue")

def create_sample_tasks():
    """サンプルタスクの作成"""
    tasks = [
        Task(
            id="task_001",
            type="analysis",
            complexity=TaskComplexity.HIGH,
            priority=1,
            data={"strategy": "OCPM", "optimization": True}
        ),
        Task(
            id="task_002", 
            type="research",
            complexity=TaskComplexity.MEDIUM,
            priority=2,
            data={"indicator": "FFR", "period": "daily"}
        ),
        Task(
            id="task_003",
            type="frontend", 
            complexity=TaskComplexity.LOW,
            priority=3,
            data={"dashboard": "main", "refresh": True}
        )
    ]
    return tasks

async def main():
    """メイン関数"""
    os.makedirs('logs', exist_ok=True)
    
    orchestrator = MasterOrchestrator()
    
    # サンプルタスクの追加
    sample_tasks = create_sample_tasks()
    for task in sample_tasks:
        orchestrator.add_task(task)
    
    # システムの開始
    await orchestrator.start()

if __name__ == "__main__":
    asyncio.run(main())