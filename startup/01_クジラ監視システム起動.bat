@echo off
REM エラーをログに出力
setlocal enabledelayedexpansion

REM 親ディレクトリを設定
for %%I in ("%~dp0.") do set "STARTUP_DIR=%%~fI"
for %%I in ("%STARTUP_DIR%\.") do set "TRADE_DIR=%%~fI"

REM ウィンドウを見えるようにする
mode con: cols=100 lines=30

title クジラ監視システム起動
chcp 65001 >nul

cls
echo.
echo ============================================================
echo  Whale Monitoring System Launcher
echo ============================================================
echo.
echo Startup Folder: %STARTUP_DIR%
echo Trade Folder:   %TRADE_DIR%
echo.

REM ディレクトリが存在するか確認
if not exist "%TRADE_DIR%" (
    echo.
    echo ERROR: Trade directory not found!
    echo Expected: %TRADE_DIR%
    echo.
    pause
    exit /b 1
)

echo [OK] Directory found
echo.

REM 必須ファイルの確認
if not exist "%TRADE_DIR%\whale_monitor.py" (
    echo ERROR: whale_monitor.py not found in %TRADE_DIR%
    pause
    exit /b 1
)

if not exist "%TRADE_DIR%\macro_filter.py" (
    echo ERROR: macro_filter.py not found in %TRADE_DIR%
    pause
    exit /b 1
)

echo [OK] Required files found
echo.

REM 既に実行中かチェック
tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if not errorlevel 1 (
    cls
    echo.
    echo ============================================================
    echo  ALREADY RUNNING
    echo ============================================================
    echo.
    echo The system is already active.
    echo.
    echo Options:
    echo  1. Run "03_システム状態確認.bat" to check status
    echo  2. Run "04_全システム停止.bat" to stop
    echo.
    pause
    exit /b 0
)

cls
echo.
echo ============================================================
echo  Starting System...
echo ============================================================
echo.

REM 起動スクリプト
cd /d "%TRADE_DIR%"

echo [1/3] Starting Whale Monitor...
start "Whale Monitor" /MIN pythonw.exe whale_monitor.py
timeout /t 2 /nobreak >nul

echo [2/3] Starting Macro Filter...
start "Macro Filter" /MIN pythonw.exe macro_filter.py
timeout /t 2 /nobreak >nul

echo [3/3] Starting Main Bot...
if exist "Qwen_Background_Start.vbs" (
    start "" "Qwen_Background_Start.vbs"
)

timeout /t 3 /nobreak >nul

REM 確認画面
cls
echo.
echo ============================================================
echo  STARTUP COMPLETE
echo ============================================================
echo.

tasklist | find "python" >nul
if not errorlevel 1 (
    echo SUCCESS: Systems are running
    echo.
    echo Running processes:
    tasklist | find "python"
) else (
    echo WARNING: Could not verify processes
)

echo.
echo Next: Run "03_システム状態確認.bat" to check status
echo.
pause
