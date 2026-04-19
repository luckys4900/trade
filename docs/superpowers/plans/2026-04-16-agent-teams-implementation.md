# Agent Teams (マルチエージェント) 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** マルチエージェント（Agent Teams）トレーディングシステムを実装し、RTKプロキシ、ZeroMQ通信、トークン管理システムを統合して、複数のAIエージェントが協調動作する自動取引プラットフォームを構築する。

**Architecture:** Master Orchestratorがタスク分配・スケジューリングを行い、5つの専門エージェント（Frontend/Backend/Analysis/Research/Protection）が非同期並列処理で実行。トークン不足時は自動的にローカルモデル（Qwen3 8b）にフォールバック。ZeroMQで低遅延通信、Redisでステート管理。

**Tech Stack:** Python 3.10+, ZeroMQ, Redis, aiohttp, asyncio, RTK Proxy, Hyperliquid SDK, numpy, pandas

---

## ファイル構造

```
trade/
├── multi_agent_config.json           [既存]
├── master_orchestrator.py            [拡張]
├── agents.py                         [拡張]
├── token_manager.py                  [新規]
├── rtk_proxy_client.py               [新規]
├── agents/
│   ├── __init__.py                   [新規]
│   ├── frontend_agent.py             [新規]
│   ├── backend_agent.py              [新規]
│   ├── analysis_agent.py             [新規]
│   ├── research_agent.py             [新規]
│   └── protection_agent.py           [新規]
├── communication/
│   ├── __init__.py                   [新規]
│   ├── zeromq_broker.py              [新規]
│   └── message_protocol.py           [新規]
├── monitoring/
│   ├── __init__.py                   [新規]
│   ├── performance_monitor.py        [新規]
│   └── health_check.py               [新規]
├── tests/
│   ├── test_agent_teams.py           [新規]
│   ├── test_token_manager.py         [新規]
│   ├── test_zeromq_broker.py         [新規]
│   └── test_integration.py           [新規]
└── logs/
    └── agent_teams/                  [新規ディレクトリ]
```

---

## Phase 1: 基礎インフラ構築

### Task 1: トークン管理システムの実装

**Files:**
- Create: `token_manager.py`
- Create: `tests/test_token_manager.py`

- [ ] **Step 1: トークン管理クラスのテスト作成**

実装ファイル内に詳細コード記載

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
cd C:\Users\user\Desktop\cursor\trade
python -m pytest tests/test_token_manager.py::test_token_quota_initialization -v
```

- [ ] **Step 3: token_manager.py 実装**

実装ファイル内に完全なコード記載

- [ ] **Step 4: テスト実行で成功を確認**

```bash
python -m pytest tests/test_token_manager.py -v
```

すべてのテストが PASSED になることを確認

- [ ] **Step 5: コミット**

```bash
git add token_manager.py tests/test_token_manager.py
git commit -m "feat: add token management system with RTK proxy support

- Implement TokenQuota for tracking per-model usage
- Add TokenManager for centralized token quota monitoring
- Implement ModelSelector for intelligent model selection based on quota
- Add RTKProxyClient for token savings estimation
- Support automatic fallback to local models when quotas exceeded
- Add comprehensive test suite with 7 tests"
```

---

### Task 2: ZeroMQ通信プロトコルの実装

**Files:**
- Create: `communication/zeromq_broker.py`
- Create: `communication/message_protocol.py`
- Create: `communication/__init__.py`
- Create: `tests/test_zeromq_broker.py`

- [ ] **Step 1: テスト作成**

実装ファイル内に詳細テストコード記載

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
python -m pytest tests/test_zeromq_broker.py::test_message_creation -v
```

- [ ] **Step 3: message_protocol.py 実装**

実装ファイル内に完全なコード記載

- [ ] **Step 4: zeromq_broker.py 実装**

実装ファイル内に完全なコード記載

- [ ] **Step 5: communication/__init__.py 作成**

実装ファイル内に記載

- [ ] **Step 6: テスト実行で成功を確認**

```bash
python -m pytest tests/test_zeromq_broker.py -v
```

- [ ] **Step 7: コミット**

```bash
git add communication/ tests/test_zeromq_broker.py
git commit -m "feat: implement ZeroMQ communication protocol

- Add MessageType enum and Message class for standardized message format
- Implement TaskRequest and TaskResult message types
- Create ZeroMQBroker with router/dealer pattern for async communication
- Add BrokerConfig for flexible broker configuration
- Implement receive/send/monitoring loops with error handling
- Add message statistics tracking
- Include comprehensive tests"
```

---

### Task 3: マスターオーケストレーターの完成

**Files:**
- Modify: `master_orchestrator.py` (補足実装)

- [ ] **Step 1: 現在の master_orchestrator.py を確認**

- [ ] **Step 2: token_manager と zeromq_broker との統合**

既存ファイルにトークン管理とZeroMQ統合コードを追加

- [ ] **Step 3: エージェント管理機能の拡張**

- [ ] **Step 4: タスク分配ロジックの実装**

- [ ] **Step 5: テスト実行**

```bash
python -m pytest tests/test_agent_teams.py -v
```

- [ ] **Step 6: コミット**

---

## Phase 2: エージェント実装

### Task 4-8: 各エージェント実装

各エージェントの実装は Task 別に進める

---

## 実行方法

このプランを実装するには以下のどちらかを選択：

**1. Subagent-Driven (推奨)**
- 各 Task ごとに独立したサブエージェントを派遣
- Task 完了後にレビュー

**2. Inline Execution**
- `superpowers:executing-plans` スキルを使用
- このセッション内で順序実行

---

## 実装済みのコンポーネント

✓ multi_agent_config.json - 全エージェント設定完成
✓ master_orchestrator.py - スケルトン実装
✓ agents.py - 基底クラス実装

## 実装予定のコンポーネント

□ token_manager.py - トークン管理システム
□ communication/ - ZeroMQ通信
□ agents/* - 5つの専門エージェント
□ monitoring/ - パフォーマンス監視
□ テストスイート - 統合テスト

