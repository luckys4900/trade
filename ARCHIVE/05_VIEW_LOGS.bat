@echo off
cls
title LOG VIEWER

echo.
echo ====== LOG VIEWER ======
echo.
echo Select log to view:
echo.
echo 1. Whale Monitor Log
echo 2. Macro Filter Log
echo 3. Main Bot Log
echo 4. Open logs folder
echo 0. Exit
echo.

set /p choice="Enter choice (0-4): "

if "%choice%"=="1" goto whale
if "%choice%"=="2" goto macro
if "%choice%"=="3" goto main
if "%choice%"=="4" goto folder
if "%choice%"=="0" exit /b

echo Invalid choice
goto end

:whale
cls
echo ====== WHALE MONITOR LOG ======
echo.
if exist logs\whale_monitor_live.log (
    type logs\whale_monitor_live.log
) else (
    echo Log file not found
)
goto end

:macro
cls
echo ====== MACRO FILTER LOG ======
echo.
if exist logs\macro_filter_live.log (
    type logs\macro_filter_live.log
) else (
    echo Log file not found
)
goto end

:main
cls
echo ====== MAIN BOT LOG ======
echo.
if exist logs\qwen_unified_live.log (
    type logs\qwen_unified_live.log
) else (
    echo Log file not found
)
goto end

:folder
start explorer "logs"
goto end

:end
echo.
pause
exit /b
