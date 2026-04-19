@echo off

chcp 65001 >nul

title BTC/USDT 4H RSI SWING v6 - LIVE (Auto Restart)



echo ============================================================

echo  BTC/USDT 4H RSI SWING v6 - LIVE TRADER (Auto Restart)

echo ============================================================

echo.

echo Starting live trading with auto-restart...

echo Script: hl_rsi_swing_v6.py

echo Log: rsi_swing_*.log

echo.

echo ============================================================

echo.



cd /d "%~dp0"



:loop

python hl_rsi_swing_v6.py



if %ERRORLEVEL% NEQ 0 (

    echo.

    echo ============================================================

    echo ERROR: Trading stopped with error code %ERRORLEVEL%

    echo ============================================================

    echo.

    echo Attempting to restart in 10 seconds...

    echo ============================================================

    timeout /t 10 /nobreak >nul

    goto loop

) else (

    echo.

    echo ============================================================

    echo Trading stopped normally

    echo ============================================================

    pause

    goto loop

)

