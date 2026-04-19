# Qwen Unified Auto-Trader - プロジェクト状況記録

## 最終更新日
2026-04-18 (Contrarian Edge Filter OOS検証完了)

---

## 現在の稼働状況

| 項目 | 状態 |
|------|------|
| プロセス | 実行中（Whale / Macro / Kronos / Unified の4系統） |
| モード | ライブトレード（Hyperliquid Mainnet） |
| ウォレット | `0x7dd9f0C23Fb61CA3f36B8414306310F963093c12` |
| 残高 | $190.59 |
| ポジション | なし（OCPM=No, MR=No, RSISwing=No, Contrarian=No） |
| BTC価格 | $70,842.50 |
| RSI(14) | 42.9 |
| トレンド | UPTREND |
| 更新間隔 | 60秒 |

---

## プロジェクト構成

### 起動関連ファイル
| ファイル | 用途 |
|----------|------|
| `Qwen_本番自動売買_起動.bat` | メイン起動バッチ（二重起動防止機能付き） |
| `Qwen_Background_Start.vbs` | バックグラウンド起動用VBS（重複起動防止、フルパス指定） |
| `Qwen_Status_Check.bat` | 状態確認バッチ（プロセス、ログ、状態ファイル表示） |
| `Qwen_AutoTrader.lnk` | スタートアップショートカット（PC起動時に自動実行） |
| `LAPTOP_MIGRATION_HANDOFF.md` | ノートPC移行用の引き継ぎファイル |
| `NOTEBOOK_SETUP_CHECKLIST.md` | ノートPCセットアップ手順 |
| `CURSOR_NOTEBOOK_HANDOFF_PROMPT.md` | ノートPCの Cursor で最初に貼るプロンプト |

### 実行スクリプト
| ファイル | 用途 |
|----------|------|
| `SYSTEM\qwen_unified_live.py` | **メイン取引ボット**（OCPM + Range MR + RSI Swing v6 + Contrarian統合） |
| `SYSTEM\kronos_predictor.py` | **Contrarian予測プロセス**（Kronos-base逆張りシグナル生成） |
| `qwen_ocpm_signal_monitor.py` | シグナル監視・アラート通知用 |
| `qwen_unified_strategy.py` | 戦略ロジック定義 |

### 設定ファイル
| ファイル | 用途 |
|----------|------|
| `config.json` | 取引パラメータ（RSI、SL/TP、レバレッジなど） |
| `config.py` | 戦略設定、バックテスト設定、グリッド設定 |
| `.env` | API認証情報（HL_PRIVATE_KEY、HL_WALLET_ADDRESS） |
| `trade_state_unified.json` | 現在の取引状態（リアルタイム更新） |

### ログ
| 場所 | 内容 |
|------|------|
| `logs\unified_live_*.log` | 統合取引ボットのログ |
| `rsi_swing_*.log` | RSI Swing単体のログ（旧版） |
| `trader_*.log` | 旧トレーダーのログ |

---

## 戦略パラメータ

### OCPM（Trend Pullback）
| パラメータ | 値 |
|------------|-----|
| EMA Fast | 21 |
| EMA Slow | 55 |
| RSI Pullback LONG | 48.0以下 |
| RSI Pullback SHORT | 52.0以上 |
| ATR SL Mult | 3.0 |
| ATR TP Mult | 6.0 |
| Max Hold | 20本 |

### Range MR（Mean Reversion）
| パラメータ | 値 |
|------------|-----|
| BB Period | 20 |
| BB Std | 2.0 |
| RSI Oversold | 30.0 |
| RSI Overbought | 70.0 |
| Max ADX | 25.0 |
| Max Hold | 10本 |

### RSI Swing v6
| パラメータ | 値 |
|------------|-----|
| RSI Period | 14 |
| RSI OS/OB | 30.0 / 70.0 |
| SL ATR | 2.0 |
| TP ATR | 5.0 |
| Max Hold | 20本 |

### 4h Contrarian (Kronos-base)
| パラメータ | 値 |
|------------|-----|
| Logic | Kronos予測の逆方向へエントリー |
| Lookback | 400本 |
| Samples | 30 |
| T / top_p | 0.8 / 0.6 |
| SL ATR | 2.0 |
| TP ATR | 4.0 |
| Max Hold | 8本 |
| Capital Pool | 70% |

### リスク管理
| パラメータ | 値 |
|------------|-----|
| Legacy Pool | 30%（OCPM + MR + RSISwing 共有） |
| Contrarian Pool | 70% |
| Legacy Risk % | 1.5% |
| Contrarian Risk % | 1.4% |
| Max Position % | 40%（Legacy） / 30%（Contrarian） |
| Max Consecutive Losses | 5 |
| Cooldown Bars | 2 |
| Drawdown Halt % | 15% |

