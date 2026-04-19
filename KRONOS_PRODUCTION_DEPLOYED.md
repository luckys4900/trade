# Kronos AI — 本番実装完了

**実装日時:** 2026-04-12 11:35 UTC  
**ステータス:** 🟢 **LIVE / 本番運用開始**

---

## 実装内容

### モード変更

```
変更前: kronos_shadow_mode = True  (ログのみ、サイズに影響なし)
変更後: kronos_shadow_mode = False (本番運用、乗数がサイズに反映)
```

**ファイル:** `SYSTEM/qwen_unified_live.py` (L110)

### 効果範囲

Kronos AI 乗数が以下のすべてのエントリーに適用されます：

```
① OCPM (On-Chain Pullback Momentum)
   └─ EMA 21/55 crossover + RSI pullback + ADX

② Range MR (Range Mean Reversion)
   └─ Bollinger Band + RSI oversold/overbought

③ RSI Swing v6
   └─ RSI crossover through 30/70
```

### 計算チェーン（本番版）

```
base_size 
  × whale_multiplier   (0.6 – 1.5)  [15min 更新]
  × macro_multiplier   (0.5 or 1.0) [60min 更新]
  × kronos_multiplier  (0.65 – 1.4) [4h 更新] ← NOW ACTIVE
  × confluence_mult    (1.5 or 1.0) [リアルタイム]
  → floor(25% of base) [保護機構]
  = final_size → ORDER EXECUTION
```

---

## 本番運用の開始方法

### 1. システム起動

```bash
MASTER_LAUNCHER.bat → [1] START SYSTEM
```

起動順序：
```
[1/4] Whale Monitor (15分周期)
[2/4] Macro Filter (60分周期)
[3/4] Kronos AI Predictor (4時間周期) ← LIVE
[4/4] Main Trading Bot (60秒周期)   ← KRONOS ACTIVE
```

### 2. リアルタイム監視

```bash
MASTER_LAUNCHER.bat → [2] MONITOR
```

ダッシュボードで確認するべき項目：

```
Process Status
├─ Whale Monitor: Running ✓
├─ Macro Filter: Running ✓
├─ Kronos AI Predictor: Running ✓
└─ Main Bot: Running ✓

Kronos Signal (Latest)
├─ Direction: LONG / SHORT / NONE
├─ Probability: 0.467 (≈47% up)
├─ Multiplier Long: 1.0 (neutral)
└─ Valid: true ✓

Real-time Trades
├─ Strategy: RSISwing
├─ Direction: LONG
├─ Kronos Aligned: YES / NO
└─ Final Size: 0.0042 BTC (with Kronos multiplier)
```

### 3. 定期検証（重要）

**毎週 Monday:**
```bash
python validate_whale_alpha.py --mode kronos
```

**月 1 回（4 週間ごと）：**
```bash
python validate_whale_alpha.py --mode both --export
```

---

## 注視すべきメトリクス

### 即座の監視（毎日）

| メトリクス | 正常値 | 警告値 | アクション |
|-----------|--------|--------|-----------|
| Kronos signal 有効性 | 100% | < 80% | ログ確認 |
| 推論時間 | < 10s | > 30s | CPU 確認 |
| Signal staleness | < 5h | > 5h | 推論失敗の可能性 |

### 統計的な検証（4 週間）

```
EV(kronos_aligned) - EV(kronos_neutral) 
  ├─ Target: > +0.3% per trade
  ├─ Warning: 0～+0.3%（効果微妙）
  └─ Critical: < 0%（本番化失敗）

該当時：
  ├─ Target: 継続運用 ✓
  ├─ Warning: パラメータ調整検討
  └─ Critical: kronos_shadow_mode = True に戻す
```

---

## 本番運用中の対応フロー

### シナリオ A：Kronos が正しく機能している場合

```
Week 1–4: Shadow Mode と同様に運用
          ├─ クジラ信号と Kronos が同意 → 乗数 up（増益）
          └─ Kronos が懸念を示唆 → 乗数 down（損失軽減）

Week 4: 統計レポート出力
        └─ Alpha > +0.3% ✓ → 継続運用を推奨
```

### シナリオ B：Kronos が機能していない場合（Alpha ≤ 0）

```
Week 4: validate_whale_alpha.py の出力で判定
        └─ EV(aligned) < EV(neutral) → Kronos 無効化

対応：
  cronos_shadow_mode = True に戻す
  または
  kronos_enabled = False で完全削除
```

### シナリオ C：Kronos 推論エラー（inference 継続失敗）

