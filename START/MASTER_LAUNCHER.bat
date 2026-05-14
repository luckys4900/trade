@echo off
REM ============================================================
REM WHALE TRADING SYSTEM - UNIFIED LAUNCHER
REM ============================================================
REM Integrated with main Qwen launcher batch
REM All components run from SYSTEM\ folder
REM ============================================================

setlocal enabledelayedexpansion

REM Change to parent directory (trade root)
cd /d "%~dp0.."

:menu
cls
echo.
echo ============================================================
echo  WHALE FOLLOWING COPY-TRADING SYSTEM v1.2 + Kronos AI
echo ============================================================
echo.
echo [1] START SYSTEM
echo     Pre-flight wallet/signal check once, then all modules in background
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
echo ============================================================
echo  Qwen Unified Auto-Trader with Whale Following System
echo  Exchange: Hyperliquid Mainnet
echo  Wallet: 0x7dd9f0C23Fb61CA3f36B8414306310F963093c12
echo ============================================================
echo.
echo  Component 1: Whale Monitor (15-min cycle, HL wallets)
echo  Component 2: Macro Filter (60-min cycle)
echo  Component 3: BTC Exchange Inflow Monitor (5-min, on-chain to data\btc_inflow_events.json)
echo  Component 4: Inflow EV1 Signal Builder (10-min to inflow_short_signal.json)
echo  Component 5: Kronos Contrarian Predictor (4h cycle)
echo  Component 6: Main Trading Bot (1-min; set inflow_short_enabled in code to use EV1)
echo  Component 7: Clarity Act Phase Monitor (daily, BTC/ETH pair during regulatory events)
echo.

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if not errorlevel 1 (
    echo System already running. Stop first with option [3]
    pause
    goto menu
)

taskkill /F /IM wscript.exe 2>nul

echo.
echo Pre-flight (blocking): exchange on-chain wallets, EV1 signal file, HL whale wallets, macro state
echo.
python data\btc_inflow_monitor.py --once
if errorlevel 1 echo [WARN] BTC inflow --once failed
python SYSTEM\inflow_short_signal_builder.py
if errorlevel 1 echo [WARN] inflow_short_signal_builder failed
python SYSTEM\whale_monitor.py --once
if errorlevel 1 echo [WARN] whale_monitor --once failed
python SYSTEM\macro_filter.py --once
if errorlevel 1 echo [WARN] macro_filter --once failed
echo Pre-flight complete.
echo.

echo [1/7] Starting Whale Monitor...
start "Whale Monitor" /MIN pythonw.exe SYSTEM\whale_monitor.py
timeout /t 3 /nobreak >nul

echo [2/7] Starting Macro Filter...
start "Macro Filter" /MIN pythonw.exe SYSTEM\macro_filter.py
timeout /t 3 /nobreak >nul

echo [3/7] Starting BTC Inflow Monitor (mempool.space, 5-min)...
start "BTC Inflow Monitor" /MIN pythonw.exe data\btc_inflow_monitor.py --loop 300
timeout /t 3 /nobreak >nul

echo [4/7] Starting Inflow EV1 Signal Builder (10-min loop)...
start "Inflow EV1 Signal" /MIN pythonw.exe SYSTEM\inflow_short_signal_loop.py
timeout /t 3 /nobreak >nul

echo [5/7] Starting Kronos AI Predictor...
start "Kronos Predictor" /MIN pythonw.exe SYSTEM\kronos_predictor.py --interval 14400
timeout /t 3 /nobreak >nul

echo [6/7] Starting Main Trading Bot...
start "Main Bot" /MIN pythonw.exe SYSTEM\qwen_unified_live.py
timeout /t 3 /nobreak >nul

echo [7/7] Starting Clarity Act Phase Monitor...
start "Clarity Phase" /MIN pythonw.exe data\clarity_phase_monitor.py
timeout /t 3 /nobreak >nul

echo.
echo System started successfully
echo Next: Use [2] MONITOR to check status
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
if not errorlevel 1 echo [OK] pythonw.exe stopped

taskkill /IM python.exe /F >nul 2>&1
if not errorlevel 1 echo [OK] python.exe stopped