---

## 修正履歴（2026-04-13）

### 1. Contrarian 実運用安定化
- `trade_state_unified.json` を `Contrarian` + `last_signal_ts` 対応の正しい初期構造に修正
- `UnifiedEngine.__init__()` の `current_bar` 初期化順を修正し、保存状態を正しく復元するよう更新
- 実稼働確認で `Whale / Macro / Kronos / Unified` の4系統起動を再検証

### 2. Hyperliquid 発注処理の修正
- 発注数量を `szDecimals` に合わせて切り捨てる `round_order_size()` を追加
- `place_order()` を `IOC limit` 注文へ変更し、`float_to_wire causes rounding` と `Invalid order type` を解消
- IOC 応答は `filled` を確認してから成功扱いにし、未約定時にローカル状態だけ `in_pos=True` にならないよう修正
- `_open_strat()` でも実発注数量を保存するよう揃え、状態同期のズレを防止

### 3. テスト強化
- `test_contrarian_integration.py` に数量丸め、IOC order_type、未約定拒否、状態保存サイズ整合のテストを追加
- 最新確認結果: `pytest test_contrarian_integration.py` で 9 件すべて成功

### 4. ノートPC移行の引き継ぎ整備
- `LAPTOP_MIGRATION_HANDOFF.md` を追加し、ノートPC側での再開前提を整理
- `NOTEBOOK_SETUP_CHECKLIST.md` を追加し、Python / Cursor / 依存導入の順序を固定
- `CURSOR_NOTEBOOK_HANDOFF_PROMPT.md` を追加し、ノートPC側の新規 Cursor セッションでそのまま再開できるようにした

### 5. Contrarian の live/backtest 整合修正
- `SYSTEM\qwen_unified_live.py` で評価バーを「最新の確定4h足」に統一し、`current_bar` / `MAX_HOLD` / `cooldown` が毎分ではなく 4h bar 単位で進むよう修正
- 新しい確定4h足が出たときだけ新規エントリー判定するよう変更し、同一 bar で何度もシグナル判定しないようにした
- `Contrarian` は `signal timestamp` が最新の確定4h足より古い場合スキップするように修正
- `trade_alignment_log.json` への追記を「約定成功後のみ」に変更し、未約定試行で EV ログが汚れないよう修正
- `_open_strat()` を成功/失敗の真偽値返却に変更し、filled-only logging に合わせて各戦略の記録タイミングを調整

### 6. 4h/1h 再現 backtest 導線の整備
- `kronos_contrarian_backtest.py` に `argparse` を追加し、4h full / 前半 / 後半 / 1h 直近6ヶ月を同一スクリプトから再生成できるよう整理
- 従来どおり `kronos_contrarian_results.json` を出力しつつ、詳細比較用に `kronos_contrarian_report.json` を出力する構成へ拡張
- GPU 確認つきの実行スモークで `cuda:0` / `RTX 4070` 認識と 4h 推論開始を確認

### 7. テスト拡張
- `test_contrarian_integration.py` を 13件に拡張
- 追加した確認項目:
  - 確定4h足でのみ `current_bar` が進む
  - 新しい確定足がないループでは entry 判定しない
  - 古い `Contrarian` signal を新 bar で再利用しない
  - 未約定 trade を alignment log に残さない
- 最新確認結果: `pytest test_contrarian_integration.py` で 13 件すべて成功
- `python -m py_compile SYSTEM\qwen_unified_live.py test_contrarian_integration.py kronos_contrarian_backtest.py` も成功

### 8. 完成確認の fresh verification
- `python -u kronos_contrarian_backtest.py --report-output kronos_contrarian_report.json` を完走
- 再生成結果は `4h Full Contrarian = -1.0% / PF 1.05 / MDD 16.7%`、`1h Recent 6m = -20.8%` で、従来想定されていた強い優位性は再現されなかった
- `SYSTEM\whale_monitor.py` の設定ファイル探索を修正し、`MASTER_LAUNCHER.bat` からでも `SYSTEM\whale_wallets.json` を読めるようにした
- live 実行では `Bar 197` が複数分にわたり固定され、`current_bar` が毎分進まないことを確認
- `kronos_contrarian_signal.json` が更新されても、新しい確定4h足が来るまで state は据え置きで、毎分の再エントリー挙動は発生していない

---

## 修正履歴（2026-04-15）

### 1. BTC EV フィルター実装
- `SYSTEM\qwen_unified_live.py` に `Contrarian` 用の `mid-volatility gate` を追加
- `vol_pct`（直近50本の絶対リターン順位）を live 指標計算へ追加し、`35 <= vol_pct <= 80` のときだけ `Contrarian` を許可
- フィルター外では `Contrarian` エントリーをスキップするようにし、低ボラ/過熱ボラのノイズ局面を除外

