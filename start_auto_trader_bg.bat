@echo off
chcp 65001 >nul
title BTC Trader - Background (v6 RSI SWING)

echo ============================================================
echo  BTC/USDT RSI SWING v6 - AUTO TRADER (Background)
echo ============================================================
echo.
echo Starting automated trading in background...
echo.
echo Mode: LIVE TRADING
echo Log: rsi_swing_*.log
echo Control: Stop with stop_trader_all.bat
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

REM Start Python in background
echo Launching trader in background...
echo ============================================================

start "HL_RSI_SWING_V6" /MIN python hl_rsi_swing_v6.py

REM Wait a moment for process to start
timeout /t 3 /nobreak >nul

REM Check if process is running
tasklist /FI "WINDOWTITLE eq HL_RSI_SWING_V6*" /FO LIST 2>nul | find /I "python.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Trader process started successfully
    echo.
    echo Trader is now running in background.
    echo.

    REM Wait a bit more for log file to be created
    timeout /t 2 /nobreak >nul

    REM Find and display the latest log file
    echo ============================================================
    echo  LATEST LOG OUTPUT
    echo ============================================================
    echo.

    for /f "delims=" %%i in ('dir /b /o-d rsi_swing_*.log 2^>nul') do (
        echo Log file: %%i
        echo.
        type "%%i"
        goto :found_log
    )

    :found_log
    echo.
    echo ============================================================
    echo To monitor trading:
    echo   - View log file: rsi_swing_*.log
    echo   - Check status: check_trader_status.bat
    echo.
    echo To stop trader:
    echo   - Run: stop_trader_all.bat
    echo ============================================================
    echo.
) else (
    echo [ERROR] Trader process failed to start
    echo.
    echo Checking log files...
    for /f "delims=" %%i in ('dir /b /o-d rsi_swing_*.log 2^>nul') do (
        echo Error log: %%i
        type "%%i"
        goto :error_log
    )
    :error_log
    echo.
    pause
)

echo.
echo Press any key to close this window...
pause
