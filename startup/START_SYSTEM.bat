@echo off
cls
title Whale Monitoring System

echo.
echo ====== WHALE MONITORING SYSTEM ======
echo.

cd ..

REM Check if running
tasklist | find "python" > nul
if errorlevel 1 (
    echo Starting system...
    echo.

    echo [1/3] Whale Monitor
    start /MIN pythonw.exe whale_monitor.py
    timeout /t 2 > nul

    echo [2/3] Macro Filter
    start /MIN pythonw.exe macro_filter.py
    timeout /t 2 > nul

    echo [3/3] Main Bot
    if exist Qwen_Background_Start.vbs (
        start Qwen_Background_Start.vbs
    )

    echo.
    echo Starting...
    timeout /t 3 > nul

    echo.
    echo Done. Check: 03_STATUS_CHECK.bat
) else (
    echo System is already running
)

echo.
pause
