@echo off
chcp 65001 >nul
title BTC/USDT 4H ADAPTIVE RSI v5 - BACKTEST

echo ============================================================
echo  BTC/USDT 4H ADAPTIVE RSI v5 - BACKTEST
echo ============================================================
echo.
echo Starting backtest...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.10+ and try again
    pause
    exit /b
)

REM Check if required modules are installed
echo Checking required modules...
python -c "import requests, pandas, numpy, matplotlib" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing required modules...
    pip install requests pandas numpy matplotlib
)

REM Run backtest
echo.
echo Running backtest (last 180 days)...
echo.
python run_backtest.py

echo.
echo Backtest completed. Check the log for results.
echo.
pause