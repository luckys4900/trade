# マルチエージェントシステム操作マニュアル

## 基本的な指示方法

### 1. マスター・オーケストレーターへの基本指示

マスター・オーケストレーターに伝えるべき基本指示：

```python
# システムの基本設定
basic_instruction = {
    "system_objective": "BTC/Hyperliquid自動売取引システムの運用",
    "risk_management": "月予算$0、トークン使用量60-90%削減を目指す",
    "priorities": [
        "リスク管理を最優先",
        "戦略のパフォーマンス向上", 
        "運用効率化",
        "コスト最適化"
    ],
    "constraints": [
        "ポジションサイズは最大40%まで",
        "連敵5回で取引停止",
        "ドローダウン15%でシステム停止",
        "リスクレベルは'low'を維持"
    ],
    "available_models": {
        "high_precision": "glm-5-1",
        "balanced": "glm-5-turbo", 
        "fast": "glm-4-7-flash",
        "fallback": "qwen3:8b"
    }
}
```

### 2. エージェントへの具体的な指示方法

#### フロントエンドエージェント
```python
frontend_task = {
    "type": "dashboard_update",
    "priority": 1,
    "data": {
        "components": ["real_time_price", "position_status", "pnl_chart"],
        "refresh_interval": 5,
        "style": "modern",
        "responsive": True
    },
    "model": "glm-5-1"  # 高精度が必要
}
```

#### バックエンドエージェント
```python
backend_task = {
    "type": "api_operation",
    "priority": 2,
    "data": {
        "endpoint": "hyperliquid_account",
        "operation": "sync",
        "data_type": "market_data"
    },
    "model": "glm-5-turbo"  # バランス型
}
```

#### 分析エージェント
```python
analysis_task = {
    "type": "strategy_optimization",
    "priority": 1,
    "data": {
        "strategies": ["OCPM", "Range_MR", "RSI_Swing"],
        "optimization_target": "sharpe_ratio",
        "backtest_period": "30d",
        "risk_constraints": {"max_drawdown": 0.1}
    },
    "model": "glm-5-1"  # 高精度が必要
}
```

#### 調査エージェント
```python
research_task = {
    "type": "market_research",
    "priority": 3,
    "data": {
        "indicators": ["FFR", "CPI", "VIX", "Oil_Price"],
        "sentiment_analysis": True,
        "news_sources": ["crypto_news", "economic_reports"],
        "update_frequency": "1h"
    },
    "model": "glm-4-7-flash"  # 高速処理
}
```

#### 保護エージェント
```python
protection_task = {
    "type": "risk_management",
    "priority": 1,
    "data": {
        "monitor_targets": ["position_size", "drawdown", "volatility"],
        "action_thresholds": {
            "high_risk": 0.8,
            "medium_risk": 0.6,
            "low_risk": 0.3
        },
        "emergency_actions": ["close_all_positions", "halt_trading"]
    },
    "model": "glm-5-turbo"  # バランス型
}
```

### 3. 緊急時の指示方法

#### システム緊急停止
```python
emergency_stop = {
    "type": "emergency_stop",
    "reason": "market_crash_detected",
    "severity": "critical",
    "actions": [
        "close_all_positions",
        "notify_admin",
        "log_incident",
        "disable_auto_trading"
    ],
    "model": "glm-5-1"  # 即時対応が必要
}
```

#### トークン切れ時のフォールバック
```python
fallback_instruction = {
    "type": "token_fallback",
    "situation": "low_token_quota",
    "fallback_model": "qwen3:8b",
    "tasks": [
        "critical_operations_only",
        "reduce_api_calls",
        "use_local_models"
    ]
}
```

### 4. 実際の使用例

#### システム起動時の指示
```python
startup_instruction = """
マルチエージェント取引システムを起動してください。

指示：
1. フロントエージェント：メインダッシュボードを生成
2. バックエンドエージェント：Hyperliquidとの同期を開始
3. 分析エージェント：現在の戦略パフォーマンスを分析
4. 調査エージェント：市場マクロ指標を収集
5. 保護エージェント：リスク監視を開始

優先度：リスク管理 > 戦略分析 > 市場調査 > UI更新
"""

#### 戦略最適化指示
```python
optimization_instruction = """
OCPM戦略を最適化してください。

要件：
- 過去30日のデータを使用
- シャープレ比最大化を目標
- 最大ドローダウン10%以内
- 勝率を70%以上に向上

分析項目：
1. RSIパラメータ最適化
2. ATR倍数調整
3. エントリー/エグジット条件
4. ポジションサイズ最適化

出力形式：
- 最適パラメータ
- パフォーマンス予測
- リスク評価
- 実施推奨
"""

#### 緊急対応指示
```python
emergency_instruction = """
市場急落を検知しました。緊急対応を実施してください。

対応ステップ：
1. すべてのポジションを即時決済
2. 自動取引を一時停止
3. 連絡先に通知（admin@example.com）
4. インシデントを記録
5. 状況レポートを作成

監視対象：
- BTC価格の急落（5%以上）
- 流動性の低下
- 取引所の異常
- システムの負荷

モデル：glm-5-1（即時対応のため高精度モデルを使用）
"""
```

### 5. 日常運用の指示パターン

#### 定期タスク
```python
daily_tasks = [
    {
        "time": "09:00",
        "agents": ["research", "protection"],
        "tasks": [
            "market_open_analysis",
            "risk_assessment"
        ]
    },
    {
        "time": "15:00", 
        "agents": ["analysis", "backend"],
        "tasks": [
            "performance_review",
            "strategy_update"
        ]
    },
    {
        "time": "20:00",
        "agents": ["frontend", "protection"],
        "tasks": [
            "daily_report",
            "system_health_check"
        ]
    }
]
```

#### 週次タスク
```python
weekly_tasks = {
    "day": "monday",
    "agents": ["analysis", "research"],
    "tasks": [
        "strategy_backtesting",
        "macro_outlook",
        "parameter_optimization"
    ]
}
```

### 6. 進捗報告の形式

#### タスク完了報告
```python
task_completion_report = {
    "task_id": "task_analysis_001",
    "status": "completed",
    "execution_time": "2分35秒",
    "result": {
        "profit": "+$1250",
        "win_rate": 72,
        "risk_score": 65
    },
    "recommendations": [
        "RSI期間を14→12に調整推奨",
        "ポジションサイズを5%に増やす"
    ],
    "next_steps": [
        "実装を開始",
        "バックテストを実行"
    ]
}
```

#### システム状態報告
```python
system_status_report = {
    "timestamp": "2026-04-10T10:45:23Z",
    "agents": {
        "frontend": {"status": "online", "uptime": "5h23m"},
        "backend": {"status": "working", "task_count": 125},
        "analysis": {"status": "idle", "last_task": "30分前"},
        "research": {"status": "working", "task_count": 89},
        "protection": {"status": "online", "alerts": 0}
    },
    "performance": {
        "token_usage": "15,230 / 50,000",
        "response_time": "1.2秒",
        "success_rate": "98.5%"
    },
    "trading": {
        "total_profit": "+$1,250.50",
        "active_positions": 2,
        "risk_level": "low"
    }
}
```

## 使用例まとめ

1. **マスター・オーケストレーターへの基本指示**でシステム全体の設定を定義
2. **各エージェントへの具体的なタスク指示**で詳細な操作を指定
3. **優先度とモデル選択**を明確にして効率的な処理を促進
4. **緊急時の対応手順**を事前に定義して迅速な対応を可能に
5. **定期タスクの自動化**で運用の効率化を実現

この指示方法を使えば、複数のエージェントを連携させた複雑なタスクを効率的に実行できます。