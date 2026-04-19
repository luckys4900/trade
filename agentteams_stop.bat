@echo off
title GLM Agent Teams - Stop

echo ========================================
echo     GLM Agent Teams Stop
echo ========================================
echo.

echo [INFO] Stopping GLM Agent Teams...

taskkill /F /IM pythonw.exe >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [OK] pythonw.exe stopped.
) else (
    echo [INFO] pythonw.exe was not running.
)

taskkill /F /IM wscript.exe >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [OK] wscript.exe stopped.
)

echo.
echo [INFO] All GLM Agent Teams processes stopped.
echo.
pause
