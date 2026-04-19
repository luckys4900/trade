@echo off

echo ============================================================

echo  Manual Test Instructions (RSI Swing v6 workspace)

echo ============================================================

echo.

echo Run these in Command Prompt from the project folder:

echo.

echo 1. Python version:

echo    python --version

echo.

echo 2. Change directory:

echo    cd /d C:\Users\user\Desktop\cursor\trade

echo.

echo 3. Quick Python:

echo    python -c "print('Python works!')"

echo.

echo 4. Basic test script:

echo    python test_basic.py

echo.

echo 5. Compile check (no live orders):

echo    python -m py_compile hl_rsi_swing_v6.py

echo.

echo 6. Live bot (double-click is easier):

echo    start_trader.bat

echo    or: start_auto_trader_bg.bat

echo    Log: rsi_swing_*.log   Config: config.json

echo.

echo 7. Optional legacy scripts (not the default live path):

echo    hl_live_trader.py / force_run_hl.py

echo.

echo ============================================================

pause

