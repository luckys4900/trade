@echo off
echo ============================================================
echo  Qwen BTC Auto-Trader - Windows Service Installer
echo  Install as Windows Scheduled Task (auto-start on login)
echo ============================================================
echo.

set TASK_NAME=QwenBTCTrader
set WORK_DIR=%~dp0
set PYTHON_EXE=python

echo [1/3] Checking Python...
%PYTHON_EXE% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found.
    pause
    exit /b 1
)
echo Python: OK

echo.
echo [2/3] Removing existing task...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
echo Done.

echo.
echo [3/3] Creating scheduled task...
echo  - Task: %TASK_NAME%
echo  - Script: onchain_pullback_momentum.py --mode live
echo  - Trigger: On user login
echo  - Hidden: Yes (no window)

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "cmd /c cd /d \"%WORK_DIR%\" && %PYTHON_EXE% onchain_pullback_momentum.py --mode live --timeframe 4h --interval 60" ^
    /sc onlogon ^
    /ru "%USERNAME%" ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo  SUCCESS - Auto-start installed
    echo ============================================================
    echo.
    echo  Start now:     schtasks /run /tn "%TASK_NAME%"
    echo  Stop:          schtasks /end /tn "%TASK_NAME%"
    echo  Uninstall:     schtasks /delete /tn "%TASK_NAME%" /f
    echo  Status:        schtasks /query /tn "%TASK_NAME%"
    echo  Logs:          %WORK_DIR%logs\
    echo.
) else (
    echo.
    echo ERROR: Failed. Right-click and "Run as Administrator".
)

pause
