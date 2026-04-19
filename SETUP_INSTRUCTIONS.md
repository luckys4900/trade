# Whale Strategy セットアップ - 実行手順

## ⚠️ 重要: 実際のウォレットアドレスが必要

現在 `whale_wallets.json` に含まれているのは**ダミーアドレス**です。  
本運用前に、**Hyperliquid Leaderboard から実際のトップパフォーマーのアドレスを取得**し、置き換える必要があります。

---

## セットアップ流れ

### フェーズ 1: Hyperliquid Leaderboard からウォレットを取得

**1. ブラウザで以下を開く**
```
https://app.hyperliquid.xyz/leaderboard
```

**2. 以下の条件でフィルタして TOP 6-10 ウォレットを選定**

| 条件 | 基準 |
|------|------|
| ROI | > 20% (過去90日) |
| 取引数 | > 50 |
| 勝率 | > 55% |
| 最大DD | > -30% |
| アクティブ | 過去7日に取引あり |

**3. 各ウォレットをクリックして詳細を確認**
- アドレスをコピー（例：`0xABC123...`）
- Account Value と Position count を記録

**4. 例：選定されたウォレット**
```
1. Wallet A: 0x1234567890abcdef1234567890abcdef12345678
   ROI: +45%, PnL: $120k, Trades: 85
   
2. Wallet B: 0x9876543210fedcba9876543210fedcba98765432
   ROI: +38%, PnL: $95k, Trades: 72
   
3. Wallet C: 0xabcdefabcdefabcdefabcdefabcdefabcdefabcd
   ROI: +32%, PnL: $78k, Trades: 64
   ...
```

---

### フェーズ 2: whale_wallets.json を更新

**方法 A: 対話型スクリプト（推奨）**

```bash
python fetch_leaderboard_wallets.py
```

プロンプトに従って、Leaderboard から取得したアドレスを入力します。

**出力:**
```
======================================================================
WHALE WALLET SETUP - Manual Entry
======================================================================

Wallet 1 address (or 'done' to finish): 0x1234567890abcdef1234567890abcdef12345678
  Validating 0x1234567... ✓ Account value: $450000.00, Positions: 2

Wallet 2 address (or 'done' to finish): 0x9876543210fedcba9876543210fedcba98765432
  Validating 0x9876543... ✓ Account value: $380000.00, Positions: 1

... (6 個のウォレット入力)

Confirming 6 wallets...
Proceed with update? (y/n): y

✓ Configuration updated successfully!
```

**方法 B: 手動編集**

`whale_wallets.json` を直接編集：

```json
{
  "wallets": [
    {
      "address": "0x1234567890abcdef1234567890abcdef12345678",
      "label": "Whale_1",
      "active": true,
      "notes": "ROI: +45%, from leaderboard"
    },
    {
      "address": "0x9876543210fedcba9876543210fedcba98765432",
      "label": "Whale_2",
      "active": true,
      "notes": "ROI: +38%, from leaderboard"
    },
    ...6 個まで
  ],
  ... (以下は変更不要)
}
```

---

### フェーズ 3: 設定確認

```bash
python fetch_leaderboard_wallets.py --show
```

**出力:**
```
======================================================================
CURRENT WHALE WALLET CONFIGURATION
======================================================================
Total wallets: 6

1. Whale_1
   Address: 0x1234567890abcdef1234567890abcdef12345678
   Status:  ✓ ACTIVE
   Notes:   ROI: +45%, from leaderboard

2. Whale_2
   Address: 0x9876543210fedcba9876543210fedcba98765432
   Status:  ✓ ACTIVE
   Notes:   ROI: +38%, from leaderboard

... (6個)
```

---

### フェーズ 4: 単体テスト

**Step 1: Whale Monitor テスト**
```bash
python whale_monitor.py --once
```

