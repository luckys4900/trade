# TP・SL実装の深掘り分析
## hl_rsi_swing_v6.py の詳細検証

**作成日:** 2026-04-03  
**調査対象:** TP・SLが実際に設定・実行されているのか  
**検査レベル:** コード静的分析

---

## 概要

**結論：TP・SLは「計算・保存」されていますが、「実際の注文」には含まれていません。**

実装は**ソフトウェア的なストップロス（Manual Monitoring）**です。

---

## 目次

1. [TP・SL設定の流れ](#tpsl設定の流れ)
2. [Hyperliquid注文送信時の問題](#hyperliquid注文送信時の問題)
3. [実装の問題点](#実装の問題点)
4. [リスク評価](#リスク評価)

---

## TP・SL設定の流れ

### Phase 1: config.jsonからパラメータ読み込み

**ファイル: config.json**
```json
{
  "sl_atr": 1.5,        // ✅ 設定済み
  "tp_atr": 3.0,        // ✅ 設定済み
  "rsi_period": 14,
  "equity_usd": 199.12,
  "risk_pct": 0.02,
  "max_bars": 20
}
```

**ファイル: hl_rsi_swing_v6.py, 行157-158**
```python
self.sl_atr = float(config.get("sl_atr", 1.5))        # ✅ 読み込み
self.tp_atr = float(config.get("tp_atr", 3.0))        # ✅ 読み込み
```

**評価:** ✅ 完全実装

---

### Phase 2: エントリー時にTP・SL計算

**ファイル: hl_rsi_swing_v6.py, _open_position()メソッド, 行484-491**

```python
def _open_position(self, side: str, price: float, atr_now: float, bar_time: int) -> None:
    # ========== TP・SL距離を計算 ==========
    sl_dist = atr_now * self.sl_atr        # ✅ ATR × 1.5
    tp_dist = atr_now * self.tp_atr        # ✅ ATR × 3.0
    
    # ========== ポジションサイズを計算 ==========
    qty = (self.equity * self.risk_pct) / sl_dist if sl_dist > 0 else 0.0
    
    # ========== LONG エントリー ==========
    if side == "long":
        self.sl_price = price - sl_dist     # ✅ SL価格 = 現在価格 - SL距離
        self.tp_price = price + tp_dist     # ✅ TP価格 = 現在価格 + TP距離
        
        # ✅ ログ出力（TP・SL表示）
        logger.info(
            "OPEN LONG @ %.2f | SL=%.2f TP=%.2f qty_est=%.6f "
            "(SL=%.1fxATR, TP=%.1fxATR)",
            price, self.sl_price, self.tp_price, qty,
            self.sl_atr, self.tp_atr
        )
        
        # ⚠️ 注文送信
        self._place_live_order(True, qty, price, False)
```

**計算例（假想）:**
```
現在価格: $42,500
ATR(14): $800

SL・TP計算:
  sl_dist = 800 × 1.5 = $1,200
  tp_dist = 800 × 3.0 = $2,400
  
SL・TP価格:
  SL = 42,500 - 1,200 = $41,300  ✅ 設定済み
  TP = 42,500 + 2,400 = $44,900  ✅ 設定済み
  
ポジション:
  self.sl_price = 41300.0   ✅ メモリに保存
  self.tp_price = 44900.0   ✅ メモリに保存
```

**評価:** ✅ TP・SL価格は正確に計算される

---

### Phase 3: 注文をHyperliquidに送信

**ファイル: hl_rsi_swing_v6.py, _place_live_order()メソッド, 行323-346**

```python
def _place_live_order(self, side_long: bool, qty: float, price: float, reduce_only: bool) -> None:
    if not (self.live_trading and self.exchange is not None):
        return
    try:
        order_type = {"market": {}}          # マーケット注文
        
        logger.info(
            "[LIVE] Placing %s order: coin=%s qty=%.6f price=%.2f reduce_only=%s",
            "BUY" if side_long else "SELL",
            self.symbol,
            qty,
            price,
            reduce_only,
        )
        
        # ⚠️⚠️⚠️ 注文送信 ⚠️⚠️⚠️
        resp = self.exchange.order(
            self.symbol,           # "BTC"
            side_long,             # True (LONG) or False (SHORT)
            float(qty),            # ポジションサイズ
            float(price),          # エントリー価格
            order_type,            # {"market": {}}
            reduce_only=reduce_only,  # False (エントリー時)
        )
        
        logger.info("[LIVE] Order response: %s", resp)
    except Exception as e:
        logger.error("[LIVE] Order failed: %s", e)
```

**問題点:**

❌ **TP・SLパラメータが注文に含まれていない！**

```python
# 実際に送信される注文パラメータ:
{
    "coin": "BTC",
    "side": "long/short",
    "quantity": 0.001234,
    "price": 42500.0,
    "orderType": "market",
    "reduceOnly": false
    
    # ❌ これらがない:
    # "tp": 44900.0,        ← TP設定なし
    # "sl": 41300.0,        ← SL設定なし
    # "tpTriggerPx": 44900, ← トリガーオーダーなし
    # "slTriggerPx": 41300, ← トリガーオーダーなし
}
```

**評価:** ❌ TP・SLはHyperliquidの注文に含まれない

---

### Phase 4: TP・SL・タイムストップの監視と実行

**ファイル: hl_rsi_swing_v6.py, run()メソッド, 行414-440**

```python
# ========== ポジション持ちながら、毎ループで価格チェック ==========
if self.position_side == "long":
    # ========== SLチェック ==========
    if self.sl_price is not None and price <= self.sl_price:
        logger.info("LONG SL hit: price=%.2f <= SL=%.2f", price, self.sl_price)
        # ⚠️ ボットが手動で決済注文を送信
        self._place_live_order(False, qty, price, True)
        self._close_position(price)
    
    # ========== TPチェック ==========
    elif self.tp_price is not None and price >= self.tp_price:
        logger.info("LONG TP hit: price=%.2f >= TP=%.2f", price, self.tp_price)
        # ⚠️ ボットが手動で決済注文を送信
        self._place_live_order(False, qty, price, True)
        self._close_position(price)
    
    # ========== タイムストップ ==========
    elif bars_held >= self.max_bars:  # max_bars = 20
        logger.info("LONG time stop reached (%d bars).", bars_held)
        # ⚠️ ボットが手動で決済注文を送信
        self._place_live_order(False, qty, price, True)
        self._close_position(price)

elif self.position_side == "short":
    # ========== SLチェック ==========
    if self.sl_price is not None and price >= self.sl_price:
        logger.info("SHORT SL hit: price=%.2f >= SL=%.2f", price, self.sl_price)
        self._place_live_order(True, qty, price, True)
        self._close_position(price, short=True)
    
    # ========== TPチェック ==========
    elif self.tp_price is not None and price <= self.tp_price:
        logger.info("SHORT TP hit: price=%.2f <= TP=%.2f", price, self.tp_price)
        self._place_live_order(True, qty, price, True)
        self._close_position(price, short=True)
    
    # ========== タイムストップ ==========
    elif bars_held >= self.max_bars:
        logger.info("SHORT time stop reached (%d bars).", bars_held)
        self._place_live_order(True, qty, price, True)
        self._close_position(price, short=True)
```

**監視ロジック:**
```
毎 check_interval 秒ごと（デフォルト60秒）:
  1. 最新の価格を取得
  2. SL・TP価格とを比較
  3. 条件に達したら決済注文を送信
  4. ポジションをクローズ
```

**評価:** ✅ TP・SL監視は実装されている  
**ただし:** ⚠️ **ボット側での監視** （Hyperliquidの自動実行ではない）

---

## Hyperliquid注文送信時の問題

### 実装の実態

このコードは以下の実装になっています：

```
エントリー:
  ├─ Hyperliquidに「マーケット注文」を送信（TP・SLなし）
  └─ self.sl_price, self.tp_price をメモリに保存

監視:
  ├─ ボットが毎60秒ごとに価格をチェック
  ├─ SL・TP価格に達したか判定
  └─ 達したら「マーケット決済注文」を手動送信

種類: ソフトウェア的なストップロス（Manual Monitoring）
```

### 正式なTP・SL注文の送信方法（実装されていない）

Hyperliquidで正式にTP・SLを設定するには：

```python
# ❌ 現在の実装 (TP・SLなし):
order_type = {"market": {}}
self.exchange.order(
    self.symbol,
    side_long,
    qty,
    price,
    order_type,
    reduce_only=False,
)

# ✅ 正式なTP・SL注文（実装されていない）:
order_type = {
    "market": {
        "tpTriggerPx": 44900.0,    # TP価格
        "slTriggerPx": 41300.0,    # SL価格
    }
}
self.exchange.order(
    self.symbol,
    side_long,
    qty,
    price,
    order_type,
    reduce_only=False,
)
```

---

## 実装の問題点

### 🔴 問題1: ボットが常に稼働している必要がある

**シナリオ:**
```
14:00 - ボットが BTC $42,500 で LONG エントリー
       SL = $41,300, TP = $44,900
       → Hyperliquidには「TP・SL設定なし」の注文が送信

14:05 - ボットが停止した
14:30 - BTC が $41,200 に下落
       → SLを突破しているが、ボットが停止しているので何も起きない
       → ポジションは開きっぱなし（損失は増加し続ける）

15:00 - ボット再起動
       → ようやくSLが発動される
```

**リスク:** 🔴 **ボット停止中の損失が限定されない**

---

### 🔴 問題2: ネットワーク遅延による実行遅延

```
check_interval = 60秒

シナリオ:
  14:00:00 - チェック実行（価格 $42,500）→ SL・TP判定なし
  14:01:00 - チェック実行予定
  
  しかし、この間に：
  14:00:15 - BTC が $41,250 に下落（SL $41,300 に接近）
  14:00:45 - BTC が $41,100 に下落（SL $41,300 を突破）
  
  14:01:05 - ようやくチェック実行
  → 既にSLを$200下回っているので、より悪い価格で決済される
```

**リスク:** 🟡 **SL実行時の価格が予期より悪い（スリッページ）**

---

### 🟡 問題3: 複数のボットインスタンスの競合

**config.json の内容:**
```json
{
  "live_trading": true,
  "environment": "mainnet",
  "symbol": "BTC"
}
```

**スタート方法の分析:**

`start_trader.bat`:
```batch
start "HL_TRADER_V6" python hl_trader_v6.py
start "HL_RSI_SWING_V6" python hl_rsi_swing_v6.py
```

両方のボットが同時に起動されると：
- `hl_trader_v6.py`: TP・SL設定なしで BTC を買う
- `hl_rsi_swing_v6.py`: TP・SLを計算して同じ BTC を買う
- 結果: 同じ通貨に対して2つの異なるポジションが作成される

**リスク:** 🟡 **ポジション管理の混乱**

---

## リスク評価

### TP・SL実装の分類

| 実装方式 | メリット | デメリット | 使用例 |
|--------|--------|---------|-------|
| **ネイティブTP・SL** | サーバー側で実行、ボット停止時も機能 | APIサポートが必要 | 大半の先物取引所 |
| **ソフトウェアTP・SL** | カスタマイズ可能 | ボット依存、遅延可能性 | **現在の実装** |

### リスク評価表

| リスク項目 | 重要度 | 現在の状態 | 評価 |
|---------|------|----------|------|
| **ボット停止時の損失** | 🔴 高 | 保護なし | ❌ 危険 |
| **約定遅延** | 🟡 中 | 60秒ごとの監視 | ⚠️ 許容範囲 |
| **複数インスタンス競合** | 🟡 中 | 可能性あり | ⚠️ 注意が必要 |
| **ネットワーク不具合** | 🟡 中 | 例外処理あり | ⚠️ 再試行機能あり |

---

## 正式な評価

### TP・SL設定: ✅ **部分的に実装**

```
✅ 計算: 完全実装
✅ メモリ保存: 完全実装
✅ 監視ロジック: 完全実装
❌ Hyperliquidへの送信: 実装されていない
❌ ネイティブ実行: 実装されていない
```

### 結論

**TP・SLは「ソフトウェア的に」実装されていますが、「ネイティブなトリガーオーダー」ではありません。**

---

## 推奨アクション

### 短期（今すぐ）

1. ✅ **ボットを継続稼働させる**
   - `check_interval` を 60秒 → 30秒に短縮検討
   - ボット停止時の自動復旧スクリプト実装

2. ✅ **複数ボットの競合を回避**
   - `start_trader.bat` 使用を避ける
   - `start_auto_trader_bg.bat`（hl_rsi_swing_v6.py のみ）に統一

3. ✅ **モニタリング体制の整備**
   - ボットの稼働状況を常時確認
   - ログファイルの定期確認

### 中期（実装改善）

1. **Hyperliquidネイティブのトリガーオーダーに対応**
   - `exchange.order()` の order_type に `tpTriggerPx`, `slTriggerPx` を追加
   - ボット停止時の自動保護を実現

2. **PnLトラッキング**
   - リアルタイムでPnLを計算
   - 自動リバランシング機能の追加

---

**分析終了**

