@echo off
REM ============================================================
REM WHALE TRADING SYSTEM - UNIFIED LAUNCHER
REM ============================================================
REM This launcher combines:
REM  1. Whale Monitor (15-min cycle)
REM  2. Macro Filter (60-min cycle)
REM  3. Main Trading Bot (Auto-trading execution)
REM ============================================================

setlocal enabledelayedexpansion

REM Change to trade root
cd /d "%~dp0"

:menu
cls
echo.
echo ============================================================
echo  WHALE FOLLOWING COPY-TRADING SYSTEM v1.2 + Kronos AI
echo ============================================================
echo.
echo [1] START SYSTEM
echo     Starts all modules in background (Whale + Macro + Kronos + Bot)
echo     BTC EV filters are loaded in the main bot
echo.
echo [2] MONITOR (Real-time Dashboard)
echo     RECOMMENDED - Check status here daily
echo.
echo [3] STOP SYSTEM
echo     Safe shutdown of all processes
echo.
echo [4] LOGS
echo     View system logs
echo.
echo [5] QUICK START GUIDE
echo.
echo [0] EXIT
echo.

set /p choice="Select option (0-5): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto monitor
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto guide
if "%choice%"=="0" exit /b
goto menu

REM ========== START ==========
:start
cls
echo.
echo Starting system...
echo.

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if not errorlevel 1 (
    echo System already running. Stop first with option [3]
    pause
    goto menu
)

echo [1/4] Starting Whale Monitor...
start /MIN pythonw.exe SYSTEM\whale_monitor.py
timeout /t 2 /nobreak >nul

echo [2/4] Starting Macro Filter...
start /MIN pythonw.exe SYSTEM\macro_filter.py
timeout /t 2 /nobreak >nul

echo [3/4] Starting Kronos AI Predictor...
start /MIN pythonw.exe SYSTEM\kronos_predictor.py --interval 14400
timeout /t 2 /nobreak >nul

echo [4/4] Starting Main Trading Bot...
start /MIN pythonw.exe SYSTEM\qwen_unified_live.py
timeout /t 3 /nobreak >nul

echo.
echo System started successfully
echo Next: Use option [2] to monitor
echo.
pause
goto menu

REM ========== MONITOR ==========
:monitor
cls
echo.
echo Starting real-time dashboard...
echo (Updates every 5 seconds. Press Ctrl+C to exit)
echo.
python SYSTEM\dashboard.py
goto menu

REM ========== STOP ==========
:stop
cls
echo.
echo Stopping system...
echo.

taskkill /IM pythonw.exe /F >nul 2>&1
if not errorlevel 1 echo Stopped pythonw.exe

taskkill /IM python.exe /F >nul 2>&1
if not errorlevel 1 echo Stopped python.exe

timeout /t 2 /nobreak >nul

tasklist | find "python" >nul
if errorlevel 1 (
    echo.
    echo All systems stopped
) else (
    echo.
    echo WARNING: Some processes still running
)

echo.
pause
goto menu

REM ========== LOGS ==========
:logs
cls
echo.
echo ====== LOG VIEWER ======
echo.
echo [1] Whale Monitor Log
echo [2] Macro Filter Log
echo [3] Main Bot Log
echo [4] Kronos Predictor Log
echo [5] Open logs folder
echo [0] Back
echo.

set /p logchoice="Select (0-5): "

if "%logchoice%"=="1" (
    cls
    echo ====== WHALE MONITOR LOG ======
    if exist logs\whale_monitor_live.log (
        type logs\whale_monitor_live.log
    ) else (
        echo Log file not found
    )
)

if "%logchoice%"=="2" (
    cls
    echo ====== MACRO FILTER LOG ======
    if exist logs\macro_filter_live.log (
        type logs\macro_filter_live.log
    ) else (
        echo Log file not found
    )
)

if "%logchoice%"=="3" (
    cls
    echo ====== MAIN BOT LOG ======
    if exist logs\qwen_unified_live.log (
        type logs\qwen_unified_live.log
    ) else (
        echo Log file not found
    )
)

if "%logchoice%"=="4" (
    cls
    echo ====== KRONOS PREDICTOR LOG ======
    if exist logs\kronos_predictor_live.log (
        type logs\kronos_predictor_live.log
    ) else (
        echo Log file not found
    )
)

if "%logchoice%"=="5" (
    start explorer "logs"
)

if not "%logchoice%"=="0" pause
goto menu

REM ========== GUIDE ==========
:guide
cls
echo.
echo ===== WHALE TRADING SYSTEM - QUICK GUIDE =====
echo.
echo WHAT IS THIS?
echo   Automated trading system that monitors large traders
echo   and copies their trades with risk management
echo.
echo DAILY WORKFLOW:
echo   Morning:   Run [1] START SYSTEM (one time)
echo   Throughout: Run [2] MONITOR multiple times (status check)
echo   Evening:   Run [3] STOP SYSTEM
echo.
echo WHAT TO WATCH FOR IN [2] MONITOR:
echo   - Process Status: 4 systems running
echo   - Whale Signal: valid=true means trade opportunity
echo   - Macro Filter: regime=NORMAL means safe to trade
echo   - Contrarian Signal: Kronos reverse-direction trade state
echo   - BTC EV Filters: Contrarian trades only fire in mid-volatility regimes
echo.
echo FILES:
echo   Input:  SYSTEM\whale_wallets.json (config)
echo   Output: whale_signal.json (15-min updates)
echo   Output: macro_state.json (60-min updates)
echo   Output: kronos_contrarian_signal.json (4h updates)
echo   Logs:   logs\ (detailed system logs)
echo.
echo FOLDERS:
echo   START\   - Launcher (this file)
echo   SYSTEM\  - Core programs (do not touch)
echo   DATA\    - Output files (auto-generated)
echo   DOCS\    - Documentation
echo   ARCHIVE\ - Old files (can delete)
echo.
echo SUPPORT:
echo   Use [4] LOGS to check detailed logs
echo   All logs are timestamped and saved
echo.
pause
goto menu
