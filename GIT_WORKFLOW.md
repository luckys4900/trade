# Git Workflow - Worktree活用ガイド

記事より: **Git Worktree = 物理コピー、並行作業で無衝突**

---

## 基本概念

### 通常の方法（ブランチ切替）

```bash
❯ git checkout feature/add-strategy
  Switched to branch 'feature/add-strategy'
  
❯ code .  # 同じディレクトリで編集
  ↑ 前のブランチと混在、git status が複雑
```

### Worktree の方法（物理コピー）

```bash
❯ git worktree add ./worktree/strategy feature/add-strategy
  ✓ ./worktree/strategy/
  ✓ 別ディレクトリに branch の完全コピー
  ✓ 2つの Claude セッション並行可能

[Terminal 1] ~/trade (main)
❯ claude
  Task A: バグ修正

[Terminal 2] ~/worktree/strategy
❯ claude
  Task B: 新戦略追加
  
→ 互いに干渉しない ✓
```

---

## セットアップ

### Worktree ディレクトリ作成

```bash
❯ mkdir -p worktrees
❯ git worktree add ./worktrees/strategy feature/add-strategy
```

**確認**:

```bash
❯ git worktree list

/c/Users/user/Desktop/trade                  abcdef1 [main]
/c/Users/user/Desktop/trade/worktrees/strategy  123456 [feature/add-strategy]
```

### 複数の worktree を並行

```bash
# Terminal 1: main で緊急パッチ
❯ cd ~/trade
❯ git checkout -b hotfix/rsi-param
❯ claude

# Terminal 2: 新機能開発
❯ git worktree add ./worktrees/whale-v2 feature/whale-v2
❯ cd ./worktrees/whale-v2
❯ claude
```

---

## ワークフロー例

### シナリオ: 新戦略を追加（バージョン2）

#### ステップ 1: ブランチ作成 & Worktree セット

```bash
❯ git checkout -b feature/range-mr-v2
❯ git worktree add ./worktrees/range-mr-v2 feature/range-mr-v2
❯ cd ./worktrees/range-mr-v2
```

#### ステップ 2: Subagent で実装

```bash
❯ claude

"Range MR v2 戦略を追加してください:
- バックテスト期間: 過去60日
- ドローダウン上限: 10%
- テストファイル: test_range_mr_v2.py
- 対象: BTC 4h
"

実装: コード、テスト、ドキュメント
```

#### ステップ 3: テスト & コミット

```bash
# Worktree の中で
❯ pytest test_range_mr_v2.py
  ✓ All tests passed

❯ git add -A
❯ git commit -m "feat: add Range MR v2 strategy with 60-day backtest"
```

#### ステップ 4: PR & Merge

```bash
# メインディレクトリへ戻る
❯ cd ~/trade

# PR 作成
❯ gh pr create --title "Range MR v2: BTC 4h" \
    --body "..."

# レビュー & マージ
❯ git pull
❯ git checkout main
❯ git merge feature/range-mr-v2
```

#### ステップ 5: Worktree クリーンアップ

```bash
❯ git worktree remove ./worktrees/range-mr-v2
  ✓ Removed worktree (branch ~/trade/worktrees/range-mr-v2)
```

---

## Advanced: 複数 Worktree の並行操作

### シナリオ: 3つの改善を同時進行

```
main (master)
  ├── worktree/strategy-tuning     (RSI パラメータ最適化)
  ├── worktree/whale-v2             (クジラシステムv2)
  └── worktree/ui-dashboard         (ダッシュボード改善)
```

**セットアップ**:

```bash
❯ git worktree add ./worktrees/strategy-tuning feature/rsi-tuning
❯ git worktree add ./worktrees/whale-v2 feature/whale-v2
❯ git worktree add ./worktrees/ui-dashboard feature/ui-dashboard
```

**並行作業**:

