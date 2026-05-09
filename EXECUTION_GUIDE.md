# FR Z-Score Mean Reversion 改善プログラム - 実行ガイド

**最終更新**: 2026-05-08

---

## 概要

FR Z-Score Mean Reversion戦略の包括的な改善プログラムを完了しました。
以下のファイル群で、問題の特定から改善案の実装まで一連の分析が可能です。

---

## ファイル構成

### 1. 初期フレームワーク実装
**ファイル**: `fr_zscore_ultimate_v3.py`
**目的**: マルチタイムフレーム確認と複合スコアリングの実装
**実行時間**: 約5分
**出力**: 
- 複数のσ閾値(2.5σ, 3.0σ, 3.5σ)でのOOS性能
- MTFスコアリング結果

```bash
python3 /Users/user/Desktop/trade/fr_zscore_ultimate_v3.py
```

---

### 2. 詳細な統計分析
**ファイル**: `fr_zscore_improved_final.py`
**目的**: EMA vs Raw Z-scoreの効果測定 + 統計検定
**実行時間**: 約3分
**出力**:
- ノイズフィルタリング効果 (p-value)
- IS vs OOS 性能比較表
- 統計有意性判定

```bash
python3 /Users/user/Desktop/trade/fr_zscore_improved_final.py
```

**重要な結果**:
```
EMA_2.5 (最良構成):
  OOS EV: -0.15957%
  p-value: 0.000042 ✓ (有意)
  
解釈: 統計的に有意な負の収益
      = 戦略は破綻している確認
```

---

### 3. 根本原因分析 ⭐ 最重要
**ファイル**: `fr_zscore_diagnosis.py`
**目的**: なぜ戦略が失敗したのかの根本分析
**実行時間**: 約2分
**出力**:
- IS vs OOS の市場レジーム比較
- Mean Reversion効果の低下量計測
- 取引コス分析

```bash
python3 /Users/user/Desktop/trade/fr_zscore_diagnosis.py
```

**最重要な発見**:
```
Mean Reversion効果:
  IS期間 (LONG信号後6h): +0.3395%
  OOS期間 (LONG信号後6h): +0.0020%
  → 99.4%低下 ← 戦略が機能しない理由
```

---

### 4. 改善案の検証
**ファイル**: `fr_zscore_remediation.py`
**目的**: 提案した改善の効果測定
**実行時間**: 約10分
**出力**:
- ベースライン vs HC Filter vs HC+Regime の比較
- 各種構成のOOS性能

```bash
python3 /Users/user/Desktop/trade/fr_zscore_remediation.py
```

**改善効果**:
```
ベースライン:
  OOS EV: -0.20846% (n=265)

HC Filter (RSI+MACD):
  OOS EV: -0.08762% (n=123)  ← 改善
  改善率: 55%
```

---

### 5. 最終報告書
**ファイル**: `STRATEGY_IMPROVEMENT_REPORT.md`
**形式**: Markdown (ブラウザで表示可能)
**内容**:
- 全体のサマリー
- 根本原因の詳細説明
- 改善案の設計思想
- 統計検定の解釈
- 次のステップの推奨

**読むべき順序**:
1. エグゼクティブサマリー
2. 根本原因分析 (3層)
3. 改善案とその効果
4. 最終推奨

---

### 6. 要約版
**ファイル**: `IMPROVEMENT_SUMMARY.txt`
**形式**: Plain Text (ターミナルでも読みやすい)
**特徴**:
- 簡潔な要点のみ
- すぐに状況を把握できる
- 管理層向け

```bash
cat /Users/user/Desktop/trade/IMPROVEMENT_SUMMARY.txt
```

---

## 実行フロー（推奨順序）

### パターンA: 全て確認したい (1時間)
```bash
# 1. 診断（最重要）
python3 /Users/user/Desktop/trade/fr_zscore_diagnosis.py

# 2. 改善案の検証
python3 /Users/user/Desktop/trade/fr_zscore_remediation.py

# 3. 詳細な統計分析
python3 /Users/user/Desktop/trade/fr_zscore_improved_final.py

# 4. レポート確認
cat /Users/user/Desktop/trade/IMPROVEMENT_SUMMARY.txt
less /Users/user/Desktop/trade/STRATEGY_IMPROVEMENT_REPORT.md
```

### パターンB: 要点のみ確認 (10分)
```bash
# 1. 根本原因確認
python3 /Users/user/Desktop/trade/fr_zscore_diagnosis.py

# 2. サマリー読む
cat /Users/user/Desktop/trade/IMPROVEMENT_SUMMARY.txt
```

### パターンC: リーダー向け (2分)
```bash
# 要約版のみ確認
cat /Users/user/Desktop/trade/IMPROVEMENT_SUMMARY.txt
```

---

## キー指標の解釈ガイド

### EV (Expected Value / 期待値)
```
EV = 平均的な1トレードあたりの利益

OOS EV > 0.1%:    ✓ 良好
OOS EV 0～0.1%:   △ 要監視
OOS EV < 0%:      ✗ 損失

現在: -0.160% ← 問題
```

### p-value (統計有意性)
```
p < 0.05:   ✓ 統計的に有意
p >= 0.05:  ✗ 偶然の可能性

注意: p < 0.05 でも EV が負なら、戦略は失敗
      「有意な損失」は「損失」と同じ
```

### Mean Reversion効果
```
+0.34% (IS): ✓ 強い MR効果あり
+0.002% (OOS): ✗ MR効果ほぼゼロ

99.4%の低下 = 市場環境が根本的に変化
```

