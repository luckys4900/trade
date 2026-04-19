@echo off
REM Stop Whale Trading System

cls
echo.
echo ====== STOPPING SYSTEM ======
echo.

tasklist | find "python" > /dev/null
if errorlevel 1 (
    echo No processes found. System already stopped.
) else (
    echo Found running processes:
    tasklist | find "python"
    echo.
    echo Stopping...
    echo.

    taskkill /IM pythonw.exe /F > /dev/null 2>&1
    if not errorlevel 1 echo [OK] pythonw.exe stopped

    taskkill /IM python.exe /F > /dev/null 2>&1
    if not errorlevel 1 echo [OK] python.exe stopped

    timeout /t 2 > /dev/null
    echo.
    echo Verification:
    tasklist | find "python" > /dev/null
    if errorlevel 1 (
        echo All systems stopped
    ) else (
        echo WARNING: Some processes still running
    )
)

echo.
pause
