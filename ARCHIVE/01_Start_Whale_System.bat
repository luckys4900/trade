@echo off
REM Start Whale Trading System

echo.
echo ====== WHALE TRADING SYSTEM - START ======
echo.

REM Check if already running
tasklist /FI "IMAGENAME eq python.exe" 2>/dev/null | find /I "python" >/dev/null
if errorlevel 1 (
    echo [1/3] Starting Whale Monitor...
    start /MIN pythonw.exe whale_monitor.py
    timeout /t 2 >/dev/null

    echo [2/3] Starting Macro Filter...
    start /MIN pythonw.exe macro_filter.py
    timeout /t 2 >/dev/null

    echo [3/3] Starting Main Bot...
    start /MIN pythonw.exe qwen_unified_live.py
    timeout /t 3 >/dev/null

    echo.
    echo ====== SUCCESS ======
    echo System started successfully
    echo.
    echo Run "02_DASHBOARD.bat" to monitor system
) else (
    echo System already running. Stop first with 04_Stop_System.bat
)

echo.
pause
