@echo off
REM Simple Dashboard Launcher
REM Calls Python for all heavy lifting

setlocal enabledelayedexpansion

title WHALE TRADING SYSTEM - Dashboard

python3 dashboard.py

pause
exit /b
