# Whale Wallet Setup ガイド

## 概要

`fetch_leaderboard_wallets.py` は Hyperliquid leaderboard から実際のトップパフォーマーウォレットを取得し、`whale_wallets.json` を更新するツールです。

---

## セットアップ手順

### Step 1: Hyperliquid Leaderboard を開く

```
https://app.hyperliquid.xyz/leaderboard
```

### Step 2: トップパフォーマーを確認

以下の条件で 6-10 個のウォレットを選定してください：

| 条件 | 基準 |
|------|------|
| **ROI** | > 20% (過去90日間) |
| **取引数** | > 50 |
| **勝率** | > 55% |
| **最大ドローダウン** | < -30% |
| **アクティブ度** | 過去7日間に取引あり |

**選定例**:
```
1. Wallet A - ROI: +45%, PnL: $120k, Trades: 85
2. Wallet B - ROI: +38%, PnL: $95k, Trades: 72
3. Wallet C - ROI: +32%, PnL: $78k, Trades: 64
... (計6-8個)
```

### Step 3: セットアップスクリプト実行

```bash
cd C:\Users\user\Desktop\cursor\trade

python fetch_leaderboard_wallets.py
```

### Step 4: ウォレットアドレスを入力

対話的プロンプトが表示されます：

```
======================================================================
WHALE WALLET SETUP - Manual Entry
======================================================================

Instructions:
1. Visit: https://app.hyperliquid.xyz/leaderboard
2. Identify 6-10 top performers by ROI or PnL
3. Copy wallet addresses and paste below
4. Enter 'done' when finished

Tip: Look for wallets with:
  - ROI > 20% (past 90 days)
  - Trade count > 50
  - Consistent profitability (no extreme drawdowns)
======================================================================

Wallet 1 address (or 'done' to finish): 0xABC123...
  Validating 0xABC123... ✓ Account value: $450000.00, Positions: 2

Wallet 2 address (or 'done' to finish): 0xDEF456...
  Validating 0xDEF456... ✓ Account value: $380000.00, Positions: 1

... (続く)

Wallet 6 address (or 'done' to finish): done
```

各入力時：
- ✓ アドレスが valid (0x... 42文字)
- ✓ Hyperliquid に存在
- ✓ アカウント残高とポジション数を表示

### Step 5: 確認と更新

```
Confirming 6 wallets...
  • Whale_1: 0xABC123...
  • Whale_2: 0xDEF456...
  ...

Proceed with update? (y/n): y

✓ Configuration updated successfully!

======================================================================
CURRENT WHALE WALLET CONFIGURATION
======================================================================
Total wallets: 6

1. Whale_1
   Address: 0xABC123...
   Status:  ✓ ACTIVE
   Notes:   Manual entry from leaderboard

2. Whale_2
   Address: 0xDEF456...
   Status:  ✓ ACTIVE
   Notes:   Manual entry from leaderboard

...
```

---

## その他のコマンド

### 現在の設定を確認

```bash
python fetch_leaderboard_wallets.py --show
```

出力例：
```
======================================================================
CURRENT WHALE WALLET CONFIGURATION
======================================================================
Total wallets: 6

1. Whale_1
   Address: 0xABC123...
   Status:  ✓ ACTIVE
   Notes:   Manual entry from leaderboard
   ...
```

### 別の設定ファイルを使用

```bash
python fetch_leaderboard_wallets.py --config custom_wallets.json
```

---

## whale_wallets.json のバックアップ

スクリプト実行時に `whale_wallets.json.backup` が自動作成されます。

何か問題が発生した場合は、以下で復元できます：

```bash
copy whale_wallets.json.backup whale_wallets.json
```

---

## トラブルシューティング

### Q: ウォレットアドレスが見つからないと言われる

**原因**: アドレスが誤入力、または Hyperliquid に登録されていない  
**対策**: 
- Leaderboard から正しくコピー＆ペースト
- アドレスが `0x...` で始まり、全長 42 文字か確認
- 別のウォレットを試す

### Q: スクリプトが止まった

**原因**: ネットワーク遅延  
**対策**: 
- インターネット接続を確認
- 数秒待ってやり直す
- 別のウォレットアドレスをスキップして続行

### Q: 設定を全てリセットしたい

```bash
python fetch_leaderboard_wallets.py --show  # 現在の設定を確認
# バックアップから復元
copy whale_wallets.json.backup whale_wallets.json
```

---

## ベストプラクティス

1. **週1回更新**  
   Leaderboard ランキングは変動するため、週1回ウォレットを再評価してください。

2. **多様性を重視**  
   同じ戦略の複数ウォレットより、異なる戦略を持つウォレット群が有効。

3. **パフォーマンス検証**  
   `whale_monitor.py` で自動計算される Sortino Ratio を確認し、低パフォーマー（Sortino < 0.5）は自動で除外されます。

4. **記録保存**  
   `logs/fetch_leaderboard_*.log` に全ての実行ログが保存されます。

---

## 次のステップ

1. ✓ このスクリプトでウォレットを設定
2. `whale_monitor.py --once` を実行して動作確認
3. `macro_filter.py --once` を実行してマクロフィルター確認
4. `qwen_unified_live.py` で統合テスト

詳細は `README.md` を参照してください。
