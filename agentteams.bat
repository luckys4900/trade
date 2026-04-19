@echo off
title GLM Agent Teams - Auto Launcher

echo ========================================
echo     GLM Agent Teams Auto Launcher
echo ========================================
echo.

REM Check if already running
tasklist /FI "IMAGENAME eq pythonw.exe" 2>NUL | find /I "pythonw.exe" > NUL
if %ERRORLEVEL% == 0 (
    echo [INFO] GLM Agent Teams is already running.
    goto :end
)

REM Check .env file
echo [INFO] Checking environment...
if not exist ".env" (
    echo [ERROR] .env file not found.
    if exist ".env.example" (
        copy .env.example .env >nul 2>&1
        echo [INFO] .env file created from .env.example
    )
    echo [INFO] Please edit .env and set your API keys.
    pause
    exit /b 1
)

REM Check Python
echo [INFO] Checking Python...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+.
    pause
    exit /b 1
)
echo [OK] Python found.

REM Check openai-swarm
echo [INFO] Checking openai-swarm...
python -c "import swarm" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing openai-swarm...
    pip install openai-swarm
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install openai-swarm.
        pause
        exit /b 1
    )
)
echo [OK] openai-swarm ready.

REM Check Ollama
echo [INFO] Checking Ollama...
curl -s http://localhost:11434/api/version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Ollama is not running.
    echo [INFO] Start Ollama first: ollama serve
    echo.
    set /p continue="Continue anyway? (y/n): "
    if /i "%continue%" neq "y" exit /b 0
)
echo [OK] Ollama running.

REM Check main script
if not exist "glm_master_swarm.py" (
    echo [ERROR] glm_master_swarm.py not found.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] All checks passed. Starting GLM Agent Teams...
echo.

python glm_master_swarm.py

echo.
echo [INFO] GLM Agent Teams has exited.
pause
