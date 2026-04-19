# Google Cloud 自動デプロイガイド

## 概要

このガイドでは、Google Cloud Run にBTCショートトレーディングボットを**自動でデプロイ**する方法を説明します。

PCへの追加インストール不要で、**完全自動化**されたセットアップです。

---

## 🚀 クイックスタート（推奨）

### Windows ユーザー

**最も簡単な方法：バッチファイルで実行**

```bash
# コマンドプロンプトまたは PowerShell で実行
cd C:\Users\user\Desktop\cursor\trade
deploy.bat
```

または

```bash
python start_cloud_deployment.py
```

### Mac/Linux ユーザー

```bash
cd ~/Desktop/cursor/trade
python3 start_cloud_deployment.py
```

---

## 📋 スクリプトの動作

### `start_cloud_deployment.py` が自動的に行う処理

1. **gcloud SDK のインストール確認**
   - インストール済みなら → スキップ
   - 未インストールなら → インストール方法を表示

2. **Google Cloud 認証**
   - ブラウザで Google アカウントにログイン

3. **プロジェクト確認**
   - Google Cloud プロジェクトが設定されているか確認

4. **Docker 確認**
   - Docker がインストール済みか確認

5. **自動デプロイ実行**
   - `deploy_to_cloud.py` を実行
   - Docker イメージをビルド
   - Google Cloud Artifact Registry にプッシュ
   - Cloud Run にデプロイ
   - Cloud Scheduler で毎時実行を設定

---

## 🔧 必要な準備（初回のみ）

### 1. Google Cloud アカウント作成

```
https://cloud.google.com → 「無料で始める」をクリック
```

**無料クレジット**: $300（有効期間3か月）

### 2. Google Cloud プロジェクト作成

**方法A: Cloud Console で作成（推奨）**
```
1. https://console.cloud.google.com にアクセス
2. 画面上部「プロジェクトを選択」
3. 「新規プロジェクト」
4. 名前: "BTC-Trading-Bot"
5. 「作成」をクリック
```

**方法B: gcloud CLI で作成**
```bash
gcloud projects create btc-trading-bot
gcloud config set project btc-trading-bot
```

### 3. Docker Desktop インストール

```
https://www.docker.com/products/docker-desktop
```

---

## ⚙️ デプロイ実行

### ステップ 1: スクリプト実行

```bash
cd C:\Users\user\Desktop\cursor\trade
deploy.bat
```

または

```bash
python start_cloud_deployment.py
```

### ステップ 2: ブラウザで認証

スクリプトが自動的にブラウザを開きます → Google アカウントでログイン

### ステップ 3: 自動デプロイ開始

スクリプトが以下を自動実行：
- gcloud 認証
- Docker イメージビルド
- Cloud Artifact Registry へプッシュ
- Cloud Run へデプロイ
- Cloud Scheduler で毎時実行を設定

**実行時間**: 5-10 分

### ステップ 4: デプロイ完了確認

スクリプト完了後、以下のメッセージが表示：
```
================================================================================
[OK] Deployment Completed Successfully!
================================================================================
Your trading bot is now running in Google Cloud!
```

---

## 📊 デプロイ後の確認

### Cloud Console で確認

```
1. https://console.cloud.google.com にアクセス
2. 左メニュー → Cloud Run
3. 「btc-trading-bot」サービスが表示
4. 「ログ」タブで実行ログを確認
```

### Python で監視

```bash
python cloud_monitor.py --stats
```

出力例：
```
================================================================================
CLOUD BOT MONITOR DASHBOARD
================================================================================

[STATUS]
  [LIVE] Mode: LIVE
  [LAST] Execution: 2026-03-18 05:07:12

[MARKET INFO]
  [PRICE] $74,425.00
  [RSI] 54.6 [NORMAL]
  [BALANCE] 199.12 USDC

[LATEST SIGNAL]
  [ENTRY] SHORT

[ENTRY HISTORY - Recent 5]
  - 2026-03-18 02:15:30 : SHORT ENTRY
  - 2026-03-18 02:16:00 : PROFIT TARGET

[STATISTICS]
  Total Executions: 24 times
  Entry Count: 5 entries
  Error Count: 0 errors
```

---

## 🐛 トラブルシューティング

### エラー: "gcloud not found"

**原因**: Google Cloud SDK がインストールされていない

**解決方法**:
```bash
# scoop でインストール
scoop install gcloud

# または、手動でダウンロード:
# https://cloud.google.com/sdk/docs/install
```

### エラー: "Project not found"

**原因**: Google Cloud プロジェクトが設定されていない

**解決方法**:
```bash
gcloud projects list
gcloud config set project YOUR_PROJECT_ID
```

### エラー: "Docker not installed"

**原因**: Docker がインストールされていない

**解決方法**:
```
Docker Desktop をダウンロード:
https://www.docker.com/products/docker-desktop
```

### エラー: "Authentication failed"

**原因**: Google Cloud 認証失敗

**解決方法**:
```bash
gcloud auth login
gcloud auth application-default login
```

### デプロイ完了したが、ボットが実行されない

**確認事項**:
```bash
# 1. Cloud Run サービスが起動したか確認
gcloud run services describe btc-trading-bot --region us-central1

# 2. Cloud Scheduler ジョブが設定されているか確認
gcloud scheduler jobs describe btc-bot-hourly --location us-central1

# 3. ログを確認
python cloud_monitor.py --minutes 1440
```

---

## 🛑 デプロイのキャンセル・削除

### Cloud Run サービスを削除

```bash
gcloud run services delete btc-trading-bot --region us-central1 --quiet
```

### Cloud Scheduler ジョブを削除

```bash
gcloud scheduler jobs delete btc-bot-hourly --location us-central1 --quiet
```

### Artifact Registry イメージを削除

```bash
gcloud artifacts docker images delete \
  us-central1-docker.pkg.dev/YOUR_PROJECT_ID/btc-trading-bot/btc-bot \
  --delete-tags
```

---

## 💰 月額費用

```
Google Cloud 無料枠内（ほぼ$0）:
  - Cloud Run: 月200万リクエストまで無料
  - Cloud Scheduler: 月3個のジョブまで無料
  - Cloud Logging: 月50GB まで無料

このボット設定での月額実行:
  = 1時間ごと × 24時間 × 30日
  = 720リクエスト
  = $0 （無料枠内）
```

---

## 📞 サポート

### 一般的な質問

**Q: PCを起動してないとボットは実行されないのか？**
- A: いいえ。Cloud Run で実行されるため、PC不要です。

**Q: ボットはいつ実行されるのか？**
- A: 毎時00分に実行されます（例: 14:00, 15:00, 16:00...）

**Q: デプロイはやり直せるのか？**
- A: はい。`deploy.bat` または `python start_cloud_deployment.py` を再実行できます。

**Q: config.json を変更したら？**
- A: ファイルを更新した後、スクリプトを再実行してください。

---

## ✅ チェックリスト

- [ ] Google Cloud アカウント作成
- [ ] Google Cloud プロジェクト作成
- [ ] Docker Desktop インストール
- [ ] `deploy.bat` または `python start_cloud_deployment.py` 実行
- [ ] ブラウザで Google アカウントにログイン
- [ ] デプロイ完了までの5-10分待機
- [ ] `python cloud_monitor.py --stats` で動作確認
- [ ] 毎時実行ログを確認

---

**これで PC を起動せず、24/7 自動トレード開始！** 🎉
