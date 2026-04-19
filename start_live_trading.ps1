# Start Live Trading Bot (PowerShell version)

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  BTC/USDT 4H RSI SWING v6 - HYPERLIQUID LIVE (hl_rsi_swing_v6.py)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  WARNING: This will execute REAL MONEY trades!" -ForegroundColor Red
Write-Host "  IMPORTANT: Start with small amounts to minimize risk!" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Press Enter to start LIVE mode..." -ForegroundColor Green
Write-Host "  Ctrl+C to stop." -ForegroundColor Green
Write-Host ""
Write-Host "  Logs: rsi_swing_*.log (project folder)" -ForegroundColor Gray
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

$null = Read-Host

Write-Host ""
Write-Host "Checking dependencies..." -ForegroundColor Yellow
Write-Host ""

Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)

python -u hl_rsi_swing_v6.py

Write-Host ""
Write-Host "Program stopped." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to exit..."
