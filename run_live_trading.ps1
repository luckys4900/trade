# PowerShell script to start live trading
# This script is recommended for better reliability

# Set execution policy
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  BTC/USDT 4H RSI SWING v6 - HYPERLIQUID LIVE (hl_rsi_swing_v6.py)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  WARNING: This will execute REAL MONEY trades!" -ForegroundColor Red
Write-Host "  IMPORTANT: Start with small amounts to minimize risk!" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Press any key to start LIVE mode..." -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop trading." -ForegroundColor Green
Write-Host ""
Write-Host "  Logs: rsi_swing_*.log (project folder)" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# Wait for user confirmation
$null = $Host.UI.RawUI.ReadKey("Press any key to continue...")

Write-Host ""
Write-Host "Starting trading bot..." -ForegroundColor Yellow
Write-Host ""

# Change to script directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $scriptPath

# Run the trading bot
python -u hl_rsi_swing_v6.py

Write-Host ""
Write-Host "Trading bot stopped." -ForegroundColor Yellow
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("Press any key to exit...")
