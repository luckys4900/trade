# PC起動時の自動実行に関する分析報告書

**作成日:** 2026-04-03  
**ステータス:** 🔴 **重大な問題を発見**

---

## 概要

PC起動時に自動実行される仕組みが確認されましたが、**以下の問題があります：**

1. ❌ **古い戦略も一緒に起動されている**
2. ❌ **スタートアップフォルダに複数の設定が存在**
3. ❌ **修正後の新戦略のみを起動する設定に統一されていない**

---

## 発見事項

### 1. スタートアップフォルダの設定

**場所:** `C:\Users\user\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\`

**現在の設定:**

| ファイル | 起動内容 | 戦略 | ステータス |
|---------|--------|------|----------|
| `HL_Trader_Autostart.bat` | `start_trader.bat` | 古い＋新規 混在 | ❌ 問題あり |
| `BTC_V5_Trader.lnk` | 別フォルダの古い戦略 | 古い戦略のみ | ❌ 不要 |

---

### 2. HL_Trader_Autostart.bat の内容

**ファイルパス:** `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\HL_Trader_Autostart.bat`

```batch
@echo off
cd /d "C:\Users\user\Desktop\cursor\trade\"
start "" "start_trader.bat"  # ❌ 古い start_trader.bat を実行
```

---

### 3. start_trader.bat の内容（PC起動時に実行される）

**ファイルパス:** `C:\Users\user\Desktop\cursor\trade\start_trader.bat`

```batch
@echo off
...
start "HL_TRADER_V6" python hl_trader_v6.py        # ❌ 古い実装（TP・SL設定なし）
...
start "HL_RSI_SWING_V6" python hl_rsi_swing_v6.py  # ✅ 新しい実装
```

**問題:** 両方のトレーダーが起動されている

---

### 4. hl_trader_v6.py と hl_rsi_swing_v6.py の違い

| 項目 | hl_trader_v6.py | hl_rsi_swing_v6.py |
|------|-----------------|-------------------|
| **TP・SL設定** | ❌ なし | ✅ あり（Hyperliquidネイティブ） |
| **バックテスト準拠** | ❌ 異なる | ✅ rsi_swing_trader_v6.py準拠 |
| **timeframe** | 1h（不適切） | 4h（正確） |
| **EMAフィルター** | ❌ 不完全 | ✅ EMA(50) |
| **リスク管理** | ⚠️ 不完全 | ✅ 2%ルール |
| **状態** | ⚠️ テスト用 | ✅ 本運用対応 |

---

### 5. BTC_V5_Trader.lnk の参照先

**リンク先:** `C:\Users\user\Desktop\BTC\btc_breakout_v5\run_trader.bat`

**状態:** ❌ 古い別プロジェクトの戦略

---

## 現在の問題シナリオ

```
PC起動（Windows ログオン時）
        ↓
HL_Trader_Autostart.bat が実行
        ↓
start_trader.bat が実行
        ├─ hl_trader_v6.py 起動 ❌ 古い戦略（TP・SL設定なし）
        └─ hl_rsi_swing_v6.py 起動 ✅ 新しい戦略
        
結果：両方のトレーダーが同時稼働
      → 同じBTCで複数の異なる戦略が動作
      → ポジション管理の混乱
      → 予測不可能な挙動
```

---

## 修正が必要なアクション

### 緊急: 現在の状態を停止

**オプション A: 完全に停止（推奨）**
```batch
uninstall_trader_autostart.bat を実行
→ HL_Trader_Autostart.bat をスタートアップから削除
→ BTC_V5_Trader.lnk を手動削除
```

**オプション B: 新戦略のみに変更**
以下を実施:

#### Step 1: HL_Trader_Autostart.bat の修正

**現在:**
```batch
@echo off
cd /d "C:\Users\user\Desktop\cursor\trade\"
start "" "start_trader.bat"  # ❌ 古い実装も実行
```

**修正後:**
```batch
@echo off
cd /d "C:\Users\user\Desktop\cursor\trade\"
start "" "start_live_trader_bg.bat"  # ✅ 新戦略のみ
```

#### Step 2: BTC_V5_Trader.lnk の削除

```batch
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\BTC_V5_Trader.lnk"
```

#### Step 3: start_trader.bat の無効化（念のため）

ファイル名を `start_trader.bat.bak` に変更するか、内容をコメント化

---

## 推奨する最終設定

### ✅ PC起動時に実行されるべき処理

```
PC起動
    ↓
