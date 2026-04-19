@echo off
title Debug Startup
cls

echo Debug: Batch file execution started

set LOG_FILE=%~dp0startup_debug.log

echo. >> %LOG_FILE%
echo === Startup Debug Log === >> %LOG_FILE%
echo Time: %date% %time% >> %LOG_FILE%
echo. >> %LOG_FILE%

echo.
echo Startup folder: %~dp0 >> %LOG_FILE%
echo Startup folder: %~dp0

cd ..
echo Changed to: %CD% >> %LOG_FILE%
echo Changed to: %CD%

echo. >> %LOG_FILE%
echo Checking Python: >> %LOG_FILE%
tasklist | find "python" >> %LOG_FILE%
echo. >> %LOG_FILE%

echo.
echo Log saved to: %LOG_FILE%
echo.
echo This debug window will close in 10 seconds...
timeout /t 10