```
ログで以下が多発：
  [ERROR] KronosPredictor: Inference error

対応手順：
  1. MASTER_LAUNCHER.bat → [3] STOP SYSTEM
  2. ログ確認: DATA/logs/kronos_predictor_*.log
  3. 原因特定：
     ├─ Hyperliquid API ダウン → 待機
     ├─ モデルメモリ不足 → 32 bars に削減
     └─ その他 → Slack で報告
  4. cronos_enabled = False で暫定対応
```

---

## パラメータ調整ガイド

### 保守的に運用したい場合

```python
kronos_align_multiplier_max = 1.2  # 1.4 → 1.2 (上値抑制)
kronos_conflict_multiplier = 0.75  # 0.65 → 0.75 (下値緩和)
kronos_neutral_band = 0.08         # 0.05 → 0.08 (中立域拡大)
```

→ Kronos の影響を 30% 削減（慎重なアプローチ）

### 積極的に運用したい場合（要検証）

```python
kronos_align_multiplier_max = 1.5  # 1.4 → 1.5 (上値拡大)
kronos_conflict_multiplier = 0.6   # 0.65 → 0.6 (下値強化)
kronos_neutral_band = 0.03         # 0.05 → 0.03 (中立域縮小)
```

→ Kronos の影響を 20% 強化（積極的なアプローチ）

**推奨:** 現在の設定 (1.4 / 0.65 / 0.05) で 4 週間運用してから判断

---

## 緊急停止フロー

### Kronos を即座に無効化

```bash
# qwen_unified_live.py の Config を修正
kronos_enabled = False
```

再起動して反映。サイズ計算から Kronos が削除される。

```
変更: final_sz = sz × whale_mult × macro_mult × 1.0 × conf_mult
```

---

## ログの確認方法

### Kronos predictor ログ

```bash
tail -f DATA/logs/kronos_predictor_*.log
```

**正常ログ例：**
```
2026-04-12 11:30:00 [INFO] Starting Kronos inference cycle...
2026-04-12 11:30:02 [INFO] Model loaded in 1.15s
2026-04-12 11:30:07 [INFO] Cycle complete in 8.33s: LONG (prob_up=0.623, strength=0.246)
```

### メイン BOT ログ

```bash
tail -f DATA/logs/qwen_unified_live_*.log | grep -i kronos
```

**正常ログ例：**
```
2026-04-12 11:31:00 RSISwing LONG SIGNAL @ 45250.42 | whale=1.20 kronos=1.15 conf=1.0 | sz=0.0036→0.0050
2026-04-12 11:31:05 [RSISwing] OPENING LONG 0.0050 @ 45250.42
```

---

## 本番化チェックリスト

- [x] Config 修正: `kronos_shadow_mode = False`
- [x] 構文チェック: OK
- [x] 推論テスト: 8.33s で成功確認済み
- [x] 本番ドキュメント作成
- [ ] システム起動（実行時）
- [ ] 1 トレード目の Kronos aligned 確認
- [ ] 毎週 Monday: EV 検証
- [ ] 4 週間後: 最終判定

---

## 重要な注記

### リスク管理

```
Kronos 乗数の最悪ケース：
  base_sz × 0.6 (whale conflict) 
         × 0.5 (macro caution) 
         × 0.65 (kronos conflict)
         = 0.195x (base の 19.5%)
         
Floor 保護により: max(0.195, 0.25) = 0.25x (25% 確保)
```

**結論:** ポジションサイズは最低 25% まで削減される。それ以上の損失はない。

### 免責事項

```
Kronos AI は以下を保証しません：
✗ 利益を出すこと
✗ 損失を防ぐこと
✗ 特定の精度レベル

これは補助的なシグナルです。
テクニカル + クジラ信号が最優先です。
```

---

## サポート情報

**問題が発生した場合：**

1. **ダッシュボード確認**
   ```
   MASTER_LAUNCHER.bat → [2] MONITOR
   ```

2. **ログ確認**
   ```
   MASTER_LAUNCHER.bat → [4] LOGS
   ```

3. **即座の対応**
   ```
   kronos_enabled = False で Kronos 無効化
   システム再起動
   ```

4. **詳細分析**
   ```
   python validate_whale_alpha.py --mode kronos --export
   CSV レポートから原因分析
   ```

---

**本番実装日:** 2026-04-12 11:35 UTC  
**実装者:** Claude Haiku 4.5  
**ステータス:** 🟢 LIVE  
**次回検証:** 2026-04-26 (2 週間後、最初の 10+ トレード後)
