@echo off
echo.
echo ==========================================================
echo   BTC/USDT 4H ADAPTIVE RSI v5 - OFFLINE BACKTEST
echo ==========================================================
echo.
echo   This version uses cached CSV data only (No Hyperliquid API)
echo.
echo   Running 365-day backtest...
echo.
echo ==========================================================
echo.

cd /d "%~dp0"
python -u force_run_hl_offline.py --mode backtest --days 365

echo.
echo ==========================================================
echo   Backtest completed
echo ==========================================================
echo.

echo Press any key to exit...
pause >nul
