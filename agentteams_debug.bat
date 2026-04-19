@echo off
title GLM Agent Teams - Debug Mode

echo ========================================
echo     GLM Agent Teams - Debug Mode
echo ========================================
echo.

echo [DEBUG] Current directory: %CD%
echo [DEBUG] Arguments: %*
echo.

REM Check pythonw process
echo [DEBUG] Checking pythonw process...
tasklist /FI "IMAGENAME eq pythonw.exe" 2>NUL | find /I "pythonw.exe" > NUL
if %ERRORLEVEL% == 0 (
    echo [INFO] GLM Agent Teams is already running.
    goto :end
) else (
    echo [DEBUG] pythonw.exe not running.
)

REM Check .env
echo.
echo [DEBUG] Checking .env...
if exist ".env" (
    echo [DEBUG] .env exists.
) else (
    echo [DEBUG] .env NOT found.
    if exist ".env.example" (
        copy .env.example .env >nul 2>&1
        echo [DEBUG] .env created from .env.example.
    ) else (
        echo [DEBUG] .env.example also NOT found.
    )
)

REM Check Python
echo.
echo [DEBUG] Checking Python...
python --version
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found.
    where python
    pause
    exit /b 1
)
echo [DEBUG] Python OK.

REM Check openai-swarm
echo.
echo [DEBUG] Checking openai-swarm...
python -c "import swarm; print('openai-swarm: OK')"
if %ERRORLEVEL% neq 0 (
    echo [DEBUG] openai-swarm NOT installed. Installing...
    pip install openai-swarm
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install openai-swarm.
        pause
        exit /b 1
    )
)

REM Check Ollama
echo.
echo [DEBUG] Checking Ollama...
curl -s http://localhost:11434/api/version
if %ERRORLEVEL% neq 0 (
    echo [DEBUG] Ollama NOT running.
    echo [WARNING] Ollama is not running.
    echo [INFO] Start with: ollama serve
    echo.
    set /p continue="Continue anyway? (y/n): "
    if /i "%continue%" neq "y" exit /b 0
) else (
    echo [DEBUG] Ollama running.
)

REM Check main script
echo.
if exist "glm_master_swarm.py" (
    echo [DEBUG] glm_master_swarm.py found.
) else (
    echo [ERROR] glm_master_swarm.py NOT found.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] All checks passed.
echo [INFO] Starting GLM Agent Teams...

python glm_master_swarm.py

echo.
echo [INFO] GLM Agent Teams has exited.
pause