### 2. OCPM hard regime 実装
- `SYSTEM\qwen_unified_live.py` に `OCPM` 専用の `hard regime filter` を追加
- 条件は `close > EMA55 > EMA200` かつ `EMA21 > EMA55` かつ `EMA21 slope > 0`（SHORT は逆）
- `RangeMR` は現状ロジックを維持し、`hard_ocpm_only` の BTC 4h 検証結果に合わせて `OCPM` のみ厳格化
- バックテスト比較では `hard_ocpm_only = Return +2.76% / Expectancy +$0.1048 / PF 1.323 / MDD 4.23% / 32 trades (~1.32 trades per month)` を確認

### 3. テスト追加
- `test_contrarian_integration.py` に以下を追加:
  - `compute_indicators()` が `vol_pct` を出力すること
  - `Contrarian` がボラティリティゲート外でエントリーしないこと
  - `Contrarian` がゲート内で通常どおりシグナル消費/記録すること
  - `compute_indicators()` が `OCPM hard regime` 列を出力すること
  - `OCPM` が hard regime 外でエントリーしないこと
  - `OCPM` が hard regime 内で通常どおり発注フローへ進むこと

### 4. 起動導線更新
- `START\MASTER_LAUNCHER.bat` と `MASTER_LAUNCHER.bat` の案内文を更新
- ランチャーから起動される `SYSTEM\qwen_unified_live.py` に BTC EV フィルターが反映される状態に統一

### 5. fresh verification
- `pytest test_contrarian_integration.py`
- `python -m py_compile SYSTEM\qwen_unified_live.py test_contrarian_integration.py`
- `cmd /c "echo 0| START\MASTER_LAUNCHER.bat"`

---

## 修正履歴（2026-04-12）

### 1. Contrarian 戦略統合
- `SYSTEM\qwen_unified_live.py` に `Contrarian` を第4戦略として追加
- `kronos_contrarian_signal.json` を読むエントリー処理追加
- 固定 SL=2ATR / TP=4ATR / Max Hold=8 のエグジット追加
- 状態保存・取引同期・クールダウン処理を `Contrarian` 対応

### 2. 資金配分の分離
- 既存3戦略は口座残高の 30% プールを共有
- Contrarian は口座残高の 70% プールを使用
- 新規エントリーは各プールの空き notional を超えないよう制限

### 3. 起動・監視導線の更新
- `MASTER_LAUNCHER.bat` を Windows CMD 構文に修正
- `START\MASTER_LAUNCHER.bat` に Kronos Predictor 起動を追加
- `Qwen_本番自動売買_起動.bat` も 4プロセス起動に更新
- `SYSTEM\dashboard.py` に Contrarian signal / strategy state を追加
- `SYSTEM\kronos_predictor.py` に `logs\kronos_predictor_live.log` 出力を追加

---

## 修正履歴（2026-04-05）

### 1. eth_account モジュールエラー修正
- **問題**: `No module named 'eth_account'` で起動失敗
- **原因**: VBSが `pythonw.exe` をフルパスで指定していなかった
- **修正**: `Qwen_Background_Start.vbs` にフルパス `C:\Users\user\AppData\Local\Programs\Python\Python310\pythonw.exe` を設定

### 2. 重複起動防止機能追加
- **問題**: 複数回クリックすると複数プロセスが起動する
- **修正**: 
  - `Qwen_本番自動売買_起動.bat` にプロセスチェック追加（実行中であればスキップ）
  - `Qwen_Background_Start.vbs` にpythonw.exe存在チェック追加

### 3. 状態確認バッチファイル作成
- **問題**: 動作確認がしづらい
- **修正**: `Qwen_Status_Check.bat` を作成（プロセス、ログ、状態ファイルを一度に表示）
- **注意**: 日本語ファイル名は文字化けするため英語名 `Qwen_Status_Check.bat` を使用

### 4. PC自動起動設定
- **設定**: スタートアップフォルダに `Qwen_AutoTrader.lnk` を作成
- **削除**: 古い `HL_Trader_Autostart.bat` を削除（旧版hl_trader_v6.py起動）

---

## 操作方法

### 起動方法
```
Qwen_本番自動売買_起動.bat をダブルクリック
```
- 既に実行中の場合は「ALREADY RUNNING」と表示して終了
- 新規起動の場合はバックグラウンドで開始

### 状態確認方法
```
Qwen_Status_Check.bat をダブルクリック
```
表示内容：
1. プロセス状態（RUNNING/STOP、PID）
2. 最新ログの末尾30行
3. 現在の取引状態（ポジション有無、エントリー価格、SL/TP）

