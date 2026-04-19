# マルチエージェントAIトレードシステム

## アーキテクチャ設計

### マスター/スレーブモデル
```
Master Agent (Ollama Qwen3 8b) → Multi-Agent Orchestration
├── Frontend Agent (GLM-5.1) → ユーザーインターフェース管理
├── Backend Agent (GLM-5-Turbo) → API/データ処理
├── Analysis Agent (GLM-5.1) → 戦略分析と最適化
├── Research Agent (GLM-4.7-Flash) → マクロ調査とデータ収集
├── Protection Agent (GLM-5-Turbo) → リスク管理とモニタリング
└── Local Fallback (Qwen3 8b) → トークン切れ時のフォールバック
```

### モデル優先順位設定
1. **プライマリ**: GLM-5.1 (高精度タスク)
2. **セカンダリ**: GLM-5-Turbo (バランス型)
3. **テリアリ**: GLM-4.7-Flash (高速/低コスト)
4. **フォールバック**: Qwen3 8b (オフライン/無料)

### トークン管理戦略
- RTKプロキシ導入でAPIコールを60-90%削減
- モデル切り替えレート制御
- クォータ監視と自動フォールバック
- ローカル/クラウドハイブリッド構成

## システム構成

### 1. マスター・オーケストレーター
```python
class MasterOrchestrator:
    def __init__(self):
        self.agents = {
            'frontend': FrontendAgent(),
            'backend': BackendAgent(), 
            'analysis': AnalysisAgent(),
            'research': ResearchAgent(),
            'protection': ProtectionAgent()
        }
        self.model_manager = ModelManager()
        self.token_monitor = TokenMonitor()
        
    async def execute_workflow(self, task):
        # モデル選択ロジック
        model = self.model_manager.select_model(task)
        # エージェント割り当て
        assigned_agents = self.assign_agents(task)
        # タスク実行
        return await self.parallel_execution(assigned_agents)
```

### 2. フォールバック・マネージャー
```python
class ModelManager:
    def select_model(self, task):
        if self.token_monitor.has_sufficient_quota():
            if task['complexity'] == 'high':
                return 'glm-5-1'
            elif task['complexity'] == 'medium':
                return 'glm-5-turbo'
            else:
                return 'glm-4-7-flash'
        else:
            return 'qwen3:8b'  # ローカルフォールバック
```

## 実装フェーズ

### Phase 1: 基礎インフラ構築
- RTKプロキシの導入
- エージェント通信プロトコルの設計
- トークン管理システムの実装

### Phase 2: エージェント実装
- 各エージェントのクラス定義
- マスター・オーケストレーター
- フォールバック機構

### Phase 3: 統合とテスト
- 現有のトレードシステムとの統合
- パフォーマンステスト
- トークン使用量の最適化

### Phase 4: デプロイと運用
- 本番環境への展開
- モニタリングとアラート
- 自動化ワークフロー

## 技術仕様

### 通信プロトコル
- Agent間通信: ZeroMQ
- データ転送: Protocol Buffers
- ステート管理: Redis

### 負荷分散
- タスクキュー: Celery + Redis
- 並列処理: asyncio
- リトライ機構: Exponential Backoff

### 監視・ログ
- ログレベル: INFO/DEBUG/WARNING/ERROR
- パフォーマンスメトリクス
- トークン使用量ダッシュボード

## コスト削見込み

- 月額 $2,000 → $0（RTK導入でAPIコスト90%削減）
- トークン消費量: 60-90%削減（RTK + ローカルモデル）
- 負荷分散で応答速度向上
- 自動フォールバックでシステム安定性向上