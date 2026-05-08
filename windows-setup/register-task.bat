@echo off
chcp 65001 >nul
echo ========================================
echo  Register memsearch Auto-Sync Task
echo ========================================
echo.

set TASK_NAME=memsearch-AutoSync
set SCRIPT_PATH=%USERPROFILE%\Desktop\trade\windows-setup\sync-and-notify.ps1
set LOG_PATH=%USERPROFILE%\Desktop\trade\windows-setup\sync.log

REM Check if task already exists
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Creating new scheduled task...
) else (
    echo [INFO] Task already exists. Deleting and recreating...
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
)

REM Create log file if not exists
if not exist "%LOG_PATH%" (
    echo. > "%LOG_PATH%"
)

REM Register task: runs every 30 minutes
schtasks /create /tn "%TASK_NAME%" ^
    /tr "powershell.exe -ExecutionPolicy Bypass -NoProfile -File \"%SCRIPT_PATH%\"" ^
    /sc minute /mo 30 ^
    /ru "%USERNAME%" ^
    /rl HIGHEST ^
    /f

if errorlevel 1 (
    echo [ERROR] Failed to register task. Run as Administrator.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Task Registered Successfully!
echo ========================================
echo.
echo  Task Name: %TASK_NAME%
echo  Schedule:  Every 30 minutes
echo  Script:    %SCRIPT_PATH%
echo  Log:       %LOG_PATH%
echo.
echo  To check status:
echo    schtasks /query /tn "%TASK_NAME%"
echo.
echo  To view sync log:
echo    type "%LOG_PATH%"
echo.
echo  To delete task:
echo    schtasks /delete /tn "%TASK_NAME%" /f
echo.
pause
