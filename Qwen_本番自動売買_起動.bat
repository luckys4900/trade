@echo off
setlocal

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if not errorlevel 1 (
    echo.
    echo [ALREADY RUNNING] Bot is already running.
    echo To restart, run the stop batch file first, then run this again.
    echo.
    pause
    exit /b 0
)

echo ============================================================
echo  Qwen Unified Auto-Trader (OCPM + Range MR + RSI Swing v6 + Contrarian)
echo  Exchange: Hyperliquid Mainnet
echo  Wallet: 0x7dd9f0C23Fb61CA3f36B8414306310F963093c12
echo ============================================================
echo.
echo  Strategy 1: OCPM (Trend Pullback - EMA21/55 + RSI)
echo  Strategy 2: Range MR (Bollinger Bands Reversal + ADX filter)
echo  Strategy 3: RSI Swing v6 (RSI Crossover + ATR SL/TP)
echo  Strategy 4: 4h Contrarian (Kronos-base reverse signal)
echo  Backtest: 2 years +6.51%% (81 trades, WR 55.6%%, PF 1.23)
echo.
echo  Running in background (no window).
echo  Check logs\ folder for status.
echo  To stop: Task Manager -^> End pythonw.exe
echo.
echo  Starting now...
echo.

cd /d "%~dp0"

taskkill /F /IM wscript.exe 2>nul

REM Start Whale Monitor (15min cycle)
echo [1/4] Starting Whale Monitor (15min cycle)...
start "Whale Monitor" /MIN pythonw.exe SYSTEM\whale_monitor.py 2>>logs\startup_errors.log
timeout /t 2 /nobreak >nul

REM Start Macro Filter (60min cycle)
echo [2/4] Starting Macro Filter (60min cycle)...
start "Macro Filter" /MIN pythonw.exe SYSTEM\macro_filter.py 2>>logs\startup_errors.log
timeout /t 2 /nobreak >nul

REM Start Kronos Predictor
echo [3/4] Starting Kronos Predictor...
start "Kronos Predictor" /MIN pythonw.exe SYSTEM\kronos_predictor.py --interval 14400 2>>logs\startup_errors.log
timeout /t 2 /nobreak >nul

REM Start Main Bot
echo [4/4] Starting Main Bot...
start "Main Bot" /MIN pythonw.exe SYSTEM\qwen_unified_live.py 2>>logs\startup_errors.log

timeout /t 3 /nobreak >nul

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if not errorlevel 1 (
    echo Bot started in background.
    echo Check logs\unified_live_*.log for status.
) else (
    echo ERROR: Failed to start bot. Check logs for details.
)

timeout /t 2
