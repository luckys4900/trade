# Context Management Guide

記事より: **Context = 最も重要な概念**

Context は予算です。全てが消費します: ツール、CLAUDE.md、MCP、スキル、会話。

---

## Context 帯域幅の理解

### 効果的なゾーン

| 使用率 | 状態 | 推奨アクション |
|-------|------|-----------------|
| 0-50% | ✓ 安全 | 通常作業可 |
| 50-70% | ⚠ 注意 | 監視開始 |
| 70-85% | 🔴 危険 | セッション終了推奨 |
| 85%+ | 🚨 臨界 | 自動 compact（データ喪失可） |

### Status Line を活用

```bash
❯ ~/trade · opus-4 · 1M ctx · 67% ■■■■■■░░░░░
                          ↑ 常に監視
```

インストール:

```bash
claude --install-status-line
```

---

## Context を消費するもの

### 1. CLAUDE.md（新セッション開始時）

**影響**: 最大

```
CLAUDE.md なし:  
  ✗ プロジェクト構造スキャン
  ✗ package.json, config読み込み
  ✗ ファイル47個分析
  → 33K tokens 消費（会話0個）

CLAUDE.md あり（174行）:
  ✓ 読み込み完了
  ✓ 運用情報あり
  → 1.2K tokens のみ
  
削減率: 27倍
```

**現在**: 174行 ✓

**ルール**: < 500行 厳守

### 2. MCP (Model Context Protocol)

**影響**: 高

グローバルに15 MCP をインストール:

```
❯ /mcp

chrome-devtools       ✓ connected (user)
exa-search           ✓ connected (user)
supabase             ✓ connected (project)
[...12 more]

全て読み込み: 5.7K+ tokens/セッション
```

**推奨**: グローバル MCP は最小化

```bash
# ✓ グローバル: 必須のみ
claude mcp add exa-search --scope user      # 検索
claude mcp add chrome-devtools --scope user # ブラウザ

# ✗ プロジェクトスコープで
claude mcp add supabase --scope project     # DB専用
claude mcp add postgres --scope project     # DB専用
```

**現在の設定**:
- グローバル: なし（最適）
- プロジェクト: Superpowers スキル

### 3. Skills

**影響**: 低（ヘッダーのみメモリ）

スキルはヘッダー（50 tokens）のみが常駐:

```
Brainstorm skill header:  ≈50 tokens
  ↓ 使用時にのみ全文ロード
Brainstorm skill body:    ≈800 tokens (一時的)
  ↓ 完了後は自動削除
```

**効率性**:
- MCP: 5.7K tokens 常時
- Skill: 50 tokens + 800 (一時)

**推奨**: MCP の代わりに Skill を使用

### 4. 会話

**影響**: 中程度

```
簡単な質問:      ≈500 tokens
複雑な分析:      ≈3K tokens
複数ファイル修正: ≈10K+ tokens
```

---

## 3 つのルール: Context を救う

### Rule 1: CLAUDE.md < 500行

**効果**: 27倍削減

```
セッション開始効率:
  新規: -33K tokens
  +CLAUDE.md: -1.2K tokens
  差分: +31.8K tokens 節約/セッション
```

**現状**: 174行 ✓

### Rule 2: 1 Task = 1 Session

**効果**: セッション間の独立性

```
❌ 間違い:
  Task 1  [███████░░░░ 60%]
  Task 2  [██████████░░ 80%]
  Task 3  [████████████ 100%] ← Context溢れ
  
✓ 正解:
  Task 1  [██████░░░░░ 40%] → /clear
  新セッション開始
  Task 2  [██████░░░░░ 40%] → /clear
  新セッション開始
  Task 3  [██████░░░░░ 40%] ✓
```

**実行**:
```bash
# Task 完了後
❯ /clear

# 新セッションで再開
❯ claude
  Loaded CLAUDE.md (174 lines)
  Ready. 1.2K tokens
```

### Rule 3: ツール/MCP はプロジェクトスコープ

**効果**: グローバル汚染防止

```bash
# ✗ グローバル追加（全プロジェクトに影響）
claude mcp add my-tool --scope user

# ✓ プロジェクトスコープ（このプロジェクトのみ）
claude mcp add my-tool --scope project
```

**確認**:
```bash
claude mcp list --scope user    # 最小化
claude mcp list --scope project # プロジェクト毎に制御
```

---

## Context が圧迫時の対応

### ステップ 1: セッション終了

```bash
# Context 70% 以上の場合
❯ /clear

# または
❯ exit
```

新セッション開始で Context リセット。

### ステップ 2: ファイル整理

```bash
# 古いドキュメント → ARCHIVE へ
mv IMPLEMENTATION_REPORT_v1.md ARCHIVE/
mv IMPLEMENTATION_REPORT_v2.md ARCHIVE/
mv FINAL_SUMMARY_OLD.md ARCHIVE/

# 確認
git status
```

**現在の状況**:
- ドキュメント: 多数 → ARCHIVE 化検討
- 未追跡ファイル: 100+個 → `.gitignore` 確認

### ステップ 3: CLAUDE.md サイズ確認

```bash
wc -l CLAUDE.md  # 174行 ✓

# 大きい場合（>300行）:
# → docs/ へ詳細移行
# → CLAUDE.md に概要のみ記載
```

---

## Session 間の Knowledge Persistence

### Memory システム（推奨）

重要な学習・パターンを記録:

```bash
# メモリに保存
.claude/projects/[project]/memory/

例:
- user_profile.md
- project_context.md
- feedback.md
- reference.md
```

このガイドも memory に保存済み:

```
memory/MEMORY.md
  → [Context Management](context_management.md)
  → [Development Process](development_process.md)
  → [User Profile](user_profile.md)
```

### CLAUDE.md への記載

永続的に必要な情報:

```markdown
## Next Session

When switching models:
1. Check memory/implementation_whale_system.md
2. This CLAUDE.md contains operational guide
3. Run 03_STATUS.lnk to verify system state
4. All code is frozen; 30-day validation in progress
```

---

## チェックリスト: Context 管理

新セッション開始時:

- [ ] `claude --install-status-line` で Status Line 確認
- [ ] CLAUDE.md 読み込み完了を待つ
- [ ] Memory から必要な context を読み込む
- [ ] `/mcp list` で不要な MCP がないか確認
- [ ] Task を明確に定義

セッション中:

- [ ] 定期的に Status Line を確認
- [ ] 70% を超える前にセッション終了
- [ ] ファイルが肥大化していないか確認

セッション終了時:

- [ ] Task 完了か確認
- [ ] Memory に学習を保存（新規の場合）
- [ ] `/clear` でセッション終了
- [ ] 不要ドキュメントを ARCHIVE へ移行

---

## 参考: Context 消費の実例

### パターン A: Context 効率的（推奨）

```
セッション開始:  1.2K (CLAUDE.md のみ)
Task 開始:      +2K (タスク内容)
実装:          +15K (ファイル修正)
テスト:        +5K
合計:          23.2K = 23% ✓

/clear でリセット
```

### パターン B: Context 非効率（避けるべき）

```
セッション開始:  33K (CLAUDE.md なし)
Task 1:        +20K
Task 2:        +25K
Task 3:        +20K
ドキュメント読み込み: +15K
合計:          113K = 113% ☠ オーバーフロー
```

---

## さらに詳しく

- [DEVELOPMENT_PROCESS.md](DEVELOPMENT_PROCESS.md) - Superpowers プロセス
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) - Git worktree 活用
- [TOOLING.md](TOOLING.md) - MCP vs Skills 選択基準
