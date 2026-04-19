@echo off
setlocal enabledelayedexpansion
title BTC Trading Chart Viewer

echo ============================================================
echo  BTC/USDT Trading Chart Viewer
echo ============================================================
echo.
echo Generating chart...
echo.

cd /d "%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

echo [OK] Python found
echo.

python trade_chart.py
set PYTHON_EXIT=%ERRORLEVEL%

echo.

if %PYTHON_EXIT% NEQ 0 (
    echo ============================================================
    echo [ERROR] Failed to generate chart
    echo ============================================================
    pause
    exit /b 1
)

echo ============================================================
echo [OK] Chart opened in browser
echo ============================================================
echo.
pause
