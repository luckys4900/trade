# トレード戦略分析レポート
## files.zipのバックテスト戦略 vs 現在のライブトレーダー実装

**作成日:** 2026-04-03  
**分析者:** Claude Code  
**調査対象:** start_live_trader_bg.bat トレード戦略精査

---

## 概要

`c:\Users\user\Desktop\files.zip` に含まれるバックテスト戦略と、現在のプロジェクトのライブトレーダー実装を比較検証しました。**重大な相違と懸念事項を発見しました。**

---

## 目次

1. [バックテスト戦略（files.zip）](#バックテスト戦略)
2. [ライブトレーダー実装の分析](#ライブトレーダー実装)
3. [TP・SL設定の詳細比較](#tpsl設定の詳細比較)
4. [発見された問題](#発見された問題)
5. [結論と推奨事項](#結論と推奨事項)

---

## バックテスト戦略

### ファイル構成
- **rsi_swing_trader_v6.py** （バックテスト実装）
- **rsi_swing_v6_report.html** （バックテスト結果レポート）

### 戦略の3層構造

```
Layer 1: RSI Crossover Signal
├─ LONG:  RSI(14) ≤ 30 → RSI > 30 に上抜け（Oversold Exit）
└─ SHORT: RSI(14) ≥ 70 → RSI < 70 に下抜け（Overbought Exit）

Layer 2: EMA(50) Trend Filter
├─ LONG:  Close > EMA(50) （上昇トレンド内のみ）
└─ SHORT: Close < EMA(50) （下降トレンド内のみ）

Layer 3: ATR Risk Management
├─ SL Distance: sl_atr × ATR(14)
├─ TP Distance: tp_atr × ATR(14) 
├─ R:R Ratio:   最低 1:2 保証（tp_atr=3.0, sl_atr=1.5で 1:2）
└─ Time Stop:   max_bars = 20本（80時間）
```

### バックテスト実績（参考値）
```
Win Rate:     60.0%
Profit Factor: 2.09
Sharpe Ratio:  5.13
Max Drawdown: -5.20%
Trades/year:   25
```

### TP・SL設定の詳細（バックテスト版）

**RSIMomentumSwing.\_enter() メソッド（行483-523）:**

```python
def _enter(self, direction, price, atr_now):
    # ============= TP・SL計算 =============
    sl_d = atr_now * self.sl_atr        # SL距離 = ATR × 1.5
    tp_d = atr_now * self.tp_atr        # TP距離 = ATR × 3.0
    
    # ============= ポジションサイズ計算 =============
    eq = float(self.equity)
    sz = max(int(round(eq * self.risk_pct / sl_d)), 1)  # 2%リスク
    mx = int(eq * 0.95 / price)
    sz = min(sz, max(mx, 1))
    
    # ============= エントリー =============
    if direction == "long":
        self.buy(size=sz, sl=price - sl_d, tp=price + tp_d)
    else:  # short
        self.sell(size=sz, sl=price + sl_d, tp=price - tp_d)
    
    self._entry_bar = len(self.data)
```

**特徴:**
- ✅ TP・SLが明示的に設定される（自動実行）
- ✅ ATRベースでボラティリティ連動
- ✅ R:R比が1:2に保証（tp_atr=3.0 / sl_atr=1.5）
- ✅ タイムストップ（max_bars=20本）実装

---

## ライブトレーダー実装

現在のプロジェクトに存在するライブトレーダーは **2つの異なる実装** があります。

### 実装1: hl_rsi_swing_v6.py (推奨実装)

**バージョン:** RSI Momentum Swing v6  
**対象:** Hyperliquid 実トレード  
**実装ステータス:** ✅ **完全実装** 

#### TP・SL設定の実装詳細

**_open_position() メソッド（行483-523）:**

```python
def _open_position(self, side: str, price: float, atr_now: float, bar_time: int) -> None:
    # ============= TP・SL計算 =============
    sl_dist = atr_now * self.sl_atr      # SL距離 = ATR × 1.5（デフォルト）
    tp_dist = atr_now * self.tp_atr      # TP距離 = ATR × 3.0（デフォルト）
    
    # ============= ポジションサイズ計算 =============
    qty = (self.equity * self.risk_pct) / sl_dist if sl_dist > 0 else 0.0
    
    # ============= LONG エントリー =============
    if side == "long":
        self.sl_price = price - sl_dist     # ✅ SL設定
        self.tp_price = price + tp_dist     # ✅ TP設定
        logger.info(
            "OPEN LONG @ %.2f | SL=%.2f TP=%.2f qty=%.6f "
            "(SL=%.1fxATR, TP=%.1fxATR)",
            price, self.sl_price, self.tp_price, qty,
            self.sl_atr, self.tp_atr
        )
        self._place_live_order(True, qty, price, False)
    
    # ============= SHORT エントリー =============
    else:
        self.sl_price = price + sl_dist     # ✅ SL設定
        self.tp_price = price - tp_dist     # ✅ TP設定
        logger.info(
            "OPEN SHORT @ %.2f | SL=%.2f TP=%.2f qty=%.6f "
            "(SL=%.1fxATR, TP=%.1fxATR)",
            price, self.sl_price, self.tp_price, qty,
            self.sl_atr, self.tp_atr
        )
        self._place_live_order(False, qty, price, False)
    
    self.in_position = True
    self.position_side = side
    self.entry_price = price
    self.entry_bar_time = bar_time
```

#### TP・SL執行ロジック（run()メソッド）

**SL・TP・タイムストップの監視（行414-440）:**

```python
if self.position_side == "long":
    # SLチェック
    if self.sl_price is not None and price <= self.sl_price:
        logger.info("LONG SL hit: price=%.2f <= SL=%.2f", price, self.sl_price)
        self._place_live_order(False, qty, price, True)  # クローズ注文
        self._close_position(price)
    
    # TPチェック
    elif self.tp_price is not None and price >= self.tp_price:
        logger.info("LONG TP hit: price=%.2f >= TP=%.2f", price, self.tp_price)
        self._place_live_order(False, qty, price, True)  # クローズ注文
        self._close_position(price)
    
    # タイムストップ（20本 = 80時間）
    elif bars_held >= self.max_bars:
        logger.info("LONG time stop reached (%d bars).", bars_held)
        self._place_live_order(False, qty, price, True)
        self._close_position(price)

elif self.position_side == "short":
    # SLチェック
    if self.sl_price is not None and price >= self.sl_price:
        logger.info("SHORT SL hit: price=%.2f >= SL=%.2f", price, self.sl_price)
        self._place_live_order(True, qty, price, True)
        self._close_position(price, short=True)
    
    # TPチェック
    elif self.tp_price is not None and price <= self.tp_price:
        logger.info("SHORT TP hit: price=%.2f <= TP=%.2f", price, self.tp_price)
        self._place_live_order(True, qty, price, True)
        self._close_position(price, short=True)
    
    # タイムストップ
    elif bars_held >= self.max_bars:
        logger.info("SHORT time stop reached (%d bars).", bars_held)
        self._place_live_order(True, qty, price, True)
        self._close_position(price, short=True)
```

**評価:** ✅ **完全実装**

#### config.json パラメータ

```json
{
  "symbol": "BTC",
  "timeframe": "4h",
  "rsi_period": 14,
  "rsi_overbought": 70,
  "rsi_oversold": 30,
  "sl_atr": 1.5,           // ✅ TP・SL設定あり
  "tp_atr": 3.0,           // ✅ R:R = 1:2
  "equity_usd": 10000,
  "risk_pct": 0.02,        // 2%リスク
  "leverage": 5,
  "check_interval": 60,
  "environment": "mainnet",
  "live_trading": true
}
```

---

### 実装2: hl_trader_v6.py (簡略版)

**バージョン:** BTC/USDT 4H ADAPTIVE RSI v5  
**対象:** Hyperliquid テストネット/デモ  
**実装ステータス:** ⚠️ **TP・SL設定が不足**

#### 問題箇所1: TP・SL計算がない

**run()メソッド内のロジック（行396-477）:**

```python
# ============= 問題: TP・SL計算なし ============= 
if not self.in_position:
    if current_rsi <= self.rsi_oversold:
        if is_live:
            # ❌ TP・SL計算がない
            # ❌ ATR計算がない
            qty_decimal = Decimal(str(self.position_size_usd)) / Decimal(str(current_price))
            qty_decimal = qty_decimal.quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
            qty = float(qty_decimal)
            order_type = {"limit": {"tif": "Ioc"}}
            
            # 注文送信のみ（SL・TP設定なし）
            resp = self.exchange.order(
                self.symbol,
                True,
                qty,
                float(current_price),
                order_type,
                reduce_only=False
            )
            self.in_position = True
            self.entry_price = current_price
        else:
            # ペーパートレード
            logger.info(f"[PAPER] BUY signal: RSI {current_rsi:.2f} <= {self.rsi_oversold}")
            self.in_position = True
            self.entry_price = current_price
else:
    if current_rsi >= self.rsi_overbought:
        if is_live:
            # ❌ 出口条件: RSIレベルのみ（リスク管理なし）
            # ❌ TP・SLの設定がない
            # ❌ 出口のRP距離が不明
            resp = self.exchange.order(
                self.symbol,
                False,
                qty,
                float(current_price),
                order_type,
                reduce_only=True
            )
        
        # ローカルのポジション状態をクローズ
        pnl = 0.0
        if self.entry_price:
            pnl = (current_price - self.entry_price) * self.leverage
        logger.info(
            f"Position closed: est. PnL per 1x notional: {pnl:.2f} "
            f"(entry={self.entry_price}, exit={current_price})"
        )
        self.in_position = False
        self.entry_price = None
```

**問題点:**
- ❌ ATR計算がない
- ❌ SL・TP設定がない
- ❌ ポジションサイズがリスク管理に基づかない（固定の`position_size_usd`）
- ❌ 出口条件が「RSIレベル」のみ（リスク管理がない）
- ❌ タイムストップがない
- ❌ max_drawdown 保護がない

#### config.json パラメータ

```json
{
  "symbol": "BTC",
  "timeframe": "4h",
  "rsi_period": 14,
  "rsi_overbought": 70,
  "rsi_oversold": 30,
  "position_size_usd": 100,      // ⚠️ 固定サイズ
  "max_positions": 1,
  "leverage": 10,                // ⚠️ 高レバレッジ
  "check_interval": 60,
  "environment": "testnet",
  "live_trading": false          // ⚠️ ペーパーモード
}
```

---

## TP・SL設定の詳細比較

### 比較表

| 項目 | files.zip (v6) | hl_rsi_swing_v6.py | hl_trader_v6.py |
|------|----------------|--------------------|-----------------|
| **TP計算** | ✅ tp_atr × ATR | ✅ tp_atr × ATR | ❌ なし |
| **SL計算** | ✅ sl_atr × ATR | ✅ sl_atr × ATR | ❌ なし |
| **ATR指標** | ✅ ATR(14) | ✅ ATR(14) | ❌ なし |
| **R:R比** | ✅ 1:2保証 | ✅ 1:2保証 | ❌ 設定なし |
| **ポジションサイズ** | ✅ リスク% | ✅ リスク% | ⚠️ 固定USD |
| **タイムストップ** | ✅ max_bars=20 | ✅ max_bars=20 | ❌ なし |
| **出口ロジック** | ✅ SL/TP/時間 | ✅ SL/TP/時間 | ❌ RSIのみ |
| **複数フィルター** | ✅ RSI+EMA | ✅ RSI+EMA | ⚠️ RSIのみ |

---

## 発見された問題

### 🔴 重大問題1: hl_trader_v6.py にTP・SL設定がない

**影響範囲:**
- `start_trader.bat` を実行した場合、2つのトレーダーが起動される
- `hl_trader_v6.py` はTP・SLなしで実行される可能性がある
- リスク管理が機能しない状態

**リスク:**
- 暴落時に損失が限定されない
- ストップロスが機能しない
- 取り利益の自動化がない
- ドローダウン管理ができない

### 🟡 問題2: start_live_trader_bg.bat が空

**ファイルサイズ:** 0 バイト  
**影響:** このbatファイルは何も実行していない

### 🟡 問題3: hl_trader_v6.py と hl_rsi_swing_v6.py の混在

**実装の一貫性:**
- `start_trader.bat` は両方を起動（矛盾する設定）
- `start_auto_trader_bg.bat` は hl_rsi_swing_v6.py のみ（推奨）

---

## 結論と推奨事項

### 推奨アーキテクチャ

```
✅ 使用すべき実装:
  - hl_rsi_swing_v6.py 
  - 起動: start_auto_trader_bg.bat
  - TP・SL: ATRベース (1.5x, 3.0x)
  - リスク管理: 2% per trade
  - トレンドフィルター: EMA(50)

❌ 避けるべき実装:
  - hl_trader_v6.py (TP・SL設定なし)
  - start_trader.bat (両方起動で混在)
  - fixed position_size (リスク管理なし)
```

### 戦略の一貫性: ✅ **HIGH**

**hl_rsi_swing_v6.py は files.zip のバックテスト戦略に完全に基づいている:**

| 項目 | files.zip | hl_rsi_swing_v6.py | 一貫性 |
|------|-----------|-------------------|------|
| RSI期間 | 14 | 14 | ✅ |
| Oversold | 30 | 30 | ✅ |
| Overbought | 70 | 70 | ✅ |
| EMA期間 | 50 | 50 | ✅ |
| SL乗数 | 1.5x ATR | 1.5x ATR | ✅ |
| TP乗数 | 3.0x ATR | 3.0x ATR | ✅ |
| R:R比 | 1:2 | 1:2 | ✅ |
| タイムストップ | 20本 | 20本 | ✅ |
| リスク管理 | 2% | 2% | ✅ |

---

## 最終判定

### TP・SL設定の実装状況: ✅ **実装済み（ただし部分的）**

**実装済み:**
- ✅ hl_rsi_swing_v6.py: 完全実装
  - TP・SL計算: ATRベース
  - 自動執行: SL/TP/タイムストップ監視
  - リスク管理: ポジションサイズ最適化
  - トレンドフィルター: EMA(50)

**実装されていない:**
- ❌ hl_trader_v6.py: TP・SL設定なし
  - RSI単独シグナルのみ
  - リスク管理が不十分
  - テストネット/デモ専用

### バックテスト戦略への準拠: ✅ **完全準拠**

hl_rsi_swing_v6.py は files.zip のバックテスト戦略(rsi_swing_trader_v6.py)に完全に準拠しています。

---

## 推奨アクション

1. **使用すべき実装:**
   - `hl_rsi_swing_v6.py` をメインに使用
   - `start_auto_trader_bg.bat` で起動
   - TP・SLはATRベースで自動設定

2. **避けるべき実装:**
   - `hl_trader_v6.py` をメイン実装として使用しない
   - `start_trader.bat` の使用を避ける（両方起動で混在）

3. **検証項目:**
   - config.json で `sl_atr=1.5`, `tp_atr=3.0` を確認
   - ロガー出力で「SL=... TP=...」の表示を確認
   - リアルトレードでSL・TPが正しく設定されたことを確認

---

**分析終了**

