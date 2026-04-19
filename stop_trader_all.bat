@echo off
chcp 65001 >nul
title Stop Live Trader

echo ============================================================
echo  BTC/USDT 4H ADAPTIVE RSI v5 - STOP TRADER
echo ============================================================
echo.
echo Stopping all Python trading processes...
echo.

taskkill /f /im python.exe

echo.
echo All Python processes have been stopped.
echo.
pause