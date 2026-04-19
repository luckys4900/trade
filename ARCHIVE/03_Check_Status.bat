@echo off
cls
title System Status Check

echo.
echo ====== SYSTEM STATUS ======
echo.

echo [Running Processes]
tasklist | find "python" > /dev/null
if errorlevel 1 (
    echo No Python processes found
) else (
    tasklist | find "python"
)

echo.
echo [Whale Signal]
if exist whale_signal.json (
    type whale_signal.json
) else (
    echo No whale_signal.json yet
)

echo.
echo [Macro State]
if exist macro_state.json (
    type macro_state.json
) else (
    echo No macro_state.json yet
)

echo.
pause
