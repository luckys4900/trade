# Tooling Guide - MCP vs Skills

記事より: **「MCP は古いアプローチ、Skills が新標準」**

---

## MCP vs Skills: 比較

| 項目 | MCP | Skills |
|------|-----|--------|
| **Context消費** | 5.7K+ 常時 | 50 tokens (header) |
| **読み込み方式** | グローバル | オンデマンド |
| **カスタマイズ** | 固定 | 編集可能 |
| **複合利用** | 難しい | 可能（組合せ） |
| **API対応** | 事前対応が必要 | ドキュメントで OK |

### コスト効果

```
3つの MCP で 17K tokens 無駄（会話0）

vs

3つの Skill で 150 tokens
（使う時だけ呼び出し）

節約: 112 倍
```

---

## MCP (Model Context Protocol)

### いつ使うか

**✓ グローバルで必須**:
- Exa Search（検索）
- Chrome DevTools（ブラウザ自動化）

**⚠ プロジェクトスコープ**:
- Supabase（DB操作）
- Postgres（DB操作）
- GitHub API（リポジトリ操作）

**✗ 避けるべき**:
- 1回だけ使う MCP
- Skill で代替可能な MCP
- 全プロジェクト共有不要な MCP

### インストール

**グローバル（必要最小限）**:

```bash
# 全プロジェクトで使う
❯ claude mcp add exa-search \
    --scope user \
    npx @anthropic/exa-search-mcp

# 検索と Exa 統合
❯ /mcp
  exa-search ✓ connected (user)
```

**プロジェクトスコープ**:

```bash
# このプロジェクトのみ
❯ claude mcp add supabase \
    --scope project \
    npx supabase-mcp
```

### 確認

```bash
# インストール済み MCP
❯ /mcp

# グローバルのみ表示
❯ claude mcp list --scope user

# プロジェクトスコープのみ表示
❯ claude mcp list --scope project
```

---

## Skills（推奨）

### 利用可能なスキル

```bash
❯ /skills-list
```

主要スキル（全て無料、Superpowers パッケージ）:

| スキル | 用途 | Context |
|--------|------|---------|
| **brainstorm** | 要件確認 | 50 tokens |
| **writing-plans** | 実装計画 | 50 tokens |
| **subagent-driven-dev** | 並行実装 | 50 tokens |
| **code-review** | コード品質 | 50 tokens |
| **test-driven-dev** | TDD | 50 tokens |
| **systematic-debugging** | バグ修正 | 50 tokens |

### スキル実行例

```bash
# Brainstorm
❯ /brainstorm
  Range MR v2 戦略を追加したい

# 実装計画
❯ /plan
  [Brainstorm 結果から自動継続]

# 並行実装
❯ /subagent-driven-development
  Strategy A, Strategy B, UI改善を並行実施
  
→ Context 利用率: 9% のみ ✓
```

### 独自スキル作成

```bash
# Skill Creator で新規作成
❯ /skill-creator
  
名前: whale-validator
説明: クジラシステムのパラメータ検証

出力: .claude/skills/whale-validator.md
```

**スキル構造**:

```markdown
---
name: whale-validator
description: Validate whale system parameters
---

## Overview
[スキル内容]

## Checklist
- [ ] Item 1
- [ ] Item 2
```

---

## 現在のプロジェクト設定

### インストール済み

```bash
❯ /mcp
  [なし（最適化済み）]

❯ /skills-list
  superpowers:*  ✓ 有効（Brainstorm, Plan等）
```

### 推奨追加

```bash
# グローバル（全プロジェクト共通）
- なし（必要最小限を保つ）

# プロジェクトスコープ
- superpowers（既に有効）
- custom-skill: whale-analyzer（必要に応じて）
```

---

## API と Skill の組み合わせ

### パターン A: MCP で完全対応

```bash
# Supabase の全 API が MCP 対応
❯ claude mcp add supabase --scope project

使用例:
  "Supabase から trade_history テーブルを取得"
  → MCP が直接実行
```