taskkill /IM python3.exe /F >nul 2>&1
if not errorlevel 1 echo [OK] python3.exe stopped

timeout /t 2 /nobreak >nul

tasklist | find "python" >nul
if errorlevel 1 (
    echo.
    echo All systems stopped successfully
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
echo [4] Startup Errors
echo [5] Clarity Act Phase Log
echo [6] Open logs folder
echo [0] Back
echo.

set /p logchoice="Select (0-5): "

if "%logchoice%"=="1" (
    cls
    echo ====== WHALE MONITOR LOG ======
    if exist logs\whale_monitor_live.log (
        type logs\whale_monitor_live.log | more
    ) else (
        echo Log file not found
    )
)

if "%logchoice%"=="2" (
    cls
    echo ====== MACRO FILTER LOG ======
    if exist logs\macro_filter_live.log (
        type logs\macro_filter_live.log | more
    ) else (
        echo Log file not found
    )
)

if "%logchoice%"=="3" (
    cls
    echo ====== MAIN BOT LOG ======
    if exist logs\qwen_unified_live.log (
        type logs\qwen_unified_live.log | more
    ) else (
        echo Log file not found
    )
)

if "%logchoice%"=="4" (
    cls
    echo ====== STARTUP ERRORS ======
    if exist logs\startup_errors.log (
        type logs\startup_errors.log | more
    ) else (
        echo No errors logged
    )
)

if "%logchoice%"=="5" (
    cls
    echo ====== CLARITY ACT PHASE LOG ======
    if exist data\clarity_phase_history.json (
        type data\clarity_phase_history.json | more
    ) else (
        echo No phase history yet
    )
)

if "%logchoice%"=="6" (
    start explorer "logs\"
)

if not "%logchoice%"=="0" pause
goto menu

REM ========== GUIDE ==========
:guide
cls
echo.
echo ===== WHALE FOLLOWING TRADING SYSTEM - GUIDE =====
echo.
echo INTEGRATED SYSTEM:
echo   This launcher combines Whale Following, Kronos Contrarian,
echo   and Qwen Auto-Trader into one unified system
echo.
echo DAILY WORKFLOW:
echo   Morning:   [1] START SYSTEM (run once)
echo   Throughout: [2] MONITOR (multiple times)
echo   Evening:   [3] STOP SYSTEM
echo.
echo On each [1] START: Pre-flight runs once (inflow wallets, inflow_short_signal.json,
echo   whale HL wallets, macro_state.json), then six background components.
echo.
echo SIX COMPONENTS:
echo   1. Whale Monitor (15-min)
echo      Analyzes large trader wallets
echo      Outputs: logs\whale_monitor_live.log
echo.
echo   2. Macro Filter (60-min)
echo      Tracks market volatility and economic events
echo      Outputs: logs\macro_filter_live.log
echo.
echo   3. BTC Inflow Monitor (5-min)
echo      On-chain exchange inflows to data\btc_inflow_events.json
echo.
echo   4. Inflow EV1 Signal (10-min)
echo      Builds inflow_short_signal.json (SHORT bias for bot when enabled)
echo.
echo   5. Kronos Contrarian Predictor (4h)
echo      Generates reverse-direction BTC signals
echo      Outputs: logs\kronos_predictor_live.log
echo.
echo   6. Main Trading Bot (1-min)
echo      Auto-trades using whale signals, BTC trend logic,
echo      and Contrarian mid-volatility filtering
echo      Outputs: logs\qwen_unified_live.log
echo.
echo   7. Clarity Act Phase Monitor (daily)
echo      BTC/ETH pair trading around regulatory events
echo      Phase 2: Vol breakout on event day
echo      Phase 3: Post-event BTC lead (D+5 to D+20)
echo      Outputs: data\clarity_phase_history.json
echo.
echo MONITOR DASHBOARD SHOWS:
echo   - Process Status: 6 systems running (if all started)
echo   - Whale Signal: valid=true means trade opportunity
echo   - Macro Filter: regime=NORMAL means safe to trade
echo   - Contrarian Signal: Kronos reverse-direction trade setup
echo   - Latest Logs: Real-time updates from all systems
echo.
pause
goto menu
