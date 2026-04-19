# Google Cloud Run での自動化ガイド

**目標:** PCを起動せず、クラウドで24/7 自動監視

---

## 🚀 セットアップ手順（5分で完了）

### ステップ 1: Google Cloud アカウント作成

```
1. https://cloud.google.com にアクセス
2. 「無料で始める」をクリック
3. Google アカウントでログイン
4. 無料クレジット $300 を取得
```

**注:** 月200万リクエストまで無料

---

### ステップ 2: Google Cloud プロジェクト作成

```
1. Cloud Console にアクセス
   https://console.cloud.google.com

2. 画面上部の「プロジェクトを選択」をクリック
3. 「新規プロジェクト」をクリック
4. プロジェクト名を入力（例: "BTC-Trading-Bot"）
5. 「作成」をクリック
```

---

### ステップ 3: 必要なAPI を有効化

```bash
# Cloud Run API を有効化
gcloud services enable run.googleapis.com

# Cloud Build API を有効化
gcloud services enable cloudbuild.googleapis.com

# Cloud Scheduler API を有効化
gcloud services enable cloudscheduler.googleapis.com
```

---

### ステップ 4: Docker イメージをデプロイ

```bash
# ローカルで確認（オプション）
docker build -t btc-trading-bot .
docker run btc-trading-bot

# Google Artifact Registry にプッシュ
gcloud auth configure-docker us-central1-docker.pkg.dev

docker tag btc-trading-bot us-central1-docker.pkg.dev/PROJECT_ID/trading-bot/btc-bot
docker push us-central1-docker.pkg.dev/PROJECT_ID/trading-bot/btc-bot
```

---

### ステップ 5: Cloud Run にデプロイ

```bash
gcloud run deploy btc-trading-bot \
  --image us-central1-docker.pkg.dev/PROJECT_ID/trading-bot/btc-bot \
  --region us-central1 \
  --memory 512Mi \
  --timeout 300 \
  --no-allow-unauthenticated
```

**出力例:**
```
Service [btc-trading-bot] revision [000001] has been deployed to Cloud Run.
Service URL: https://btc-trading-bot-xxxxx.run.app
```

---

### ステップ 6: Cloud Scheduler で自動実行を設定

```bash
# 1時間ごとに実行するスケジュールを作成
gcloud scheduler jobs create http btc-bot-hourly \
  --schedule="0 * * * *" \
  --uri="https://btc-trading-bot-xxxxx.run.app" \
  --http-method=POST \
  --location=us-central1 \
  --oidc-service-account-email=SERVICE_ACCOUNT@PROJECT_ID.iam.gserviceaccount.com
```

---

## 📊 実行フロー

```
Cloud Scheduler (毎時実行)
         ↓
Cloud Run (Docker コンテナ)
         ↓
short_trading_bot_cloud.py
         ↓
Hyperliquid API
         ↓
ショート取引実行
         ↓
Cloud Logging (ログ保存)
```

---

## 🔍 ログの確認

```bash
# リアルタイムログを表示
gcloud run services describe btc-trading-bot --region us-central1

# ログスト リームを表示
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=btc-trading-bot" \
  --limit 50 \
  --format json
```

**または Cloud Console で確認:**
```
Cloud Run → btc-trading-bot → ログ
```

---

## 💰 費用（ほぼ無料）

```
【月額費用】
- Cloud Run: 月200万リクエストまで無料
- Cloud Scheduler: 月3個のジョブまで無料
- Cloud Logging: 月50GB まで無料

【この設定での月額費用】
= 1時間ごと × 24時間 × 30日 = 720リクエスト
= $0 （無料枠内）
```

---

## ⚙️ 設定ファイル

`config.json` をクラウドで使用するには：

```json
{
  "secret_key": "0x...",
  "account_address": "0x...",
  "live_trading": true,
  "paper_mode": false,
  "environment": "mainnet",
  "symbol": "BTC",
  "timeframe": "1h",
  "rsi_overbought": 60,
  "profit_target_pct": 0.003,
  "stop_loss_pct": 0.01,
  "max_hold_bars": 10,
  "leverage": 1,
  "check_interval": 60,
  "initial_capital": 100,
  "position_size_pct": 0.5,
  "max_daily_loss_pct": 0.05,
  "manual_balance": 199.12,
  "manual_balance_enabled": true
}
```

---

## 🎯 監視とアラート

```bash
# エラーが発生した場合の通知を設定
# Cloud Run → トリガー → 通知を追加
```

---

## 🛑 停止・削除

```bash
# サービスを削除
gcloud run services delete btc-trading-bot --region us-central1

# スケジューラジョブを削除
gcloud scheduler jobs delete btc-bot-hourly --location us-central1
```

---

## ✅ チェックリスト

- [ ] Google Cloud アカウント作成
- [ ] プロジェクト作成
- [ ] API 有効化
- [ ] config.json に API credentials 設定
- [ ] Docker イメージをビルド＆プッシュ
- [ ] Cloud Run にデプロイ
- [ ] Cloud Scheduler で自動実行設定
- [ ] ログで正常実行を確認
- [ ] アラート通知を設定

---

## 📞 トラブルシューティング

### Docker ビルドエラー

```bash
# 依存パッケージのキャッシュをクリア
docker system prune -a

# 再度ビルド
docker build -t btc-trading-bot .
```

### Cloud Run が 時間切れ エラー

```bash
# タイムアウトを延長
gcloud run deploy btc-trading-bot \
  --timeout 600  # 10分に設定
```

### Cloud Scheduler が実行されない

```bash
# 実行ログを確認
gcloud scheduler jobs describe btc-bot-hourly --location us-central1

# 手動実行をテスト
gcloud scheduler jobs run btc-bot-hourly --location us-central1
```

---

**これで 24/7 自動化が完成！** 🎉
