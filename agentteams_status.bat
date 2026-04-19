@echo off
title GLM Agent Teams - Status

echo ========================================
echo     GLM Agent Teams Status Check
echo ========================================
echo.

REM Check pythonw process
echo [INFO] Checking pythonw process...
tasklist /FI "IMAGENAME eq pythonw.exe" 2>NUL | find /I "pythonw.exe" > NUL
if %ERRORLEVEL% == 0 (
    echo [RUNNING] GLM Agent Teams is running.
    tasklist /FI "IMAGENAME eq pythonw.exe" /FO TABLE | find "pythonw"
) else (
    echo [STOPPED] GLM Agent Teams is not running.
)

REM Check Ollama
echo.
echo [INFO] Checking Ollama...
curl -s http://localhost:11434/api/version >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [RUNNING] Ollama is running.
) else (
    echo [STOPPED] Ollama is not running.
    echo [INFO] Start with: ollama serve
)

REM Check .env
echo.
echo [INFO] Checking config...
if exist ".env" (
    echo [OK] .env file exists.
) else (
    echo [ERROR] .env file not found.
)

echo.
echo ========================================
echo Commands:
echo   agentteams.bat        - Start
echo   agentteams_status.bat - Status
echo   agentteams_stop.bat   - Stop
echo ========================================
echo.
pause
