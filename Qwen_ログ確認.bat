@echo off
echo ============================================================
echo  Qwen Unified Trader - Log Viewer
echo ============================================================
echo.

set LOG_DIR=%~dp0logs

if not exist "%LOG_DIR%" (
    echo No logs directory found.
    pause
    exit /b 1
)

echo Latest log files:
echo.
dir /b /o-d "%LOG_DIR%\unified_live_*.log" 2>nul | findstr /n "^" | findstr "^1:" > "%TEMP%\latest_log.txt"
set /p LATEST_FILE=<"%TEMP%\latest_log.txt"
set LATEST_FILE=%LATEST_FILE:*:=%

if not defined LATEST_FILE (
    echo No unified_live log files found.
    echo Checking for any log files...
    dir /b /o-d "%LOG_DIR%\*.log" 2>nul | findstr /n "^" | findstr "^1:" > "%TEMP%\latest_log.txt"
    set /p LATEST_FILE=<"%TEMP%\latest_log.txt"
    set LATEST_FILE=%LATEST_FILE:*:=%
    if not defined LATEST_FILE (
        echo No log files found at all.
        pause
        exit /b 1
    )
)

echo Opening: %LATEST_FILE%
echo.

for %%F in ("%LOG_DIR%\%LATEST_FILE%") do set FILE_SIZE=%%~zF
echo File size: %FILE_SIZE% bytes
echo.
echo ============================================================
echo  Latest 50 lines:
echo ============================================================
echo.

powershell -Command "Get-Content '%LOG_DIR%\%LATEST_FILE%' -Tail 50"

echo.
echo ============================================================
echo  Process status:
echo ============================================================
powershell -Command "Get-Process | Where-Object { $_.ProcessName -like '*python*' } | Select-Object ProcessName, Id, StartTime | Format-Table -AutoSize"

echo.
echo ============================================================
echo  Current trade state:
echo ============================================================
if exist "%~dp0trade_state_unified.json" (
    powershell -Command "Get-Content '%~dp0trade_state_unified.json'"
) else (
    echo No state file found.
)

echo.
echo ============================================================
pause
