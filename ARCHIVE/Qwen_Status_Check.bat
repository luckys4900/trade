@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Qwen Unified Auto-Trader - Status Check
echo ============================================================
echo.

echo [1] Process Status
echo -----------------------------------------------------------
tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if %errorlevel%==0 (
    echo [OK] Bot is RUNNING
    tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe"
) else (
    echo [STOP] Bot is NOT running
)
echo.

echo [2] Latest Log (last 30 lines)
echo -----------------------------------------------------------
set "LOG_DIR=%~dp0logs"
if exist "%LOG_DIR%\unified_live_*.log" (
    for /f "delims=" %%f in ('dir /b /o-d "%LOG_DIR%\unified_live_*.log" 2^>nul') do (
        echo File: %%f
        echo.
        powershell -NoProfile -Command "Get-Content '%LOG_DIR%\%%f' -Tail 30"
        goto :done_log
    )
) else (
    echo No unified_live_*.log found.
)
:done_log
echo.

echo [3] Current State
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
