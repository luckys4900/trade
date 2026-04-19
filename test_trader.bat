@echo off

chcp 65001 >nul

cd /d "%~dp0"

echo ============================================================

echo  Smoke test (RSI Swing v6)

echo ============================================================

echo.



echo [1] test_basic.py

python test_basic.py

if %ERRORLEVEL% NEQ 0 (

    echo [FAIL] test_basic.py

    pause

    exit /b 1

)

echo.



echo [2] py_compile hl_rsi_swing_v6.py (syntax check, no trading)

python -m py_compile hl_rsi_swing_v6.py

if %ERRORLEVEL% NEQ 0 (

    echo [FAIL] py_compile

    pause

    exit /b 1

)

echo [OK] hl_rsi_swing_v6.py compiles

echo.



echo ============================================================

echo  Done. To run live: start_trader.bat or start_auto_trader_bg.bat

echo ============================================================

pause

