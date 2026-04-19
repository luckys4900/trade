# BTC Trading Bot - Cloud Deploy (PowerShell 5.1 Compatible)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "`n================================" -ForegroundColor Cyan
Write-Host "BTC Trading Bot - Cloud Deploy" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Step 1: Check gcloud
Write-Host "`n[Step 1/8] Check Google Cloud SDK" -ForegroundColor Yellow

$gcloud = gcloud --version 2>$null
if ($gcloud) {
    Write-Host "[OK] Google Cloud SDK installed" -ForegroundColor Green
} else {
    Write-Host "[Install] Installing Google Cloud SDK..." -ForegroundColor Yellow

    $ErrorActionPreference = "Stop"
    try {
        iwr -useb get.scoop.sh | iex
        scoop bucket add extras
        scoop install gcloud
        Write-Host "[OK] Installation complete" -ForegroundColor Green
    }
    catch {
        Write-Host "[ERROR] Installation failed" -ForegroundColor Red
        Write-Host "Please install Google Cloud SDK manually:" -ForegroundColor Cyan
        Write-Host "  https://cloud.google.com/sdk/docs/install"
        exit 1
    }
    $ErrorActionPreference = "SilentlyContinue"
}

# Step 2: Authenticate
Write-Host "`n[Step 2/8] Authenticate with Google Cloud" -ForegroundColor Yellow
Write-Host "Browser will open. Login with your Google account." -ForegroundColor Cyan

$ErrorActionPreference = "Stop"
try {
    gcloud auth login
    Write-Host "[OK] Authentication complete" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Authentication failed" -ForegroundColor Red
    exit 1
}
$ErrorActionPreference = "SilentlyContinue"

# Step 3: Get project
Write-Host "`n[Step 3/8] Configure Google Cloud project" -ForegroundColor Yellow

$projectId = gcloud config get-value project 2>$null
if ($projectId) {
    Write-Host "[OK] Project: $projectId" -ForegroundColor Green
} else {
    Write-Host "Available projects:" -ForegroundColor Yellow
    gcloud projects list
    Write-Host "[ERROR] Project not set" -ForegroundColor Red
    Write-Host "Run: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Cyan
    exit 1
}

# Step 4: Enable APIs
Write-Host "`n[Step 4/8] Enable Google Cloud APIs" -ForegroundColor Yellow

$apis = @("run.googleapis.com", "cloudbuild.googleapis.com", "artifactregistry.googleapis.com", "cloudscheduler.googleapis.com", "logging.googleapis.com")

foreach ($api in $apis) {
    Write-Host "Enabling $api..." -ForegroundColor Gray
    gcloud services enable $api --quiet 2>$null
}

Write-Host "[OK] APIs enabled" -ForegroundColor Green

# Step 5: Build Docker image
Write-Host "`n[Step 5/8] Build Docker image (3-5 min wait)" -ForegroundColor Yellow

$tradeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
cd $tradeDir

$imageName = "us-central1-docker.pkg.dev/$projectId/btc-trading-bot/btc-bot"

Write-Host "Creating Artifact Registry repository..." -ForegroundColor Gray
gcloud artifacts repositories create btc-trading-bot --repository-format=docker --location=us-central1 --quiet 2>$null

Write-Host "Configuring Docker..." -ForegroundColor Gray
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

Write-Host "Building Docker image..." -ForegroundColor Gray

$ErrorActionPreference = "Stop"
try {
    docker build -t $imageName .
    Write-Host "[OK] Build complete" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Docker build failed" -ForegroundColor Red
    exit 1
}
$ErrorActionPreference = "SilentlyContinue"

# Step 6: Push image
Write-Host "`n[Step 6/8] Upload to Google Cloud (2-5 min wait)" -ForegroundColor Yellow

Write-Host "Pushing Docker image..." -ForegroundColor Gray

$ErrorActionPreference = "Stop"
try {
    docker push $imageName
    Write-Host "[OK] Upload complete" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Docker push failed" -ForegroundColor Red
    exit 1
}
$ErrorActionPreference = "SilentlyContinue"

# Step 7: Deploy to Cloud Run
Write-Host "`n[Step 7/8] Deploy to Cloud Run" -ForegroundColor Yellow

Write-Host "Deploying to Cloud Run..." -ForegroundColor Gray

$ErrorActionPreference = "Stop"
try {
    gcloud run deploy btc-trading-bot --image=$imageName --region=us-central1 --memory=512Mi --timeout=300 --no-allow-unauthenticated --quiet
    Write-Host "[OK] Deployment complete" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Cloud Run deployment failed" -ForegroundColor Red
    exit 1
}
$ErrorActionPreference = "SilentlyContinue"

# Get service URL
$serviceUrl = gcloud run services describe btc-trading-bot --region=us-central1 --format="value(status.url)"
Write-Host "Service URL: $serviceUrl" -ForegroundColor Cyan

# Step 8: Setup Cloud Scheduler
Write-Host "`n[Step 8/8] Setup Cloud Scheduler" -ForegroundColor Yellow

Write-Host "Creating scheduler job..." -ForegroundColor Gray

gcloud scheduler jobs delete btc-bot-hourly --location=us-central1 --quiet 2>$null

$ErrorActionPreference = "Stop"
try {
    gcloud scheduler jobs create http btc-bot-hourly --schedule="0 * * * *" --uri="$serviceUrl" --http-method=POST --location=us-central1 --oidc-service-account-email=default@appspot.gserviceaccount.com --quiet
    Write-Host "[OK] Scheduler configured" -ForegroundColor Green
}
catch {
    Write-Host "[WARNING] Scheduler setup may need additional permissions" -ForegroundColor Yellow
}
$ErrorActionPreference = "SilentlyContinue"

# Complete
Write-Host "`n================================" -ForegroundColor Green
Write-Host "[OK] Deployment Complete!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

Write-Host "`n[Settings]" -ForegroundColor Cyan
Write-Host "  Project: $projectId"
Write-Host "  Service: btc-trading-bot"
Write-Host "  Region: us-central1"
Write-Host "  URL: $serviceUrl"

Write-Host "`n[Schedule]" -ForegroundColor Cyan
Write-Host "  Executes every hour at :00 (14:00, 15:00, etc)"

Write-Host "`n[Monitor from PC]" -ForegroundColor Cyan
Write-Host "  python cloud_monitor.py --stats"

Write-Host "`nYour bot is running 24/7 in Google Cloud! No PC needed." -ForegroundColor Green
Write-Host "================================`n" -ForegroundColor Green
