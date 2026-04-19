@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title BTC Trading Bot - Google Cloud Deploy

echo.
echo ================================================================================
echo BTC Short Trading Bot - Google Cloud Auto-Deploy
echo ================================================================================
echo.

cd /d "%~dp0"

python start_cloud_deployment.py

if !errorlevel! equ 0 (
    echo.
    echo ================================================================================
    echo [OK] Deployment Completed Successfully!
    echo ================================================================================
    echo.
    echo Your trading bot is now running in Google Cloud!
    echo The bot will execute automatically every hour.
    echo.
    echo To monitor the bot from your PC:
    echo   python cloud_monitor.py --stats
    echo.
    pause
) else (
    echo.
    echo ================================================================================
    echo [ERROR] Deployment Failed
    echo ================================================================================
    echo.
    pause
    exit /b 1
)
