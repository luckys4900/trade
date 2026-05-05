# 🐋 Whale Inflow Short Strategy - クイックスタート

**Status**: ✅ IS/OOS検証完了・実装可能  
**Created**: 2026-05-02  
**Last Updated**: 2026-05-05

---

## 📌 LLMへの指示方法（重要）

次回のセッションで新規戦略について指示したい場合は、**以下のファイル名を指定してください**：

### ✅ 推奨される指示方法

```
新規戦略「Whale Inflow Short」について確認してください。
参考資料：
- memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md
- memory/whale_inflow_short_strategy_research.md
- 特にセクション10（OOS検証）とセクション12（Deep Factor Analysis）

確認項目：
1. 3つの戦略バリアント（Robinhood, 12h Multi-Exchange, gate.io）の理解
2. IS/OOS検証結果の評価
3. 実装の優先順位
4. 現在の口座資金$190での開始可否
```

### ❌ 避けるべき指示方法

```
❌ 「新しい戦略を作成してください」
❌ 「バックテストを実行してください」
❌ ファイル名なしの抽象的な指示
```

---

## 🎯 3つの戦略 - 一覧表

| # | 戦略名 | EV | WR | 月間回数 | 難易度 | 推奨開始時期 |
|----|--------|-----|-----|---------|--------|-----------|
| 🏆 | **Robinhood Premium** | +1.42% | 80% | 3-5回 | 高 | Phase 3 |
| 🥈 | **全取引所 12h SHORT** | +0.127% IS / +0.100% OOS | 53% | ~10回 | 中 | Phase 2 |
| 🥉 | **gate.io 48h SHORT** | +0.040% IS / +0.153% OOS | 50% | 20+回 | 低 | Phase 1 |

---

## 📁 ファイル構成と役割

```
trade/
├── memory/
│   ├── NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md ⭐ START HERE
│   ├── whale_inflow_short_strategy_research.md (詳細)
│   └── MEMORY.md (インデックス)
│
├── WHALE_INFLOW_STRATEGY_README.md (このファイル)
│
├── data/
│   ├── btc_inflow_strategy_pro_backtest.py (実装スクリプト)
│   ├── btc_inflow_backtest.py (基本バックテスト)
│   ├── btc_inflow_oos_validation.py (OOS検証)
│   ├── btc_full_backtest.py (全740イベント検証)
│   │
│   ├── btc_inflow_backtest_results.json (473ポイント結果)
│   ├── btc_inflow_events.json (流入イベント記録)
│   └── btc_top100_whale_wallets.json (監視対象ウォレット)
│
└── SYSTEM/
    ├── qwen_unified_live.py (メインボット - 統合予定)
    ├── whale_monitor.py (既存クジラ監視)
    └── (新規戦略スクリプト - Phase 2で作成)
```

---

## 🚀 実装フェーズ別ガイド

### Phase 1: 戦略理解（今ここ）

**必読ファイル**:
- `memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md` (20-30分)

**確認項目**:
- [ ] 3戦略の違いを理解した
- [ ] EV と WR の意味を理解した
- [ ] OOS検証の重要性を理解した

---

### Phase 2: 技術検証（1-2週間）

**実行コマンド**:
```bash
# バックテスト再実行（2026-04のデータで）
python data/btc_inflow_strategy_pro_backtest.py

# OOS検証（最新データ含める）
python data/btc_inflow_oos_validation.py

# データ品質確認
python data/btc_inflow_reproducibility_study.py
```

**確認項目**:
- [ ] 過去の検証結果が2026-05でも再現されるか
- [ ] データソース（Whale Alert API）が利用可能か
- [ ] リアルタイム流入検知の遅延を測定

**担当**: LLM + ユーザー（API設定）

---

### Phase 3: システム統合（2-4週間）

**実装対象**:
```
SYSTEM/whale_inflow_live.py (新規作成)
├── WhaleInflowMonitor クラス
│   ├── リアルタイム流入検知
│   ├── RSI/ATR計算
│   └── シグナル生成
├── WhaleInflowTrader クラス
│   ├── ポジション管理
│   ├── リスク管理
│   └── ログ記録
└── メイン実行ループ
```

**統合先**: `SYSTEM/qwen_unified_live.py`

**確認項目**:
- [ ] ペーパートレードで月3-5回のシグナル発生確認
- [ ] リスク管理が機能しているか
- [ ] ログが正しく記録されるか

**担当**: LLM（実装）+ ユーザー（テスト）

---

### Phase 4: ライブ実行（慎重に）

