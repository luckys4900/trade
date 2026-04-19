@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo  Qwen Unified Auto-Trader - Status Check
rem ---- Dashboard URL ---------------------------------------------------
rem Run "python -m http.server 8000" in the project root to serve the UI.
rem Then open the URL below to view open positions and TP/SL.
rem ------------------------------------------------------------
rem Dashboard URL: http://localhost:8000/dashboard.html
echo ============================================================
echo.

cd /d "%~dp0"

echo [1] Process Status
echo -----------------------------------------------------------
set "PY_COUNT=0"
for /f %%a in ('tasklist /FI "IMAGENAME eq pythonw.exe" 2^>nul ^| find /C /I "pythonw.exe"') do set "PY_COUNT=%%a"
if %PY_COUNT% GTR 0 (
    echo [OK] Bot is RUNNING (%PY_COUNT% pythonw.exe process(es))
) else (
    echo [STOP] Bot is NOT running
)
echo.

echo [2] Latest Log (last 30 lines)
echo -----------------------------------------------------------
set "LOG_DIR=%~dp0logs"
set "FOUND_LOG="
if exist "%LOG_DIR%" (
    for /f "delims=" %%f in ('dir /b /o-d "%LOG_DIR%\unified_live_*.log" 2^>nul') do (
        set "FOUND_LOG=%%f"
        goto :show_log
    )
)
:show_log
if defined FOUND_LOG (
    echo File: %FOUND_LOG%
    echo.
    powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG_DIR%\%FOUND_LOG%' -Tail 30 -ErrorAction SilentlyContinue"
) else (
    echo No unified_live_*.log found.
)
echo.

echo [3] Current State (trade_state_unified.json)
echo -----------------------------------------------------------
if exist "trade_state_unified.json" (
    type "trade_state_unified.json"
) else (
    echo State file not found.
)
echo.

echo ============================================================
echo Press any key to exit...
pause >nul
