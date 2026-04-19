@echo off
echo ============================================================
echo  Qwen OCPM Alert Monitor - Background Service Installer
echo  Run alert monitor in background (no window)
echo ============================================================
echo.

set TASK_NAME=QwenAlertMonitor
set WORK_DIR=%~dp0
set PYTHONW_EXE=pythonw.exe

echo [1/3] Checking Pythonw...
where %PYTHONW_EXE% >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pythonw.exe not found. Please install Python properly.
    pause
    exit /b 1
)
echo Pythonw: OK

echo.
echo [2/3] Removing existing task...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
echo Done.

echo.
echo [3/3] Creating scheduled task (Hidden)...
echo  - Task: %TASK_NAME%
echo  - Script: qwen_ocpm_signal_monitor.py
echo  - Mode: Background (No window)
echo  - Trigger: On user login

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "cmd /c cd /d \"%WORK_DIR%\" && %PYTHONW_EXE% qwen_ocpm_signal_monitor.py" ^
    /sc onlogon ^
    /ru "%USERNAME%" ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo  SUCCESS - Alert Monitor installed as background service
    echo ============================================================
    echo.
    echo  Start now:     schtasks /run /tn "%TASK_NAME%"
    echo  Stop:          schtasks /end /tn "%TASK_NAME%"
    echo  Uninstall:     schtasks /delete /tn "%TASK_NAME%" /f
    echo.
    echo  You will receive a Windows Popup + Sound when a signal appears.
    echo.
) else (
    echo.
    echo ERROR: Failed. Right-click and "Run as Administrator".
)

pause
