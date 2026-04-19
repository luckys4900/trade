@echo off
echo.
echo Deleting old CSV file...
del /f /q btc_usdt_4h.csv
echo CSV file deleted successfully
echo.
echo Now run the backtest again:
echo python -u force_run_hl_offline.py --mode backtest --days 365
echo.
pause
