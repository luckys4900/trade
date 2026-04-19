@echo off

chcp 65001 >nul

title BTC/USDT 4H RSI SWING v6 - Trader



echo ============================================================

echo  BTC/USDT 4H RSI SWING v6 - AUTO TRADER

echo ============================================================

echo.

echo Starting automated trading...

echo.

echo Mode: LIVE TRADING

echo Log: rsi_swing_*.log

echo.



REM Set working directory

cd /d "%~dp0"



REM Check if Python exists

where python >nul 2>&1

if %ERRORLEVEL% NEQ 0 (

    echo [ERROR] Python not found in PATH

    echo Please install Python or add it to PATH

    pause

    exit /b 1

)



echo [OK] Python found

echo.



REM Start Python script

echo Launching trader...

echo ============================================================



python hl_rsi_swing_v6.py



echo.

echo ============================================================

echo Trader stopped

echo ============================================================

echo.

pause