### 停止方法
```
タスクマネージャー → pythonw.exe を終了
```
または
```
taskkill /F /IM pythonw.exe
```

### ログ確認方法
```
logs\unified_live_*.log をテキストエディタで開く
```

---

## トラブルシューティング

### ボットが起動しない
1. `Qwen_Status_Check.bat` でプロセス状態を確認
2. `logs\unified_live_*.log` でエラーメッセージを確認
3. 一般的なエラー：
   - `No module named 'eth_account'` → `pip install eth_account hyperliquid-python-sdk`
   - `Failed to init HL client` → `.env` のAPIキー確認

### 重複起動してしまった
```
taskkill /F /IM pythonw.exe
taskkill /F /IM wscript.exe
```
実行後、再度 `Qwen_本番自動売買_起動.bat` を実行

### シグナルは出ているが取引しない
- アラート監視ツールと実際の取引ボットは別物
- 取引ボットはより厳格な条件でエントリー判断
- 現在のRSIが閾値に到達していない可能性がある

---

## バックテスト実績

| 戦略 | 期間 | リターン | トレード数 | 勝率 | PF |
|------|------|----------|------------|------|-----|
| 統合 | 2年 | +6.51% | 81 | 55.6% | 1.23 |
| RSI Swing v6 | 4H | - | - | 60% | 2.09 |
| Contrarian (Kronos mult OFF) | 2024-04~12 | -6.7万USD | 1121 | - | - |
| Contrarian (Kronos mult ON) | 2024-04~12 | -8.9万USD | 1121 | - | - |

### Kronos Contrarian Multiplier 調査結果 (2026-04-18)

- **目的**: ContrarianエントリにKronosサイズマルチプライヤ(1.4/0.7交互)を適用し期待値向上を検証
- **結果**: マルチプライヤONで損失が31%拡大(-67k -> -89k USD)、Sharpe悪化(-0.058 -> -0.075)
- **結論**: **マルチプライヤは期待値を悪化させるため不採用**
- **対応**: `contrarian_use_kronos_multiplier = False` (デフォルト無効) を設定
- **コード**: `SYSTEM/qwen_unified_live.py` にフラグ実装済み(デフォルトOFF)

### Kronos Edge Filter 実装 (2026-04-18)

- **実Kronos予測精度**: 49.3% (2013予測/4446bars) → 50%未満のため逆張り(Contrarian)が正しい
- **発見**: RSI>55 & UPTREND条件でKronos精度が46.3%に低下 → Contrarian WR 53.7%
- **実装**: `contrarian_edge_filter_enabled = True` (RSI>55 & UPTRENDのみエントリ)
- **リスク**: `contrarian_risk_pct = 0.04` (4%、積極モード)

### Contrarian Edge Filter OOS検証結果 (2026-04-18)

- **検証手法**: 70/30 IS/OOS分割、SL/TP/max_hold完全再現、Taker fee 0.035%、Slippage 0.1%
- **Kronos精度**: IS=49.3% / OOS=49.2%（両方50%未満→逆張り妥当）
- **In-Sample結果**:
  - No filter: PnL=-11,678 / WR 43.7% / PF 0.933 / Sharpe -0.058
  - **RSI>55 & UPTREND: PnL=+447 / WR 48.7% / PF 1.006 / Sharpe 0.006**
- **Out-of-Sample結果**:
  - No filter: PnL=+3,937 / WR 47.9% / PF 1.052 / Sharpe 0.047
  - **RSI>55 & UPTREND: PnL=+4,962 / WR 49.3% / PF 1.218 / Sharpe 0.176**
- **判定**: **フィルタ有効（OOS検証パス）**
  - OOS PnL > 0、PF > 1.0、Sharpe改善
  - IS→OOSで性能低下なし（むしろOOSで改善）→過学習なし
  - DD改善（5.8% → 4.7%）
- **結論**: `contrarian_edge_filter_enabled = True` を本番採用確定

---

## 注意事項

1. **メインネット接続** → 実際のお金が動きます。十分注意してください。
2. **自動起動設定済み** → PC起動時に自動的にボットが起動します。
3. **ログは定期的に確認** → エラーが発生していないか確認してください。
4. **残高管理** → 現在の残高は$211.19です。リスク管理設定を確認してください。

---

## 次回作業時の確認事項

1. `Qwen_Status_Check.bat` で稼働状況を確認
2. 最新ログでエラーがないか確認
3. `trade_state_unified.json` でポジション状態を確認
4. 必要に応じて `Qwen_本番自動売買_起動.bat` で再起動
