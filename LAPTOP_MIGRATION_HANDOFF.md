# Laptop Migration Handoff

## 目的

このファイルは、`trade` プロジェクトをノートPCへ移し、`Cursor` 上でこの作業を継続するための引き継ぎ書です。

ノートPC側の新しい `Cursor` セッションでは、まずこのファイルと `PROJECT_STATUS.md` を読ませてから作業を再開してください。

## 現在の前提

- プロジェクト: `trade`
- 対象環境: Windows ノートPC
- 運用対象: Hyperliquid Mainnet
- 現在の主要構成:
  - `SYSTEM/qwen_unified_live.py`
  - `SYSTEM/kronos_predictor.py`
  - `SYSTEM/whale_monitor.py`
  - `SYSTEM/macro_filter.py`
- 4系統構成:
  - Whale
  - Macro
  - Kronos
  - Unified

## 実装の現状

- `Contrarian` は実装済み
- `trade_state_unified.json` は `contrarian` / `last_signal_ts` 対応済み
- 発注処理は `IOC limit` + 数量丸め対応済み
- 未約定を成功扱いしない修正済み
- テスト: `test_contrarian_integration.py` は通過済み

## ノートPCへ移すもの

1. このプロジェクトフォルダ一式
2. `.env`
3. 必要なら `logs/` と `trade_state_unified.json`

`.env` には秘密情報が含まれるため、安全な手段で移してください。

## ノートPC側で最初に開くファイル

1. `LAPTOP_MIGRATION_HANDOFF.md`
2. `PROJECT_STATUS.md`
3. `NOTEBOOK_SETUP_CHECKLIST.md`
4. `CURSOR_NOTEBOOK_HANDOFF_PROMPT.md`

## ノートPC側の最初の到達目標

1. `Python 3.10` が使える
2. `Cursor` でこのフォルダを開ける
3. 必要な Python パッケージが入る
4. `.env` を配置できる
5. 起動確認できる
6. スリープしない設定にできる

## ノートPC側の運用方針

- GPU は不要
- CPU-only で運用可能
- ただし、常時給電・スリープ無効・通信安定が必須
- 本番運用前に `Qwen_Status_Check.bat` か同等確認を実行すること

## Cursor セッション再開ルール

ノートPC側の新しい `Cursor` セッションでは、最初に次を伝える:

- `LAPTOP_MIGRATION_HANDOFF.md`
- `PROJECT_STATUS.md`
- `NOTEBOOK_SETUP_CHECKLIST.md`
- `CURSOR_NOTEBOOK_HANDOFF_PROMPT.md`

を読んだうえで、ノートPCでセットアップと稼働確認を継続すること。

## 注意点

- `.env` は絶対にコミットしない
- `pythonw.exe` の重複起動を避ける
- スリープ・休止・自動再起動の設定を確認する
- `trade_state_unified.json` は実運用状態ファイルなので、古いものを無造作に上書きしない

## 参考ファイル

- `PROJECT_STATUS.md`
- `AGENTS.md`
- `CLAUDE.md`
- `Qwen_本番自動売買_起動.bat`
- `Qwen_Status_Check.bat`
- `MASTER_LAUNCHER.bat`
