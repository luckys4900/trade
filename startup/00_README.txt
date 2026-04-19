============================================================
  Whale Monitoring System - Operation Guide
  クジラ監視システム 操作ガイド
============================================================

このフォルダは、Hyperliquid自動売買ボットの起動・停止・確認用スクリプトです。

【使用順序】

1. 最初の起動:
   >> 01_クジラ監視システム起動.bat

2. 状態確認（いつでも実行可能）:
   >> 03_システム状態確認.bat

   表示内容：
   - 実行中のプロセス
   - whale_signal.json (クジラ監視信号)
   - macro_state.json (ボラティリティ状態)
   - 最新ログ

3. 完全停止:
   >> 04_全システム停止.bat


【稼働システム】

✓ whale_monitor.py
  - 15分ごとにクジラウォレットのポジションを監視
  - whale_signal.json を生成

✓ macro_filter.py
  - 60分ごとにボラティリティと経済イベントを監視
  - macro_state.json を生成

✓ qwen_unified_live.py (メインボット)
  - 1分ごとにトレード判定
  - whale_signal + macro_state を読み込んでポジションサイズ決定
  - trade_alignment_log.json に記録


【ログファイル】

全ログは親ディレクトリの logs/ フォルダに保存：
- logs/unified_live_*.log      → メインボットのログ
- logs/whale_monitor_*.log     → クジラ監視のログ
- logs/macro_filter_*.log      → マクロフィルターのログ
- logs/startup_errors.log      → 起動エラー


【シグナルファイル】

親ディレクトリ直下に以下のJSONファイルが生成：
- whale_signal.json      (最新のクジラシグナル)
- macro_state.json       (最新のマクロ状態)
- trade_alignment_log.json (トレード記録)
- trade_state_unified.json (現在のポジション)


【問題解決】

Q: プロセスが起動しない
A: 03_システム状態確認.bat を実行して、logs/startup_errors.log を確認

Q: whale_signal.json が生成されない
A: 3つのウォレット設定を確認：
   親ディレクトリの whale_wallets.json を確認

Q: 手動でプロセスを停止したい
A: Task Manager (Ctrl+Shift+Esc) で python.exe/pythonw.exe を終了


【注意事項】

- このフォルダのbatファイルは、親ディレクトリの
  whale_monitor.py, macro_filter.py, qwen_unified_live.py
  が必須です

- ファイルを別の場所に移動する場合は、
  batファイル内の TRADE_DIR パスを修正してください

- 起動後、最初のシグナル生成には15-60分かかります
  （whale_monitor は15分ごと、macro_filter は60分ごと）


【ファイル一覧】

01_クジラ監視システム起動.bat   → 全システム起動（最初）
03_システム状態確認.bat         → 状態確認（いつでも）
04_全システム停止.bat           → 全システム停止

============================================================
