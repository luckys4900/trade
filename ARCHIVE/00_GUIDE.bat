@echo off
cls
title System Guide

color 0F

echo.
echo ===== WHALE TRADING SYSTEM - QUICK START GUIDE =====
echo.
echo STEP 1: START SYSTEM
echo   Double-click: 01_START.lnk
echo.
echo STEP 2: CHECK DASHBOARD
echo   Double-click: 02_DASHBOARD.lnk
echo   (Real-time status display, updates every 5 seconds)
echo   Press Ctrl+C to exit
echo.
echo STEP 3: VIEW LOGS (if needed)
echo   Double-click: 05_VIEW_LOGS.lnk
echo.
echo STEP 4: STOP SYSTEM
echo   Double-click: 04_STOP.lnk
echo.
echo ===== FILES CREATED =====
echo.
echo Shortcuts (.lnk):
echo   01_START.lnk ............. Start system
echo   02_DASHBOARD.lnk ......... Monitor (USE DAILY)
echo   03_STATUS.lnk ............ Detailed status
echo   04_STOP.lnk .............. Stop system
echo   05_VIEW_LOGS.lnk ......... View logs
echo   00_GUIDE.lnk ............. This guide
echo.
echo Scripts (.bat):
echo   Same as .lnk files (alternative)
echo.
echo Auto-generated files:
echo   whale_signal.json ........ Signal (15-min update)
echo   macro_state.json ......... Market environment
echo   logs/ ..................... Detailed logs
echo.
echo ===== DAILY OPERATION =====
echo.
echo Morning:   Click 01_START.lnk
echo Throughout: Click 02_DASHBOARD.lnk multiple times
echo Evening:  Click 04_STOP.lnk
echo.
pause
