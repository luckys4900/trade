@echo off
chcp 65001 >nul
title Check Live Trader Status

echo ============================================================
echo  BTC/USDT 4H Adaptive RSI v5 - Status Checker
echo ============================================================
echo.

set latest_log=
set max_date=0

REM Find latest log file
for %%f in (logs\live_trade_*.log) do (
    set "filename=%%f"
    for /f "tokens=1-4 delims=/-" %%a in ("%%f") do (
        set /a date_val=%%a*10000+%%b*100+%%c
        if !date_val! gtr %max_date% (
            set "max_date=!date_val!"
            set "latest_log=%%f"
        )
    )
)

if "%latest_log%"=="" (
    echo [WARNING] No log files found!
    echo.
    echo Starting trader for the first time...
    echo ============================================================
    echo.
    echo Press any key to start the trader...
    pause >nul
    start_live_trader_bg.bat
    goto :eof
)

echo Latest log: %latest_log%
echo.

REM Show last 20 lines of the log
echo Last 20 lines of log:
echo ============================================================
powershell -Command "Get-Content '%latest_log%' | Select-Object -Last 20"
echo ============================================================
echo.

REM Show some statistics
echo Statistics from this log:
powershell -Command "$content = Get-Content '%latest_log%'; $info = $content | Select-String 'INFO'; $errors = $content | Select-String 'ERROR'; Write-Host 'Total INFO messages:' $info.Count; Write-Host 'Total ERROR messages:' $errors.Count"

echo.
echo To see full log, open: %latest_log%
echo To start trading, run: start_live_trader_bg.bat
echo To stop trading, press Ctrl+C in the trader window
echo.
pause
