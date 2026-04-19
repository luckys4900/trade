# PowerShell version - more reliable
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $scriptPath

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  BTC/USDT 4H ADAPTIVE RSI v5 - OFFLINE BACKTEST" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press any key to start..." -ForegroundColor Green
Write-Host ""

$null = $Host.UI.RawUI.ReadKey("Press any key to continue...")

Write-Host ""
Write-Host "Starting offline backtest..." -ForegroundColor Yellow
Write-Host ""

python -u force_run_hl_offline.py --mode backtest --days 180

Write-Host ""
Write-Host "Backtest completed." -ForegroundColor Yellow
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("Press any key to exit...")
