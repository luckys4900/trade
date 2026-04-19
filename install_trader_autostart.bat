@echo off

chcp 65001 >nul

title Install RSI Swing v6 Autostart



echo ============================================================

echo  BTC/USDT 4H RSI SWING v6 - AUTOSTART SETUP

echo ============================================================

echo.



set "SCRIPT_DIR=%~dp0"

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

set "WRAPPER_BAT=%STARTUP_DIR%\HL_Trader_Autostart.bat"

set "TRADER_PY=%SCRIPT_DIR%hl_rsi_swing_v6.py"



if not exist "%TRADER_PY%" (

    echo Error: hl_rsi_swing_v6.py not found.

    echo Path: %TRADER_PY%

    pause

    exit /b 1

)



echo Logon autostart: hl_rsi_swing_v6.py only (no other strategies).

echo Startup folder: "%STARTUP_DIR%"

echo.



if not exist "%STARTUP_DIR%" (

    echo Error: Startup folder not found.

    pause

    exit /b 1

)



if exist "%WRAPPER_BAT%" (

    del "%WRAPPER_BAT%" >nul 2>&1

)



(

    echo @echo off

    echo cd /d "%SCRIPT_DIR%"

    echo start "HL_RSI_SWING_V6" /MIN python hl_rsi_swing_v6.py

) > "%WRAPPER_BAT%"



if not exist "%WRAPPER_BAT%" (

    echo.

    echo Failed to create autostart wrapper.

    pause

    exit /b 1

)



echo.

echo Autostart configured. Next logon: hl_rsi_swing_v6.py only (minimized).

echo.

pause

