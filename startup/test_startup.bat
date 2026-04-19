@echo off
REM テスト用batファイル
REM このファイルをダブルクリックして、ウィンドウが表示されるか確認

setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo ============================================================
echo  TEST: Bat File Execution Check
echo ============================================================
echo.

set "TRADE_DIR=%~dp0.."
echo Current Batch File: %~f0
echo Startup Folder: %~dp0
echo Trade Directory: %TRADE_DIR%
echo.

REM 簡単なパステスト
echo [TEST 1] Check if TRADE_DIR exists
if exist "%TRADE_DIR%" (
    echo OK: %TRADE_DIR% exists
) else (
    echo ERROR: %TRADE_DIR% not found
)

echo.
echo [TEST 2] Check for whale_monitor.py
if exist "%TRADE_DIR%\whale_monitor.py" (
    echo OK: whale_monitor.py found
) else (
    echo ERROR: whale_monitor.py not found
)

echo.
echo [TEST 3] Check for logs folder
if exist "%TRADE_DIR%\logs" (
    echo OK: logs folder found
) else (
    echo ERROR: logs folder not found
)

echo.
echo [TEST 4] List Python processes
tasklist | find "python" >nul
if errorlevel 1 (
    echo INFO: No Python processes running
) else (
    echo Running processes:
    tasklist | find "python"
)

echo.
echo [TEST 5] Check signal files
if exist "%TRADE_DIR%\whale_signal.json" (
    echo OK: whale_signal.json exists
) else (
    echo INFO: whale_signal.json not yet created
)

echo.
echo ============================================================
echo  If you see this message, batfiles work correctly.
echo  You can delete this test file.
echo ============================================================
echo.

pause
