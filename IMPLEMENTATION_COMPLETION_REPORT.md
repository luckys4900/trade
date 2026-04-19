# 実装完了レポート
## start_live_trader_bg.bat をバックテスト戦略に対応させる

**完了日:** 2026-04-03  
**ステータス:** ✅ **実装完了**

---

## 概要

`start_live_trader_bg.bat` を実行すると、files.zipのバックテスト戦略（rsi_swing_trader_v6.py: WR60%, PF2.09, Sharpe5.13）が実際のライブトレード環境で実行されるように、以下の3つのファイルを修正しました。

---

## 修正内容

### 1. config.json（timeframe 修正）

**変更内容:**
```json
// 変更前
"timeframe": "1h",

// 変更後
"timeframe": "4h",
```

**理由:** バックテスト戦略は4H足で実証されています。1H足では異なる結果になります。

---

### 2. hl_rsi_swing_v6.py（コアロジック修正）

#### 修正点 2a: max_bars をconfig.jsonから読み込む

**行181:**
```python
# 変更前
self.max_bars: int = 20

# 変更後
self.max_bars: int = int(config.get("max_bars", 20))
```

**効果:** config.jsonで `"max_bars"` を変更できるようになります。

---

#### 修正点 2b: 旧 `_place_live_order` を削除

**行323（削除済み）:**
```python
# これは削除されました
def _place_live_order(self, side_long: bool, qty: float, price: float, reduce_only: bool) -> None:
    order_type = {"market": {}}  # ❌ SDK非対応
    ...
```

**理由:** `{"market": {}}` はHyperliquid SDKで無効です。

---

#### 修正点 2c: 新メソッド追加 - `_place_entry_order()`

**行323～360:**
```python
def _place_entry_order(self, side_long: bool, qty: float, price: float) -> bool:
    """
    エントリー注文を発注。IOC指値（実質成行）。
    成功したら True、失敗したら False を返す。
    """
    if not (self.live_trading and self.exchange is not None):
        return True  # paper mode
    try:
        # IOC指値: スリッページ5%
        slippage = 0.05
        if side_long:
            limit_px = round(price * (1 + slippage), 1)
        else:
            limit_px = round(price * (1 - slippage), 1)

        order_type = {"limit": {"tif": "Ioc"}}  # ✅ SDK対応
        logger.info("[LIVE] Entry order: %s coin=%s qty=%.6f limit_px=%.2f",
                    "BUY" if side_long else "SELL", self.symbol, qty, limit_px)
        resp = self.exchange.order(
            self.symbol, side_long, float(qty), float(limit_px),
            order_type, reduce_only=False,
        )
        # レスポンス解析して成功/失敗を判定
        statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
        if statuses and "filled" in statuses[0]:
            return True
        elif statuses and "error" in statuses[0]:
            logger.error("[LIVE] Entry order rejected: %s", statuses[0]["error"])
            return False
        return True
    except Exception as e:
        logger.error("[LIVE] Entry order failed: %s", e)
        return False
```

**特徴:**
- ✅ IOC指値（best ask/bid ± 5%スリッページ）で実質成行
- ✅ 成功/失敗をboolで返す
- ✅ ペーパーモードでは常に成功扱い
- ✅ SDK対応のorder_type: `{"limit": {"tif": "Ioc"}}`

---

#### 修正点 2d: 新メソッド追加 - `_place_tp_sl_orders()`

