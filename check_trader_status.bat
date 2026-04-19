@echo off

chcp 65001 >nul

title Check RSI Swing v6 Status



echo ============================================================

echo  BTC/USDT RSI SWING v6 - Status (hl_rsi_swing_v6.py)

echo ============================================================

echo.



cd /d "%~dp0"



set "latest_log="

for /f "delims=" %%i in ('dir /b /o-d rsi_swing_*.log 2^>nul') do (

    set "latest_log=%%i"

    goto :have_log

)



:have_log

if "%latest_log%"=="" (

    echo [INFO] No rsi_swing_*.log found in project folder.

    echo Trader may not be running.

    echo.

    echo To start: start_auto_trader_bg.bat or start_trader.bat

    goto :proc

)



echo [INFO] Latest log: %latest_log%

echo.

echo Last 30 lines:

echo ============================================================

powershell -NoProfile -Command "Get-Content -LiteralPath '%CD%\%latest_log%' -Tail 30 -ErrorAction SilentlyContinue"

echo ============================================================

echo.



:proc

echo Process check (window title HL_RSI_SWING_V6):

tasklist /FI "WINDOWTITLE eq HL_RSI_SWING_V6*" /FO LIST 2>nul | find /I "python.exe" >nul

if %ERRORLEVEL% EQU 0 (

    echo [OK] hl_rsi_swing_v6 window is RUNNING

    echo To stop: stop_trader_all.bat ^(kills all python.exe^)

) else (

    echo [INFO] HL_RSI_SWING_V6 window not found ^(may still run without matching title^)

    echo To start: start_auto_trader_bg.bat

)



echo.

echo ============================================================

pause

