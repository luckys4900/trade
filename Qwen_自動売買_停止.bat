@echo off
echo ============================================================
echo  Qwen BTC Auto-Trader - Stop Service
echo ============================================================
echo.

set TASK_NAME=QwenBTCTrader

echo Stopping scheduled task...
schtasks /end /tn "%TASK_NAME%" 2>nul
schtasks /delete /tn "%TASK_NAME%" /f 2>nul

echo Killing pythonw processes...
powershell -Command "Stop-Process -Name 'pythonw' -Force -ErrorAction SilentlyContinue"
powershell -Command "Stop-Process -Name 'python' -Force -ErrorAction SilentlyContinue"

timeout /t 2 /nobreak >nul

echo Verifying...
powershell -Command "Get-Process | Where-Object { $_.ProcessName -like '*python*' } | Select-Object ProcessName, Id" 2>nul

echo.
echo ============================================================
echo  STOPPED - Bot is no longer running
echo  To restart: Run Qwen_Background_Start.bat
echo ============================================================

pause
