# Development Process - Superpowers Framework

このプロジェクトの改善・機能追加時に従うべき標準プロセス。

**参照**: [Claude Code Complete Guide - zostaff](https://x.com/zostaff) より Superpowers プロセス採用

## 標準プロセス

全ての機能追加・改善は以下の流れで実施：

```
1. Brainstorm     → 要件と設計を理解
2. Plan           → 実装戦略を文書化  
3. Subagent Dev   → 並行実装で効率化
4. Code Review    → 品質確保
5. Merge/Deploy   → 統合
```

### 1. Brainstorm フェーズ

**何をするか**: 機能要件とデザインを検証

```bash
❯ /brainstorm
```

**出力物**:
- 要件定義
- 設計概要
- 技術的制約の確認

**例**: 新しい戦略を追加する場合
- 入力: 「Range MR 戦略を BTC 4h に追加」
- 確認項目:
  - RSI/ATR パラメータ範囲
  - バックテスト期間
  - リスク制限（ドローダウン上限など）
  - 本物口座での テスト計画

### 2. Plan フェーズ

**何をするか**: 実装計画を作成

```bash
❯ /plan
```

**出力物**:
- ファイル修正リスト
- 実装ステップ（分割可能）
- テスト戦略
- デプロイ手順

**チェックリスト**:
- [ ] ファイルパス確認
- [ ] 依存関係確認
- [ ] ロールバック計画（必要に応じて）

### 3. Subagent Driven Development

**何をするか**: 並行実装で効率化

```bash
❯ /subagent-driven-development
```

**特徴**:
- 複数タスクを同時実行
- Context 効率化（メインセッション 9% vs 通常 85%+）
- 3x 高速化、6x コスト削減

**例**: 3つの機能を追加
```
セッション1 (直列): 15分 × 3 = 45分, 300K tokens
セッション (並行):  5分, 50K tokens in main
```

**ガイド**:
- 1 セッション = 1 サブエージェント × 1 タスク
- テスト結果を報告
- エラーは即座に修正

### 4. Code Review フェーズ

**何をするか**: 品質保証

```bash
❯ /review-pr
```

**確認項目**:
- [ ] テスト通過
- [ ] CLAUDE.md 更新
- [ ] ログ・エラーハンドリング
- [ ] リスク管理の維持

### 5. Merge/Deploy フェーズ

```bash
git add <files>
git commit -m "feat: <description>"
git push origin <branch>
```

---

## セッション管理戦略

### Rule 1: 1 Task = 1 Session

**原則**: 1つのタスク完了後、必ず `/clear` してセッション終了

```bash
# タスク完了後
❯ /clear

# 新セッションでクリーンなコンテキストから開始
❯ claude
  Loaded CLAUDE.md (174 lines)
  Ready. 1.2K tokens only
```

**効果**:
- Context leak 防止
- トークン効率化
- セッション間の独立性

### Rule 2: CLAUDE.md < 500 行

**現状**: 174 行 ✓

**保守方法**:
- 運用ガイド = CLAUDE.md に
- 詳細な実装仕様 = docs/ 配下に
- 過去の実装報告 = ARCHIVE/ に

### Rule 3: ツール/MCPはプロジェクトスコープ

**グローバル MCP**（全プロジェクト共通）:
```bash
claude mcp add exa-search --scope user
claude mcp add chrome-devtools --scope user
```

**プロジェクトスコープ MCP**（このプロジェクトのみ）:
```bash
claude mcp add <tool> --scope project
```

**現在の設定**:
- グローバル: なし（最小化）
- プロジェクト: Superpowers スキル

---

## Context 監視

### Status Line で確認

```
~/trade · opus-4 · 1M ctx · 45% ■■■■░░░░░░
                              ↑ この数値を監視
```

**警告レベル**:
- 0-50% ✓ 安全ゾーン
- 50-70% ⚠ 注意
- 70-85% 🔴 危険（新セッション推奨）
- 85%+ 🚨 自動 compact（データロス可能性）

### Context 圧迫時の対応

1. **セッション終了**: `/clear` → 新セッション開始
2. **ファイル整理**: 不要なドキュメントを ARCHIVE/ へ
3. **CLAUDE.md 確認**: 500行以下か再確認

---

## Model Selection

各タスクに応じた最適モデル：

| タスク | モデル | 理由 |
|--------|--------|------|
| 計画・設計 | Opus 4.6 | 複雑な判断 |
| コード実装 | Sonnet 4.6 | 速度 × 品質 |
| ドキュメント検索 | Haiku 4.5 | 高速 |
| バックテスト分析 | Opus 4.6 | 精密分析 |

---

## チェックリスト: 新機能追加

新しい戦略やシステムを追加する場合：

- [ ] Brainstorm: 要件確認
- [ ] Plan: 実装計画作成
- [ ] バックテスト: 30日以上のデータで検証
- [ ] Subagent Dev: 実装 & テスト
- [ ] Code Review: 品質確保
- [ ] CLAUDE.md 更新: 新機能の概要追加
- [ ] Merge: メインブランチへ統合
- [ ] Validation: 本番環境での動作確認（1-2日）

---

## 参考ドキュメント

- [Git Workflow Guide](GIT_WORKFLOW.md) - ワークツリー活用
- [Tooling Guide](TOOLING.md) - MCP vs Skills
- [Context Management](CONTEXT_MANAGEMENT.md) - メモリ管理