### パターン B: API ドキュメント + Skill

```bash
# API ドキュメント URL があれば Skill で十分
❯ /skill-creator
  名前: hyperliquid-analyzer
  説明: Hyperliquid API を使用した分析
  入力: API ドキュメント URL

→ MCP なしで実装可能
```

### パターン C: Skill + CLI

```bash
# Python API クライアント + Skill
# hyperliquid-python-sdk を直接使用
# Skill で Bash コマンド実行

スキル内容:
  python hyperliquid_analyzer.py --action=validate-wallets
```

---

## Decision Tree: ツール選択

```
新しい機能が必要か？

↓
1. これは全プロジェクトで使うか？
   YES → MCP (グローバル) に検討
   NO  → ステップ 2 へ
   
↓
2. API は MCP 対応か？
   YES → MCP (プロジェクトスコープ) 
   NO  → ステップ 3 へ
   
↓
3. Skill で代替できるか？
   YES → Skill を選択 ✓
   NO  → ステップ 4 へ
   
↓
4. 独自 MCP を作成すべきか？
   YES → MCP (プロジェクトスコープ)
   NO  → Bash + Skill で実装
```

---

## ベストプラクティス

### 1. グローバル MCP を最小化

```bash
# ❌ よくある間違い
claude mcp add postgres --scope user
claude mcp add supabase --scope user
claude mcp add anthropic --scope user
[... 15 個 ...]

→ 毎セッション 5.7K+ tokens 無駄

# ✓ 正解
[グローバルなし]
各プロジェクトで必要なものをスコープ指定
```

### 2. Skill の活用

```bash
# MCP より先に Skill を検索
❯ /skills-list

# なければ Skill Creator で作成
❯ /skill-creator
```

### 3. 定期的な整理

```bash
# 月 1 回確認
❯ claude mcp list --scope user

# 不要な MCP を削除
❯ claude mcp remove <name> --scope user
```

---

## 実装例: クジラシステム検証スキル

### 作成手順

```bash
❯ /skill-creator

名前: whale-validator
説明: クジラシステムのパラメータと結果を検証
スキル内容: [下記参照]
```

### スキルファイル例

```markdown
---
name: whale-validator
description: Validate whale system parameters and outcomes
---

## Checklist
- [ ] whale_wallets.json チェック
  - 3つのウォレットが存在
  - AUM が記載されている
  
- [ ] Sortino 計算を検証
  - sqrt(actual_trades_per_year) を使用
  - 定数 1.587 を使用していない
  
- [ ] Signal generation テスト
  - whale_signal.json が生成されている
  - timestamp が 30分以内
  
- [ ] 30日検証の進捗確認
  - trade_alignment_log.json が更新されている
  - ログエントリが 30+ 個ある
```

### 実行例

```bash
❯ /whale-validator

✓ whale_wallets.json チェック...
✓ Sortino 計算検証...
⚠ Signal generation: whale_signal.json がやや古い (25分前)
✓ 30日検証: 45エントリー記録済み

推奨: whale_monitor.py が動作していることを確認
```

---

## トラブルシューティング

### MCP が応答しない

```bash
# 再接続
❯ /mcp

# 詳細情報
❯ /mcp --verbose

# 削除 & 再インストール
❯ claude mcp remove <name>
❯ claude mcp add <name>
```

### Skill が見つからない

```bash
# スキルリスト更新
❯ /skills-list

# キャッシュクリア
❯ claude --clear-cache
```

### Context が膨張

```bash
# グローバル MCP を確認
❯ claude mcp list --scope user

# 不要な MCP を削除
❯ claude mcp remove <name> --scope user

# セッション再開
❯ /clear
❯ claude
```

---

## 参考ドキュメント

- [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) - Context 予算管理
- [DEVELOPMENT_PROCESS.md](DEVELOPMENT_PROCESS.md) - プロセスフロー
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) - Git Worktree
