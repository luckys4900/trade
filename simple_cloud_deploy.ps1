# BTC Trading Bot - Google Cloud Simple Deploy Script (PowerShell)
# 日本語対応版

$ErrorActionPreference = "Stop"

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "BTC Short Trading Bot - Google Cloud Auto-Deploy" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# ステップ 1: gcloud インストール確認
Write-Host "`n[ステップ 1/8] Google Cloud SDK チェック" -ForegroundColor Yellow

$gcloud = gcloud --version 2>$null
if ($gcloud) {
    Write-Host "[OK] Google Cloud SDK はインストール済み" -ForegroundColor Green
} else {
    Write-Host "[インストール] Google Cloud SDK をセットアップ中..." -ForegroundColor Yellow

    # Scoop でインストール
    iwr -useb get.scoop.sh | iex
    scoop bucket add extras
    scoop install gcloud

    Write-Host "[OK] Google Cloud SDK インストール完了" -ForegroundColor Green
}

# ステップ 2: Google Cloud 認証
Write-Host "`n[ステップ 2/8] Google Cloud に認証" -ForegroundColor Yellow
Write-Host "ブラウザが開きます。Google アカウントでログインしてください..." -ForegroundColor Cyan

gcloud auth login

Write-Host "[OK] 認証完了" -ForegroundColor Green

# ステップ 3: プロジェクト確認/設定
Write-Host "`n[ステップ 3/8] Google Cloud プロジェクト設定" -ForegroundColor Yellow

$projectId = gcloud config get-value project 2>$null
if ($projectId) {
    Write-Host "[OK] プロジェクト: $projectId" -ForegroundColor Green
} else {
    Write-Host "プロジェクト一覧:" -ForegroundColor Yellow
    gcloud projects list

    Write-Host "`nプロジェクトが設定されていません。" -ForegroundColor Red
    Write-Host "以下を実行してください:" -ForegroundColor Cyan
    Write-Host "  gcloud config set project YOUR_PROJECT_ID"
    exit 1
}

# ステップ 4: API 有効化
Write-Host "`n[ステップ 4/8] Google Cloud API を有効化" -ForegroundColor Yellow

$apis = @(
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "logging.googleapis.com"
)

foreach ($api in $apis) {
    Write-Host "有効化中: $api..." -ForegroundColor Gray
    gcloud services enable $api --quiet 2>$null
}

Write-Host "[OK] API 有効化完了" -ForegroundColor Green

# ステップ 5: ビルド＆デプロイ
Write-Host "`n[ステップ 5/8] Docker イメージをビルド＆デプロイ（3-5分待機）" -ForegroundColor Yellow

$tradeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
cd $tradeDir

$imageName = "us-central1-docker.pkg.dev/$projectId/btc-trading-bot/btc-bot"

Write-Host "Artifact Registry リポジトリを作成..." -ForegroundColor Gray
gcloud artifacts repositories create btc-trading-bot `
    --repository-format=docker `
    --location=us-central1 `
    --quiet 2>$null || Write-Host "（既存のリポジトリを使用）" -ForegroundColor Gray

Write-Host "Docker を認証..." -ForegroundColor Gray
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

Write-Host "Docker イメージをビルド中..." -ForegroundColor Gray
docker build -t "$imageName" .

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker ビルド失敗" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] ビルド完了" -ForegroundColor Green

# ステップ 6: Docker プッシュ
Write-Host "`n[ステップ 6/8] Google Cloud にアップロード（2-5分待機）" -ForegroundColor Yellow

Write-Host "Docker イメージをプッシュ中..." -ForegroundColor Gray
docker push "$imageName"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker プッシュ失敗" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] アップロード完了" -ForegroundColor Green

# ステップ 7: Cloud Run デプロイ
Write-Host "`n[ステップ 7/8] Cloud Run にデプロイ" -ForegroundColor Yellow

Write-Host "Cloud Run にデプロイ中..." -ForegroundColor Gray
gcloud run deploy btc-trading-bot `
    --image=$imageName `
    --region=us-central1 `
    --memory=512Mi `
    --timeout=300 `
    --no-allow-unauthenticated `
    --quiet

Write-Host "[OK] Cloud Run デプロイ完了" -ForegroundColor Green

# Service URL を取得
$serviceUrl = gcloud run services describe btc-trading-bot `
    --region=us-central1 `
    --format="value(status.url)"

Write-Host "Service URL: $serviceUrl" -ForegroundColor Cyan

# ステップ 8: Cloud Scheduler 設定
Write-Host "`n[ステップ 8/8] Cloud Scheduler で自動実行設定" -ForegroundColor Yellow

Write-Host "Cloud Scheduler ジョブを作成中..." -ForegroundColor Gray

# 既存ジョブを削除
gcloud scheduler jobs delete btc-bot-hourly --location=us-central1 --quiet 2>$null || Write-Host ""

# 新しいジョブを作成
gcloud scheduler jobs create http btc-bot-hourly `
    --schedule="0 * * * *" `
    --uri="$serviceUrl" `
    --http-method=POST `
    --location=us-central1 `
    --oidc-service-account-email=default@appspot.gserviceaccount.com `
    --quiet

Write-Host "[OK] Cloud Scheduler 設定完了" -ForegroundColor Green

# 完了
Write-Host "`n================================================================================" -ForegroundColor Green
Write-Host "[OK] デプロイ完了！" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green

Write-Host @"
【設定情報】
  プロジェクト: $projectId
  サービス: btc-trading-bot
  リージョン: us-central1
  URL: $serviceUrl

【実行スケジュール】
  毎時00分に自動実行（例: 14:00, 15:00, 16:00...）

【PC から監視する場合】
  python cloud_monitor.py --stats

これであなたのボットは Google Cloud で 24/7 自動実行中です！🚀
PC を起動する必要はありません。

"@ -ForegroundColor Cyan

Write-Host "================================================================================" -ForegroundColor Green
