---
name: Whale Inflow Short Strategy - New Trading Logic (2026-05-02)
description: Complete BTC whale inflow short strategy with EV validation, IS/OOS testing, and 3 implementation-ready variants
type: project
---

# Whale Inflow Short Strategy - 新規売買ロジック完全ガイド
**Created**: 2026-05-02 (バックテスト検証完了)  
**Status**: ✅ IS/OOS検証済み・実装可能  
**Expected Value**: +0.10% ～ +1.48%（戦略による）

---

## 📌 クイックリファレンス

### 実装優先度別・3つの戦略

| 優先度 | 戦略名 | エントリー条件 | ホライズン | IS EV | OOS EV | WR | 運用性 |
|--------|--------|--------------|-----------|-------|--------|-----|--------|
| 🏆 1位 | **Robinhood Premium** | Robinhoodコールド流入 50+ BTC + RSI > 50 | 短期 | +1.42% | N/A | 80% | 月3-5回 |
| 🥈 2位 | **全取引所 12h SHORT** | 全取引所への50+ BTC流入 | 12h | +0.127% | +0.100% ✅ | 53% | 月10回 |
| 🥉 3位 | **gate.io 48h SHORT** | gate.io流入 50-1000 BTC | 48h | +0.040% | +0.153% ✅ | 50% | 月20回以上 |

---

## 📊 詳細仕様

### 戦略1: Robinhood Premium（最高EV）

**目的**: Robinhood（個人投資家向け取引所）への大口流入 = 売却目的のシグナル

**エントリー条件**（すべて必須）:
```
1. Robinhoodコールドウォレット宛に50+ BTC流入
2. 流入時刻のRSI(14) > 50（中立以上）
3. （オプション）価格が下向き（DOWN flag）
```

**パフォーマンス**:
- IS: EV +1.42%, WR 80% (55イベント)
- オプション条件付き: EV +1.48%, WR 100%
- 期間: 2020-2026年の限定的イベント

**運用上の注意**:
- ⚠️ **月3-5回程度のトレード機会のみ**
- リアルタイムWhaleAlert APIが必須
- サンプルサイズ限定（55件/6年）

**参考ファイル**: 
- `memory/whale_inflow_short_strategy_research.md` (セクション12: Deep Factor Analysis)

---

### 戦略2: 全取引所 12h SHORT（最も安定）

**目的**: すべての大口取引所への50+ BTC流入を一律のショートシグナルとして使用

**エントリー条件**（シンプル）:
```
1. 任意の取引所（Binance, OKEx, gate.io等）への50+ BTC外部流入
2. 流入検知から即エントリー
3. 12時間ポジション保有
```

**パフォーマンス**:
- IS: EV +0.127%, WR 53% (414イベント)
- OOS: EV +0.100%, WR 53% (301イベント) ✅ **OOS検証PASS**
- 期間: 2020-02～2026-04

**運用上の強み**:
- ✅ OOS検証で過学習なし（IS と OOS がほぼ同じEV）
- ✅ 月約10回のトレード機会（運用可能）
- ✅ ロジックが単純（取引所別フィルター不要）
- ✅ 事後分析に740件の実績データ

**手数料に対する耐性**:
- EV +0.10% に対して手数料 0.07%（往復0.035%×2）
- 利益ほぼ消失のリスク（要資本スケーリング）

**参考ファイル**:
- `memory/whale_inflow_short_strategy_research.md` (セクション10: フルバックテスト結果)

---

### 戦略3: gate.io 48h SHORT（OOS最強）

**目的**: gate.io（大量で規則的な流入がある取引所）への50-1000 BTC流入を特化分析

**エントリー条件**:
```
1. gate.io コールドウォレット宛に50-1000 BTC流入
2. 48時間ポジション保有
```

**パフォーマンス**:
- IS: EV +0.040%, WR ≈50% (299イベント)
- OOS: EV +0.153%, WR ≈50% (250イベント) ✅ **OOS検証PASS（IS超過）**
- 期間: 2020-02～2026-04

**注目点**:
- 🚀 **珍しく OOS で IS を上回るEV**（過度なIS最適化の逆証）
- 毎日130-150 BTCの規則的流入（ノイズの可能性）
- 550件の豊富なデータセット

**参考ファイル**:
- `memory/whale_inflow_short_strategy_research.md` (セクション10: 取引所別結果)

---

## 🔬 詳細Factor Analysis（ボーナス知識）

### 12h Horizonでの各要素の EV寄与度

| 要素 | 条件 | WR | EV | 活用方法 |
|------|------|-----|-----|---------|
| RSI帯域 | 40-50 | 57% | +0.36% | 中立～弱気 |
| RSI帯域 | 70-100 | 52% | +0.44% | 過熱時も機会 |
| セッション | US Session（08:00-16:00 UTC） | 62% | +0.48% | 米国営業時間帯 |
| ボラティリティ | ATR 1.5-2.5% | 59% | +0.44% | 中程度ボラ |
| **流入規模** | **500-1000 BTC** | **62%** | **+1.45%** | ⭐ 強シグナル |
| **連続流入** | **3+回/24h** | **58%** | **+0.45%** | ⭐ 複合シグナル |

**実装への示唆**:
- 単純なEV +0.10%より、条件を厳選（500+ BTC、連続流入、US Session）で EV +0.45%へ向上
- ただしトレード機会が減少（月10→月3程度）

