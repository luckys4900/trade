@echo off

title BTC/USDT RSI SWING v6 - Hyperliquid Testnet



echo ==========================================================

echo  BTC/USDT RSI SWING v6 - TESTNET (hl_rsi_swing_v6.py)

echo ==========================================================

echo.

echo  Set config.json: "environment": "testnet", "live_trading": true

echo  Demo funds only on testnet.

echo.

echo  Press Enter to start...

echo  Ctrl+C to stop.

echo.

echo  Log: rsi_swing_*.log

echo ==========================================================

echo.



pause



echo.

cd /d "%~dp0"

python -u hl_rsi_swing_v6.py



echo.

echo Program stopped.

echo.

pause