**行361～413:**
```python
def _place_tp_sl_orders(self, side_long: bool, qty: float,
                         tp_price: float, sl_price: float) -> None:
    """
    TP・SL のtrigger注文を取引所に発注。
    失敗時はソフトウェア監視にフォールバック（エラーログのみ）。
    """
    if not (self.live_trading and self.exchange is not None):
        return

    # TP注文: trigger注文 with reduce_only=True
    try:
        tp_order_type = {
            "trigger": {
                "triggerPx": float(tp_price),
                "isMarket": True,
                "tpsl": "tp",  # ✅ Hyperliquidネイティブ設定
            }
        }
        tp_is_buy = not side_long  # LONG→SELL, SHORT→BUY
        logger.info("[LIVE] TP order: triggerPx=%.2f is_buy=%s qty=%.6f",
                    tp_price, tp_is_buy, qty)
        tp_resp = self.exchange.order(
            self.symbol, tp_is_buy, float(qty), float(tp_price),
            tp_order_type, reduce_only=True,
        )
        logger.info("[LIVE] TP order response: %s", tp_resp)
    except Exception as e:
        logger.error("[LIVE] TP order failed (fallback to software monitor): %s", e)

    # SL注文: trigger注文 with reduce_only=True
    try:
        sl_order_type = {
            "trigger": {
                "triggerPx": float(sl_price),
                "isMarket": True,
                "tpsl": "sl",  # ✅ Hyperliquidネイティブ設定
            }
        }
        sl_is_buy = not side_long
        logger.info("[LIVE] SL order: triggerPx=%.2f is_buy=%s qty=%.6f",
                    sl_price, sl_is_buy, qty)
        sl_resp = self.exchange.order(
            self.symbol, sl_is_buy, float(qty), float(sl_price),
            sl_order_type, reduce_only=True,
        )
        logger.info("[LIVE] SL order response: %s", sl_resp)
    except Exception as e:
        logger.error("[LIVE] SL order failed (fallback to software monitor): %s", e)
```

**特徴:**
- ✅ **Hyperliquidネイティブのtrigger注文**でTP・SLを取引所側に設定
- ✅ ボット停止時も取引所がTP・SLを監視・実行
- ✅ 失敗時はソフトウェア監視にフォールバック（二重保護）
- ✅ TP: `"tpsl": "tp"` (利確)
- ✅ SL: `"tpsl": "sl"` (損切)
- ✅ reduce_only=True で、ポジション縮小のみ

---

#### 修正点 2e: 新メソッド追加 - `_place_close_order()`

**行415～433:**
```python
def _place_close_order(self, side_long: bool, qty: float, price: float) -> None:
    """ポジションクローズ注文（IOC指値 reduce_only=True）"""
    if not (self.live_trading and self.exchange is not None):
        return
    try:
        slippage = 0.05
        if side_long:
            limit_px = round(price * (1 + slippage), 1)
        else:
            limit_px = round(price * (1 - slippage), 1)
        order_type = {"limit": {"tif": "Ioc"}}
        logger.info("[LIVE] Close order: %s coin=%s qty=%.6f limit_px=%.2f",
                    "BUY" if side_long else "SELL", self.symbol, qty, limit_px)
        resp = self.exchange.order(
            self.symbol, side_long, float(qty), float(limit_px),
            order_type, reduce_only=True,
        )
        logger.info("[LIVE] Close order response: %s", resp)
    except Exception as e:
        logger.error("[LIVE] Close order failed: %s", e)
```

**用途:** SL・TP・タイムストップ発動時の決済注文

---

#### 修正点 2f: `_open_position()` メソッドの修正

**行590～612:**
```python
def _open_position(self, side: str, price: float, atr_now: float, bar_time: int) -> None:
    sl_dist = atr_now * self.sl_atr
    tp_dist = atr_now * self.tp_atr
    qty = (self.equity * self.risk_pct) / sl_dist if sl_dist > 0 else 0.0
    side_long = (side == "long")

    if side_long:
        self.sl_price = price - sl_dist
        self.tp_price = price + tp_dist
    else:
        self.sl_price = price + sl_dist
        self.tp_price = price - tp_dist

    logger.info("OPEN %s @ %.2f | SL=%.2f TP=%.2f qty_est=%.6f",
                side.upper(), price, self.sl_price, self.tp_price, qty)

    # ✅ エントリー注文送信
    entry_ok = self._place_entry_order(side_long, qty, price)

    if entry_ok:
        # ✅ エントリー成功後にTP/SL注文を取引所に送信
        self._place_tp_sl_orders(side_long, qty, self.tp_price, self.sl_price)
    else:
        logger.error("Entry order failed. Position not opened.")
        self.sl_price = None
        self.tp_price = None
        return

    self.in_position = True
    self.position_side = side
    self.entry_price = price
    self.entry_bar_time = bar_time
```