**前提条件**:
- [ ] 口座資金: 最低 $1,000 推奨（$190では利益消失リスク）
- [ ] ペーパートレード: 2-4週間完了
- [ ] IS/OOS検証: 2026-05でも保持確認

**実行手順**:
1. 小ポジション（口座の1-2%）で開始
2. 30日間のトレード履歴記録
3. 実績 EV が理論値に近いか評価
4. 段階的にポジションサイズ拡大

---

## 💡 次のLLMセッションでの指示テンプレート

### テンプレート A: バックテスト確認

```
Whale Inflow Short戦略について、以下を確認してください：

【参考資料】
- memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md
- data/btc_inflow_strategy_pro_backtest.py

【確認項目】
1. 現在のバックテスト結果は有効か？
   （2026-04検証 vs 2026-05現在）
2. OOS検証（EV +0.100%）は信頼できるか？
3. 手数料 0.07% を考慮した実質EV は？
4. サンプルサイズ（414 IS / 301 OOS）は十分か？

【期待される回答形式】
- 評価結果（PASS/FAIL/条件付きPASS）
- 理由（統計的信頼度、市場環境変化等）
- リスク（懸念事項）
```

### テンプレート B: 実装設計確認

```
【参考資料】
- memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md (セクション: 実装ロードマップ)
- data/btc_inflow_strategy_pro_backtest.py (ロジック参考)

【確認項目】
1. Phase 2-3 の実装設計を提案してください
2. どのファイルを新規作成する必要があるか
3. qwen_unified_live.py との統合ポイントは？
4. リスク管理パラメータの推奨値は？

【期待される回答形式】
- 実装フロー図
- ファイル一覧（新規/修正）
- コード骨組み（クラス設計）
- テストケース
```

### テンプレート C: 戦略選択支援

```
【参考資料】
- memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md (セクション: 詳細仕様)

【確認項目】
1. 現在の$190口座では、3戦略のどれが最適か？
2. Robinhood Premium（EV +1.42%）は実装可能か？
   - API制限、月3-5回の運用性
3. 全取引所 12h（OOS検証済み）から開始すべきか？
4. 段階的な戦略展開順序の提案

【期待される回答形式】
- 推奨戦略（Phase 1-3別）
- 理由（EV、運用性、口座資金等）
- 段階的実装スケジュール
```

---

## ⚠️ よくある質問（FAQ）

### Q1: EV +0.127% は小さくないか？

**A**: 月10回のトレードで年間 EV +1.5% 程度。手数料を考慮すると利益は薄い。
ただし過度な期待なし、OOS検証で過学習なし（信頼できる）。

### Q2: 現在の$190口座で開始可能か？

**A**: 理論上は可能。ただし：
- 最小ポジション：手数料を考慮すると $1,000 以上推奨
- $190では利益がほぼ手数料に消失する可能性

**対策**: 口座スケーリング後、Phase 2 から開始推奨

### Q3: Robinhood Premium の EV +1.42% は本当か？

**A**: 統計的には信頼度：中
- サンプルサイズ：55イベント/6年 = 月1回未満
- OOS検証：N/A（データ不足）
- リアルタイム検知：難難度高（Whale Alert API有料）

### Q4: リアルタイムで流入を検知できるか？

**A**: 2つの課題あり：
1. Whale Alert Free版 = 10M USD以上のみ（多くの中流入は検知不可）
2. mempool.space API の遅延（1-5分）→ エントリー後ズレ

**対策**: CryptoQuant API（有料 $49/月）の検討

---

## 📞 技術サポート

### LLMセッションで詳しく知りたい場合

```bash
# ファイルの所在を確認
find trade/ -name "*inflow*" -o -name "*whale*"

# メモリインデックスを確認
cat trade/memory/MEMORY.md

# 最新の戦略ガイドを確認
cat trade/memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md
```

### 実装時に参考になるファイル

- **バックテスト結果**: `data/btc_inflow_backtest_results.json`
- **イベントデータ**: `data/btc_inflow_events.json`
- **価格データ**: `data/btc_price_4h_cache.csv`
- **ウォレット監視リスト**: `data/btc_top100_whale_wallets.json`

---

## ✅ チェックリスト：実装開始前に確認

- [ ] `memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md` を読了
- [ ] 3戦略の違い（EV、WR、月間取引回数）を理解
- [ ] OOS検証（過学習なし）を理解
- [ ] 手数料 0.07% の影響を認識
- [ ] Phase 1-4 の全体スケジュールを把握
- [ ] 次のLLMセッションでの質問内容を決定

---

**Last Updated**: 2026-05-05  
**Strategy Status**: ✅ Ready for Implementation
