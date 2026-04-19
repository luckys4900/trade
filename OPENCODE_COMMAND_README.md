# GLM Agent Teams - OpenCode内コマンド設定

## 概要
opencode内で「agentteams」と入力するとGLMエージェントシステムが起動します。

## 設定方法

### 1. 一度だけ実行（コマンド設定）
```bash
python setup_agentteams_command.py
```

### 2. 使用方法
```bash
agentteams              # GLMエージェントシステムを起動
agentteams status       # 状態を確認
agentteams stop         # システムを停止
agentteams help         # ヘルプを表示
```

## 機能

### 環境チェック
- `.env`ファイルの存在確認
- Pythonのバージョン確認
- openai-swarmライブラリの自動インストール
- Ollamaサービスの確認

### システム管理
- 起動: `agentteams start`
- 状態確認: `agentteams status`
- 停止: `agentteams stop`
- ヘルプ: `agentteams help`

### 自動化
- PC起動時に自動で起動可能
- バックグラウンド実行
- エラー処理と自動修復

## 注意事項

- 初回実行時に`.env`ファイルがなければ自動で作成
- 必要なライブラリがなければ自動でインストール
- Ollamaが起動していなければ警告を表示
- Windows環境で動作確認済み