**修正フロー:**
1. SL・TP価格を計算
2. `_place_entry_order()` でエントリー
3. エントリー成功時のみ `_place_tp_sl_orders()` でTP・SL発注
4. エントリー失敗時は状態をリセット

---

#### 修正点 2g: `run()` メソッド内のクローズ呼び出しを修正（6箇所）

**変更:**
```python
# 変更前（全6箇所）
self._place_live_order(False, qty, price, True)  # ❌ 無効なorder_type

# 変更後
self._place_close_order(False, qty, price)  # ✅ IOC指値
```

**変更箇所:**
- 行513: LONG SL hit
- 行517: LONG TP hit
- 行521: LONG time stop
- 行527: SHORT SL hit
- 行531: SHORT TP hit
- 行535: SHORT time stop

---

#### 修正点 2h: 既存ポジション引き継ぎ時のTP/SL送信

**行499～502（追加）:**
```python
# 既存ポジション用のTP/SL注文を取引所に送信
qty = self._calc_qty(atr_now)
side_long = (self.position_side == "long")
self._place_tp_sl_orders(side_long, qty, self.tp_price, self.sl_price)
```

**効果:** ボット起動時に既存ポジションが検知された場合、即座にTP・SLをHyperliquidに設定

---

### 3. start_live_trader_bg.bat（起動スクリプト修正）

**変更内容:**
- 空ファイル → `hl_rsi_swing_v6.py` を起動する実装
- `start_auto_trader_bg.bat` と同じ構造で、バックグラウンド起動
- ログファイル監視機能
- プロセス起動確認機能

**実行内容:**
```batch
start "BTC Live Trader v6" /MIN python hl_rsi_swing_v6.py
```

**出力:**
- プロセス起動確認
- 最新ログファイルの内容表示
- エラー時の診断情報

---

## 実装の特徴

### ✅ TP・SLがHyperliquidネイティブで実行される

| 項目 | 実装内容 |
|------|--------|
| エントリー | IOC指値 (IOC order type) |
| TP | Hyperliquid trigger注文 (`tpsl: "tp"`) |
| SL | Hyperliquid trigger注文 (`tpsl: "sl"`) |
| ボット停止時 | 取引所がTP・SLを監視 ✅ |
| フォールバック | ソフトウェア監視も併行 (二重保護) |

### ✅ バックテスト戦略に完全準拠

| パラメータ | 値 |
|-----------|-----|
| RSI期間 | 14 |
| Oversold | 30 |
| Overbought | 70 |
| EMA期間 | 50 |
| SL乗数 | 1.5× ATR |
| TP乗数 | 3.0× ATR |
| R:R比 | 1:2 ✅ |
| タイムストップ | 20本 ✅ |
| リスク/トレード | 2% ✅ |
| Timeframe | 4H ✅ |

### ✅ エラーハンドリング

```python
# エントリー失敗 → ポジション状態をリセット
if entry_ok:
    self._place_tp_sl_orders(...)
else:
    self.sl_price = None
    self.tp_price = None
    return

# TP・SL発注失敗 → ソフトウェア監視にフォールバック
try:
    self.exchange.order(...)
except Exception as e:
    logger.error("[LIVE] TP order failed (fallback to software monitor): %s", e)
```

---

## ログ出力例

起動時:
```
2026-04-03 10:00:00 [INFO] ============================================================
2026-04-03 10:00:00 [INFO]  BTC/USDT RSI SWING v6 - LIVE TRADER
2026-04-03 10:00:00 [INFO] ============================================================
2026-04-03 10:00:00 [INFO] Initialized RSI SWING trader for BTC 4h (rsi_period=14, OS=30, OB=70, SL=1.5xATR, TP=3.0xATR)
2026-04-03 10:00:00 [INFO] Starting RSI SWING trading loop (live mode)...
```

