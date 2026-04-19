@echo off
cls
title System Status

echo.
echo ====== SYSTEM STATUS ======
echo.

cd ..

REM Show running processes
echo [Processes]
tasklist | find "python"

echo.
echo [Signals]
if exist whale_signal.json (
    type whale_signal.json
) else (
    echo No whale_signal.json yet
)

echo.
pause
