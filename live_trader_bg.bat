@echo off

chcp 65001 >nul

title BTC/USDT 4H RSI SWING v6 - LIVE (Background)



echo ============================================================

echo  BTC/USDT 4H RSI SWING v6 - LIVE TRADER (Background)

echo ============================================================

echo.

echo Starting hl_rsi_swing_v6.py in a minimized window...

echo Log: rsi_swing_*.log

echo.

echo ============================================================

echo.



cd /d "%~dp0"



where python >nul 2>&1

if %ERRORLEVEL% NEQ 0 (

    echo [ERROR] Python not found in PATH

    pause

    exit /b 1

)



start "HL_RSI_SWING_V6" /MIN python hl_rsi_swing_v6.py



echo.

echo Trader started. To stop: Task Manager (python.exe) or stop_trader_all.bat

echo.

pause