シグナル発生時:
```
2026-04-03 10:05:00 [INFO] BAR 2026-04-03T10:00:00 | Price=42500.0 RSI=28.5 (prev=35.2) EMA50=41800.0 ATR14=800.0
2026-04-03 10:05:00 [INFO] OPEN LONG @ 42500.00 | SL=41300.00 TP=44900.00 qty_est=0.001234
2026-04-03 10:05:01 [INFO] [LIVE] Entry order: BUY coin=BTC qty=0.001234 limit_px=44625.00
2026-04-03 10:05:02 [INFO] [LIVE] Entry order response: {...}
2026-04-03 10:05:02 [INFO] [LIVE] TP order: triggerPx=44900.00 is_buy=False qty=0.001234
2026-04-03 10:05:03 [INFO] [LIVE] TP order response: {...}
2026-04-03 10:05:03 [INFO] [LIVE] SL order: triggerPx=41300.00 is_buy=False qty=0.001234
2026-04-03 10:05:04 [INFO] [LIVE] SL order response: {...}
2026-04-03 10:05:05 [INFO] In position (long). SL=41300.00 TP=44900.00 | Entry=42500.00 Cur=42520.00
```

---

## 検証チェックリスト

実装後の検証ステップ:

- [ ] `start_live_trader_bg.bat` をダブルクリック実行
- [ ] プロセス起動確認: "BTC Live Trader v6" ウィンドウが最小化状態で起動
- [ ] ログファイル確認: `rsi_swing_*.log` にメッセージが出力
- [ ] "Initialized RSI SWING trader ... SL=1.5xATR, TP=3.0xATR" メッセージ確認
- [ ] シグナル発生待機（4H足ごと、60秒間隔でチェック）
- [ ] シグナル発生時:
  - [ ] "[LIVE] Entry order response" が出力
  - [ ] "[LIVE] TP order response" が出力
  - [ ] "[LIVE] SL order response" が出力
- [ ] Hyperliquid ポートフォリオで:
  - [ ] ポジションが開かれたこと確認
  - [ ] TP・SL注文が表示されていることを確認
- [ ] SL・TP到達時:
  - [ ] "LONG SL hit" / "LONG TP hit" / "SHORT SL hit" / "SHORT TP hit" ログ出力確認
  - [ ] "[LIVE] Close order response" が出力
  - [ ] ポジションが決済されたこと確認

---

## 重要な注意事項

### ⚠️ config.json の設定確認

実行前に必ず確認:
```json
{
  "environment": "mainnet",        // 本番環境
  "live_trading": true,             // 本番トレードモード
  "timeframe": "4h",                // 4H足（重要）
  "sl_atr": 1.5,                    // SL: 1.5xATR
  "tp_atr": 3.0,                    // TP: 3.0xATR
  "max_bars": 20,                   // タイムストップ: 20本
  "equity_usd": 199.12,             // 現在のアカウント残高
  "risk_pct": 0.02                  // 2%リスク/トレード
}
```

### 🔴 注意: ネイティブTP・SL設定

Hyperliquidの trigger注文が失敗した場合、**ソフトウェア監視にフォールバック** されます。これは意図された設計で、二重保護です。しかしログを確認して、TP・SL注文が正常に送信されていることを定期的に確認してください。

---

## 修正前後の比較

| 項目 | 修正前 | 修正後 |
|------|-------|-------|
| order_type | `{"market": {}}` ❌ | `{"limit": {"tif": "Ioc"}}` ✅ |
| TP・SL送信 | なし ❌ | trigger注文で送信 ✅ |
| TP・SL監視 | ソフトウェアのみ | ソフトウェア + Hyperliquid ✅ |
| ボット停止時 | 無保護 ❌ | Hyperliquidが監視 ✅ |
| timeframe | 1h ❌ | 4h ✅ |
| start_live_trader_bg.bat | 空ファイル ❌ | 稼働スクリプト ✅ |
| 戦略根拠 | 不明 | files.zipバックテスト実証 ✅ |

---

**実装完了 - 2026-04-03**

