@echo off

chcp 65001 >nul

title BTC/USDT 4H RSI SWING v6 - LIVE TRADER



echo ============================================================

echo  BTC/USDT 4H RSI SWING v6 - LIVE TRADER (only)

echo ============================================================

echo.

echo Starting trading bot...

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

python -c "import requests, pandas, numpy" >nul 2>&1

if %errorlevel% neq 0 (

    echo Installing required modules...

    pip install requests pandas numpy

)



echo.

echo Starting RSI Swing v6 live trader (hl_rsi_swing_v6.py)...

start "HL_RSI_SWING_V6" python hl_rsi_swing_v6.py



echo.

echo Trader launched in a separate window.

echo You can close this launcher window now if you like.

echo.

pause