HL_Trader_Autostart.bat が実行
    ↓
start_live_trader_bg.bat が実行
    ↓
python hl_rsi_swing_v6.py が起動
    └─ バックテスト実証戦略（WR60%, PF2.09, Sharpe5.13）
    └─ TP・SLはHyperliquidネイティブで監視
    └─ ボット停止時も保護
```

---

## 検証コマンド

### 現在のスタートアップ設定を確認

```bash
# スタートアップフォルダのファイル一覧
ls -la "$APPDATA/Microsoft/Windows/Start Menu/Programs/Startup/" | grep -i "trader\|hl"

# 出力例:
# BTC_V5_Trader.lnk           ❌ 古い戦略
# HL_Trader_Autostart.bat     ❌ 古い実装も起動
```

### 実際に実行されるバッチの内容

```bash
# start_trader.bat の内容を確認
cat /c/Users/user/Desktop/cursor/trade/start_trader.bat
# → hl_trader_v6.py と hl_rsi_swing_v6.py の両方が起動される
```

---

## 修正手順（推奨）

### 手順 1: 現在のPC自動実行を停止（即座）

```batch
uninstall_trader_autostart.bat を実行
```

### 手順 2: HL_Trader_Autostart.bat を修正（新戦略のみ）

```batch
ファイル: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\HL_Trader_Autostart.bat

@echo off
cd /d "C:\Users\user\Desktop\cursor\trade\"
start "" "start_live_trader_bg.bat"
```

### 手順 3: BTC_V5_Trader.lnk を削除

```batch
スタートアップフォルダから BTC_V5_Trader.lnk を削除
```

### 手順 4: install_trader_autostart.bat を修正（将来の再設定用）

```batch
ファイル: C:\Users\user\Desktop\cursor\trade\install_trader_autostart.bat

現在:
set "START_BAT=%SCRIPT_DIR%start_trader.bat"

修正後:
set "START_BAT=%SCRIPT_DIR%start_live_trader_bg.bat"
```

---

## 修正後の動作確認

### ✅ 修正後のチェックリスト

- [ ] `uninstall_trader_autostart.bat` を実行
- [ ] スタートアップフォルダから以下を確認:
  - [ ] `HL_Trader_Autostart.bat` が削除されている
  - [ ] `BTC_V5_Trader.lnk` が削除されている
- [ ] `install_trader_autostart.bat` を修正（オプション）
- [ ] PC を再起動テスト:
  - [ ] hl_rsi_swing_v6.py のみが起動されることを確認
  - [ ] hl_trader_v6.py は起動されないことを確認
  - [ ] ログファイル（rsi_swing_*.log）が作成されることを確認

### ⚠️ 手動起動テスト

修正前後で `start_live_trader_bg.bat` を手動実行して動作確認：

```
start_live_trader_bg.bat をダブルクリック
  ↓
ウィンドウが最小化状態で起動 ✅
  ↓
rsi_swing_*.log ファイルが作成 ✅
  ↓
"Initialized RSI SWING trader ... SL=1.5xATR, TP=3.0xATR" ✅
```

---

## まとめ

### 現在の状態
- ❌ 古い戦略と新戦略が混在している
- ❌ PC起動時に複数のトレーダーが同時起動される
- ❌ 予測不可能な挙動の原因

### 修正後の状態
- ✅ 新戦略（hl_rsi_swing_v6.py）のみが起動
- ✅ バックテスト実証の戦略が実行
- ✅ TP・SLはHyperliquidネイティブで保護
- ✅ ポジション管理が統一される

---

**推奨:** 即座に現在の自動実行を停止し、新戦略のみを設定してください。

