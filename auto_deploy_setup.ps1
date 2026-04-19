# Google Cloud SDK インストール + デプロイ自動化 (PowerShell)
# 実行方法: powershell -ExecutionPolicy Bypass -File auto_deploy_setup.ps1

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Google Cloud Auto-Deploy Setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Step 1: gcloud をインストール（チェック）
Write-Host "`n[Step 1/4] Google Cloud SDK をインストール中..." -ForegroundColor Yellow
$gcloud = Get-Command gcloud -ErrorAction SilentlyContinue

if ($null -eq $gcloud) {
    Write-Host "gcloud が見つかりません。インストール中..." -ForegroundColor Yellow

    # scoop でインストール
    $scoop = Get-Command scoop -ErrorAction SilentlyContinue

    if ($null -eq $scoop) {
        Write-Host "Scoop をインストール中..." -ForegroundColor Yellow
        iwr -useb get.scoop.sh | iex
    }

    Write-Host "gcloud をインストール中（2-3分かかります）..." -ForegroundColor Yellow
    scoop install gcloud

    # パスを更新
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
} else {
    Write-Host "[OK] gcloud はすでにインストール済み" -ForegroundColor Green
}

# Step 2: gcloud 認証
Write-Host "`n[Step 2/4] Google Cloud に認証中..." -ForegroundColor Yellow
Write-Host "ブラウザが開きます。Google アカウントでログインしてください。" -ForegroundColor Cyan

gcloud auth login --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 認証に失敗しました" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] 認証完了" -ForegroundColor Green

# Step 3: プロジェクト ID を確認
Write-Host "`n[Step 3/4] Google Cloud プロジェクトを設定中..." -ForegroundColor Yellow

$projectId = gcloud config get-value project
if ([string]::IsNullOrEmpty($projectId)) {
    Write-Host "プロジェクトが設定されていません。`n以下をコンソールで実行してください:" -ForegroundColor Red
    Write-Host "gcloud projects list" -ForegroundColor Cyan
    Write-Host "gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Cyan
    exit 1
}

Write-Host "[OK] プロジェクト: $projectId" -ForegroundColor Green

# Step 4: Docker を確認
Write-Host "`n[Step 4/4] Docker をチェック中..." -ForegroundColor Yellow

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    Write-Host "[ERROR] Docker がインストールされていません" -ForegroundColor Red
    Write-Host "Docker Desktop をインストールしてください: https://www.docker.com/products/docker-desktop" -ForegroundColor Cyan
    exit 1
}

Write-Host "[OK] Docker はインストール済み" -ForegroundColor Green

# Step 5: デプロイ実行
Write-Host "`n================================" -ForegroundColor Green
Write-Host "準備完了！デプロイを開始します..." -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

$tradeDir = "C:\Users\user\Desktop\cursor\trade"
cd $tradeDir

# deploy_to_cloud.py を実行
Write-Host "`nPython デプロイスクリプトを実行中..." -ForegroundColor Yellow
python deploy_to_cloud.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n================================" -ForegroundColor Green
    Write-Host "✓ デプロイ完了！" -ForegroundColor Green
    Write-Host "================================" -ForegroundColor Green
    Write-Host "クラウドボットは1時間ごとに自動実行されます。`nPC を起動せずに 24/7 自動トレード中です。" -ForegroundColor Cyan
    Write-Host "`n監視コマンド:" -ForegroundColor Yellow
    Write-Host "python cloud_monitor.py --stats" -ForegroundColor Cyan
} else {
    Write-Host "`n[ERROR] デプロイに失敗しました" -ForegroundColor Red
    exit 1
}
