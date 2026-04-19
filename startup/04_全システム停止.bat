@echo off
setlocal

mode con: cols=80 lines=20
title システム停止
chcp 65001 >nul

cls
echo.
echo ============================================================
echo  Stopping Whale Monitoring System
echo ============================================================
echo.

REM プロセス確認
tasklist | find "python" >nul
if errorlevel 1 (
    echo [INFO] No Python processes found
    echo System may already be stopped
    echo.
    pause
    exit /b 0
)

echo Found running processes:
echo.
tasklist | find "python"
echo.
echo Stopping...
echo.

REM 停止処理
taskkill /IM pythonw.exe /F 2>nul
if not errorlevel 1 echo [OK] pythonw.exe stopped

taskkill /IM python.exe /F 2>nul
if not errorlevel 1 echo [OK] python.exe stopped

timeout /t 2 /nobreak >nul

echo.
echo ============================================================
echo Verification
echo ============================================================
echo.

tasklist | find "python" >nul
if errorlevel 1 (
    echo [SUCCESS] All systems stopped
) else (
    echo [WARNING] Some processes still running
    echo.
    tasklist | find "python"
    echo.
    echo Retry in Task Manager:
    echo  Ctrl+Shift+Esc ^> Find python.exe ^> End Task
)

echo.
pause