**期待される出力:**
```
Loaded config: 6 wallets
=== Run Once ===
Whale_1: sortino=2.15, wr=65.2%, trades=85, ev=0.0312
Whale_2: sortino=1.89, wr=62.1%, trades=72, ev=0.0198
Whale_3: sortino=1.52, wr=58.5%, trades=64, ev=0.0145
... (3-6 wallets qualified)
Signal written: LONG, strength=0.62, valid=True
```

**Step 2: Macro Filter テスト**
```bash
python macro_filter.py --once
```

**期待される出力:**
```
=== Run Once ===
Fetching BTC candles... ✓ (30 bars)
ATR ratio: 0.0287 (NORMAL regime)
Loaded 20 calendar events
Caution mode: False (no HIGH impact events in ±12h)
State written: regime=NORMAL, atr=0.0287, caution=False
```

**Step 3: ファイル確認**
```bash
ls -la whale_signal.json macro_state.json
cat whale_signal.json
cat macro_state.json
```

**期待される内容:**

`whale_signal.json`:
```json
{
  "direction": "LONG",
  "strength": 0.62,
  "wallet_count": 4,
  "n_ranked": 5,
  "avg_sortino": 1.89,
  "timestamp": 1712769479000,
  "valid": true
}
```

`macro_state.json`:
```json
{
  "regime": "NORMAL",
  "atr_ratio": 0.0287,
  "caution_mode": false,
  "next_event": "2026-04-15 14:30:00",
  "next_event_name": "US CPI YoY",
  "hours_to_event": 75.5,
  "timestamp": 1712769479000,
  "valid": true
}
```

---

### フェーズ 5: 本運用開始

#### ターミナル 1: Whale Monitor（15分毎）
```bash
python whale_monitor.py
```

#### ターミナル 2: Macro Filter（60分毎）
```bash
python macro_filter.py
```

#### ターミナル 3: メインボット（60秒毎）
```bash
python qwen_unified_live.py
```

**ログで whale_mult が表示されることを確認:**
```
grep "whale_mult" logs/unified_live_*.log
```

**期待される出力:**
```
RSISwing LONG SIGNAL @ 42123.45 (RSI=28.5) | whale_mult=1.35 | sz=0.0032→0.0043
OCPM SHORT SIGNAL @ 41987.12 | whale_mult=0.60 | sz=0.0028→0.0017
```

---

## トラブルシューティング

### Q: whale_monitor.py で全ウォレットが "qualified" ではない

**原因:**
- Sortino < 0.5
- Trade count < 10 (過去90日)

**対策:**
- 別のウォレットを試す
- Leaderboard で ROI がより高いウォレットを選定

### Q: macro_filter.py でマクロデータが取得できない

**原因:**
- ネットワーク接続問題
- Hyperliquid API 一時的に停止

**対策:**
```bash
# 再実行
python macro_filter.py --once

# API 接続を確認
python -c "import requests; print(requests.post('https://api.hyperliquid.xyz/info', json={'type': 'meta'}).status_code)"
```

### Q: whale_signal.json が生成されない

**原因:**
- ウォレットアドレスが無効
- Hyperliquid に登録されていない

**対策:**
1. Leaderboard でアドレスを再確認
2. `whale_wallets.json` を再編集
3. `python fetch_leaderboard_wallets.py --show` で確認

---

## 重要な注意事項

⚠️ **本運用前にパイロット期間を設ける**

推奨:
1. **Week 1-2**: 小ロット（0.5% risk）で動作確認
2. **Week 3-4**: whale_signal の品質を実データで検証
3. **Month 2**: trade_alignment_log.json で EV 改善を確認
4. **Month 3**: validate_whale_alpha.py で本検証

---

## 次のステップ

✅ **今すぐ実行:**
```bash
# ウォレット設定（対話型）
python fetch_leaderboard_wallets.py

# 単体テスト
python whale_monitor.py --once
python macro_filter.py --once

# ファイル確認
ls -la whale_signal.json macro_state.json
```

✅ **本運用準備完了後:**
```bash
# 3つのプロセスを並行実行
python whale_monitor.py &
python macro_filter.py &
python qwen_unified_live.py
```

---

**セットアップ完了までの目安: 15-20 分**