```bash
# Terminal 1
❯ cd ~/trade/worktrees/strategy-tuning
❯ claude  # Subagent: RSI パラメータ最適化

# Terminal 2
❯ cd ~/trade/worktrees/whale-v2
❯ claude  # Subagent: クジラシステム v2

# Terminal 3
❯ cd ~/trade/worktrees/ui-dashboard
❯ claude  # Subagent: UI 改善

# Main Terminal
❯ cd ~/trade  # main のまま
```

**メリット**:
- 3つのセッション並行実行
- Context 90% 削減（メインセッションは軽い）
- Merge 衝突なし（別ディレクトリ）
- 本来 45分 → 15分で完了

---

## トラブルシューティング

### Worktree がロック状態

```bash
# 症状
❯ git worktree remove ./worktrees/strategy
fatal: '/path/to/worktree' is a working tree

# 原因: Claude セッションがまだ active
# 解決
❯ cd ~/trade  # worktree から出る
❯ pkill -f "claude.*worktree"  # 必要に応じて強制終了
❯ git worktree remove ./worktrees/strategy --force
```

### ブランチ競合

```bash
# 症状
❯ git checkout feature/strategy
fatal: reference is not a tree: 2ab1c3

# 原因: 同じブランチで複数 worktree
# ❌ NG: 同じブランチで複数 worktree
❯ git worktree add ./w1 feature/strategy
❯ git worktree add ./w2 feature/strategy  ← エラー

# ✓ 正解: 各ブランチは worktree ごとに
❯ git worktree add ./w1 feature/strategy
❯ git worktree add ./w2 feature/whale
```

### Worktree リスト確認

```bash
❯ git worktree list --prune

/path/to/main              abc [main]
/path/to/worktrees/s1      def [feature/strategy] (detached)
/path/to/worktrees/s2      ghi [feature/whale]
/path/to/worktrees/orphan  jkl (broken)  ← 削除推奨
```

**破損した worktree 削除**:

```bash
❯ git worktree remove /path/to/worktrees/orphan --force
```

---

## ベストプラクティス

### 1. Worktree 命名規則

```bash
# ✓ 明確な命名
./worktrees/strategy-tuning
./worktrees/whale-v2
./worktrees/hotfix-rsi-param

# ❌ 曖昧な命名
./worktrees/temp
./worktrees/test
./worktrees/new
```

### 2. ブランチ戦略

```bash
# main:    安定版、テスト済み
# develop: 統合版
# feature/*: 機能開発
# hotfix/*:  緊急バグ修正
```

### 3. Worktree 整理

```bash
# 定期的に cleanup
❯ git worktree prune

# 不要なディレクトリを確認
❯ ls -la ./worktrees/
```

---

## 推奨フロー

```
1. 機能要件確認
   ❯ /brainstorm

2. 実装計画作成
   ❯ /plan

3. Worktree セット
   ❯ git worktree add ./worktrees/feature-X feature/X

4. 実装（Subagent Driven）
   ❯ cd ./worktrees/feature-X
   ❯ claude [Subagent タスク]

5. テスト & コミット
   ❯ pytest test_*.py
   ❯ git commit -m "feat: ..."

6. PR & マージ
   ❯ cd ~/trade
   ❯ gh pr create
   ❯ git merge feature/X

7. クリーンアップ
   ❯ git worktree remove ./worktrees/feature-X
   ❯ git branch -d feature/X
```

---

## Git の基本コマンド

### セーフティネット

```bash
# 変更内容を確認
❯ git status
❯ git diff

# ローカルコミットを確認
❯ git log --oneline -10

# 直前のコミットを取り消し（変更は残す）
❯ git reset --soft HEAD~1
```

### Merge & Push

```bash
# メインブランチ最新化
❯ git checkout main
❯ git pull

# Worktree ブランチを main へマージ
❯ git merge feature/strategy

# リモートへプッシュ
❯ git push origin main
```

---

## 参考ドキュメント

- [DEVELOPMENT_PROCESS.md](DEVELOPMENT_PROCESS.md) - プロセスフロー
- [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) - Context 管理
- [TOOLING.md](TOOLING.md) - ツール選択
