# Awesome Claude Code ガイド

**インストール**: `awesome-claude-code@claude-plugins-official`

このガイドはセッション開始時に参照可能です。

## スキル早見表

### プロセス系（最初に使用）
- **superpowers:brainstorming** - 新機能設計前に構造化
- **superpowers:writing-plans** - 多段階タスク計画
- **superpowers:executing-plans** - 計画実行サポート
- **superpowers:systematic-debugging** - バグ調査体系化

### 検証系（実装後に使用）
- **superpowers:test-driven-development** - テスト駆動開発
- **superpowers:verification-before-completion** - 完了前検証
- **superpowers:code-review** - コードレビュー
- **superpowers:requesting-code-review** - レビュー依頼

### ツール系
- **superpowers:using-git-worktrees** - 機能ブランチ隔離
- **claude-api** - Claude API実装
- **loop** - 定期実行タスク
- **schedule** - スケジュール実行

## 取引ボット向け推奨ワークフロー

### 新規戦略設計時
```
1. superpowers:brainstorming
   - 戦略コンセプト
   - 期待値の根拠
   - リスク管理

2. superpowers:writing-plans
   - 実装ステップ
   - テストプラン
   - 検証基準

3. superpowers:test-driven-development
   - テスト作成
   - 実装
   - バックテスト
```

### バグ修正時
```
1. superpowers:systematic-debugging
   - 根本原因特定
   - 再現条件確認
   - 修正案検証

2. superpowers:verification-before-completion
   - ユニットテスト
   - 統合テスト
   - ライブテスト（paper）
```

### 本番導入時
```
1. superpowers:executing-plans
   - フェーズ1: ペーパートレード
   - フェーズ2: 小額リアル
   - フェーズ3: 本番スケール

2. superpowers:requesting-code-review
   - セキュリティ確認
   - ロジック妥当性
   - リスク管理妥当性
```

## セッション開始チェックリスト

毎朝:
- [ ] システム稼働確認 (`03_STATUS.lnk`)
- [ ] 前日の意思決定確認 (memory/DAILY_ANALYSIS.md)
- [ ] 今日のTo-Do確認

新規開発時:
- [ ] superpowers:brainstorming 使用
- [ ] 期待値分析完了
- [ ] リスク管理承認済み

トラブル発生時:
- [ ] superpowers:systematic-debugging 起動
- [ ] ログ確認
- [ ] 原因特定
- [ ] 修正テスト

## よく使うコマンド

```bash
# スキル一覧確認
claude skill list

# 特定スキル詳細確認
claude skill show brainstorming

# 計画作成
superpowers:writing-plans "戦略Xを実装する"

# デバッグ開始
superpowers:systematic-debugging "エラーメッセージXが発生"
```

## リソース

- GitHub: https://github.com/hesreallyhim/awesome-claude-code
- スキルマーケット: claude.ai/marketplace
- ドキュメント: docs.claude.ai

---
**Last Updated**: 2026-04-16
**Version**: Awesome Claude Code Integration v1.0