**参考ファイル**:
- `memory/whale_inflow_short_strategy_research.md` (セクション12: Deep Factor Analysis)

---

## 📁 関連ファイル一覧

### バックテストスクリプト
| ファイル | 用途 |
|---------|------|
| `data/btc_inflow_monitor.py` | リアルタイムWhale流入監視 |
| `data/btc_inflow_backtest.py` | 基本的なバックテスト実装 |
| `data/btc_inflow_strategy_pro_backtest.py` | Pro版（複数条件・ファクター分析） |
| `data/btc_inflow_oos_validation.py` | OOS検証スクリプト |
| `data/btc_full_backtest.py` | 全740イベント検証 |
| `data/btc_inflow_reproducibility_study.py` | 再現性研究 |
| `data/btc_inflow_evidence_strategy_report.py` | 戦略レポート生成 |

### データファイル
| ファイル | 内容 | サイズ |
|---------|------|--------|
| `data/btc_inflow_backtest_results.json` | 473ポイント詳細結果 | 147.9 KB |
| `data/btc_inflow_events.json` | 255イベント（初回監視） | 3.1 KB |
| `data/btc_inflow_seen_txs.json` | トランザクション処理済みキャッシュ | 82.5 KB |
| `data/btc_top100_whale_wallets.json` | 100ウォレットDB | - |
| `data/btc_price_4h_cache.csv` | BTC 4h OHLCV (7200本) | - |

### メモリ・ドキュメント
| ファイル | 内容 |
|---------|------|
| `memory/whale_inflow_short_strategy_research.md` | 詳細研究（セクション1-12） |
| `memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md` | **このファイル** |

---

## ⚙️ 実装ロードマップ

### Phase 1: 検証（1-2週間）
- [ ] `data/btc_inflow_strategy_pro_backtest.py` を現在の市場データで再実行
- [ ] OOS検証が2026-04から現在まで保持されているか確認
- [ ] ライブWhaleAlert APIでリアルタイム流入検知の動作確認

### Phase 2: 統合（2-4週間）
- [ ] SYSTEM/ フォルダに新規戦略スクリプト作成
- [ ] whale_monitor.py を拡張または新規スクリプト化
- [ ] qwen_unified_live.py への統合（ポジションサイズ、リスク管理）

### Phase 3: ペーパートレード（1-4週間）
- [ ] `qwen_unified_live.py` でペーパー実行
- [ ] 月3-5回（Robinhood）or 月10回（全取引所）のシグナル発生を確認
- [ ] 手数料を考慮した実損益シミュレーション

### Phase 4: ライブ取引（慎重に）
- [ ] 小ポジション（$1,000未満）で開始
- [ ] EV +0.10%は理論値で、実際のスリッページ・手数料を観察
- [ ] 30日間のライブ出来高確認後に判定

---

## ⚠️ 重要な懸念事項

### 1. 手数料の影響
```
期待値: +0.10% ～ +1.42%
取引手数料: 0.035% (Taker) × 2往路 = 0.07%
実質利益: EV - 手数料 = 薄利（口座スケールが重要）
```
**対策**: 最低$10,000口座から開始推奨

### 2. サンプルサイズの限定性
- Robinhood Premium: 55イベント/6年 = 月1回未満
- 統計的信頼度が低い可能性

### 3. リアルタイム検知の遅延
- Whale Alert Free版は10M USD以上のみ
- mempool.space API には遅延あり
- エントリータイミングが後ズレする可能性

### 4. 市場変動への適応
- バックテスト対象: 2020-2026年（強気～弱気の両相場）
- 現在のボラティリティ環境で EV が保証されない

---

## 🎓 LLMへの指示テンプレート

**次回のLLMセッションで新規戦略を理解させたい場合**:

```
# 指示用テンプレート

以下のファイルを確認して、Whale Inflow Short戦略の現況を報告してください：

1. メモリ：
   - memory/NEW_STRATEGY_WHALE_INFLOW_SHORT_2026-05-02.md
   - memory/whale_inflow_short_strategy_research.md (セクション10, 12)

2. 実装ファイル：
   - data/btc_inflow_strategy_pro_backtest.py
   - data/btc_inflow_oos_validation.py

3. バックテスト結果：
   - data/btc_inflow_backtest_results.json
   - IS/OOS検証結果の確認

質問例：
- Robinhood Premium戦略のEV +1.42% は現在も有効か？
- 全取引所 12h SHORT の OOS検証（EV +0.100%）は信頼できるか？
- 実装時の優先順位は？
- 現在の口座資金$190で開始可能か？
```

---

## ✅ チェックリスト：このドキュメント読了時

- [ ] 3つの戦略の違いを理解した
- [ ] Robinhood Premium が最高EV（+1.42%）だが月3-5回のみ
- [ ] 全取引所 12h SHORT が OOS検証済み（最も信頼できる）
- [ ] gate.io 48h SHORT は OOS で IS を上回っている（珍しい）
- [ ] 手数料 0.07% が利益を圧迫することを認識した
- [ ] 関連ファイル一覧を把握した
- [ ] Phase 1-4 の実装ロードマップを理解した

---

**更新日**: 2026-05-05  
**LLM向けマスターガイド**: ✅ 完成