### Win Rate
```
> 55%:  ✓ 良好
50-55%: △ 標準的
< 50%:  ✗ 負の期待値が大きい

現在: 39.9% ← トレードの半分以上が負
```

---

## 判定フローチャート

```
                IS EV > 0?
                   |
        yes--------+---------no
        |                    |
       ✓                 戦略は IS で赤字
        |                (基本的に失敗)
        |
      OOS EV > 0?
        |
    yes-+-no
    |   |
    |   ✗ (現在ここ)
    |   | 戦略は機能していない
    |   | → 放棄推奨
    |   |
    |   p < 0.05?
    |   |
    |   yes--no
    |   |  |
    |   |  統計的に有意でない
    |   |  (偶然の可能性)
    |   |  → さらに改善が必要
    |   |
    |   p < 0.05?
    |   |
    |   yes
    |   |
    |   統計的に有意な損失を確認
    |   → 戦略は明らかに破綻
    |   → 確実に放棄すべき
    |
    p < 0.05?
    |
    yes--no
    |   |
    ✓   統計的には
    |   偶然の可能性
    |   → 実運用前に
    |     さらに多くの
    |     データが必要
    |
    ✓ 導入可能
      (監視条件付き)
```

---

## 各スクリプトの詳細オプション

### fr_zscore_diagnosis.py
直接的に実行可能。設定変更なし。

```python
# 内部で以下を分析：
IS_START = pd.Timestamp('2024-04-12')
IS_END   = pd.Timestamp('2025-03-31 23:59:59')
OOS_START = pd.Timestamp('2025-04-01')
OOS_END   = pd.Timestamp('2026-03-02 23:59:59')
```

### fr_zscore_remediation.py
改善案のパラメータを調整可能：

```python
SIGMA_THRESHOLD = 3.5  # 変更可: 2.5, 3.0, 3.5, 4.0
TP_MULT = 8            # 変更可: 5, 6, 7, 8, 10
MIN_RSI_STRENGTH = 0.4 # 変更可: 0.3, 0.5, 0.6
MIN_MR_EFFECT = 0.0005 # 変更可: 0.0001, 0.0002, 0.0010
```

---

## トラブルシューティング

### エラー1: CSV ファイルが見つからない
```
FileNotFoundError: data/btc_funding_rate.csv
```
**解決**: スクリプトの実行ディレクトリが `/Users/user/Desktop/trade` であることを確認
```bash
cd /Users/user/Desktop/trade
python3 fr_zscore_diagnosis.py
```

### エラー2: メモリ不足 (large dataset)
```
MemoryError
```
**解決**: より短い期間でテスト
```python
IS_START = pd.Timestamp('2024-12-01')  # 短期間に変更
```

### エラー3: Z-score が NaN/Inf になっている
```
Z-score range: [-inf, inf]
```
**原因**: 初期の DEFAULT_LOOKBACK (90) より少ないデータ
**解決**: `DEFAULT_LOOKBACK = 40` に小さくする

---

## 今後の改善方向

### 短期 (1-2週間)
- [ ] Trend-Following 戦略の開発開始
- [ ] 過去のFRデータ (2022-2023) でテスト
- [ ] マルチ資産への拡張検討

### 中期 (1ヶ月)
- [ ] 新しい代替戦略の IS/OOS 検証
- [ ] 統計的有意性が達成できる戦略の特定
- [ ] Paper trading による実検証

### 長期 (3ヶ月)
- [ ] 複合戦略 (複数のアルファ源の組み合わせ)
- [ ] High-Frequency アルゴリズムの研究
- [ ] Risk Parity ポートフォリオの構築

---

## 参考資料

### 統計用語の説明

**t-statistic** (t統計量)
```
サンプルの平均が理論値からどれだけ離れているかを示す
t = 0 に近い → 理論値に近い (有意でない)
t が大きい (正か負) → 理論値から遠い (有意)
```

**p-value**
```
帰無仮説が真である確率
p < 0.05 → 95%以上の信頼度で「有意」と判定
p >= 0.05 → 「偶然の可能性がある」
```

**Sharpe Ratio**
```
(平均リターン - 無リスク資産) / ボラティリティ

> 0.5: ✓ 良好
0-0.5: △ 標準的
< 0: ✗ 負の期待値
```

---

## ファイル配置図

```
/Users/user/Desktop/trade/
├── fr_zscore_ultimate_v3.py          (1. フレームワーク実装)
├── fr_zscore_improved_final.py        (2. 統計分析)
├── fr_zscore_diagnosis.py             (3. 根本原因 ⭐)
├── fr_zscore_remediation.py           (4. 改善案検証)
│
├── STRATEGY_IMPROVEMENT_REPORT.md     (5. 詳細報告書)
├── IMPROVEMENT_SUMMARY.txt            (6. 要約版)
├── EXECUTION_GUIDE.md                 (このファイル)
│
├── data/
│   └── btc_funding_rate.csv
├── btc_usdt_1h_kronos.csv
└── btc_usdt_4h.csv
```

---

## まとめ

### 最終判定: 🔴 REJECT

**戦略評価**:
- OOS EV: -0.160% ✗
- p-value: < 0.05 ✓ (ただし負)
- Win Rate: 39.9% ✗
- Sharpe: -0.17 ✗

**推奨**: 戦略を放棄し、代替案へシフト

### 根本原因
- Mean Reversion効果の消滅 (99.4%低下)
- 市場環境の恒久的変化

### 改善の可能性
- 低い (構造的問題のため)
- パラメータ最適化では対応不可
- より根本的な戦略設計の変更が必要

---

**作成日**: 2026-05-08  
**分析者**: Claude Code (Haiku 4.5)

---
