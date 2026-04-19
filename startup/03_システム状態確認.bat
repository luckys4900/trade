@echo off
setlocal enabledelayedexpansion

REM 親ディレクトリを設定
for %%I in ("%~dp0.") do set "STARTUP_DIR=%%~fI"
for %%I in ("%STARTUP_DIR%\.") do set "TRADE_DIR=%%~fI"

mode con: cols=100 lines=40
title システム状態確認
chcp 65001 >nul

cls
echo.
echo ============================================================
echo  System Status Dashboard
echo ============================================================
echo.
echo Trade Directory: %TRADE_DIR%
echo Time: %date% %time%
echo.

if not exist "%TRADE_DIR%" (
    echo ERROR: Trade directory not found: %TRADE_DIR%
    pause
    exit /b 1
)

REM プロセス確認
echo ============================================================
echo  Running Processes
echo ============================================================
tasklist | find "python" >nul
if errorlevel 1 (
    echo [STOPPED] No Python processes running
) else (
    echo [RUNNING] Python processes:
    echo.
    tasklist | find "python"
)

echo.
echo ============================================================
echo  Signal Files
echo ============================================================
echo.

if exist "%TRADE_DIR%\whale_signal.json" (
    echo [whale_signal.json]
    type "%TRADE_DIR%\whale_signal.json"
) else (
    echo [whale_signal.json] - Not yet created
)

echo.
if exist "%TRADE_DIR%\macro_state.json" (
    echo [macro_state.json]
    type "%TRADE_DIR%\macro_state.json"
) else (
    echo [macro_state.json] - Not yet created
)

echo.
echo ============================================================
echo  Recent Logs
echo ============================================================
echo.

cd /d "%TRADE_DIR%"

REM 最新のunified_liveログ
setlocal disabledelayedexpansion
for /f "tokens=*" %%F in ('dir /b /o-d logs\unified_live_*.log 2^>nul') do (
    echo [unified_live.log - Latest]
    echo File: %%F
    echo Last 5 lines:
    for /f "skip=5 tokens=*" %%L in ('type logs\%%F') do echo. %%L
    goto skip_main
)
echo [unified_live.log] - Not found
:skip_main
endlocal

echo.

REM 最新のwhale_monitorログ
setlocal disabledelayedexpansion
for /f "tokens=*" %%F in ('dir /b /o-d logs\whale_monitor_*.log 2^>nul') do (
    echo [whale_monitor.log - Latest]
    echo File: %%F
    type logs\%%F
    goto skip_whale
)
echo [whale_monitor.log] - Not found
:skip_whale
endlocal

echo.
echo ============================================================
echo  Actions
echo ============================================================
echo.
echo  To START: Run "01_クジラ監視システム起動.bat"
echo  To STOP:  Run "04_全システム停止.bat"
echo.

pause
