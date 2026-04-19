@echo off
chcp 65001 >nul
title Uninstall RSI Swing v6 Autostart

echo ============================================================
echo  BTC/USDT 4H RSI SWING v6 - AUTOSTART REMOVE
echo ============================================================
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "WRAPPER_BAT=%STARTUP_DIR%\HL_Trader_Autostart.bat"

echo スタートアップから自動起動設定を削除します...
echo 対象ファイル: "%WRAPPER_BAT%"
echo.

if not exist "%WRAPPER_BAT%" (
    echo 自動起動用バッチは存在しません。
    echo すでに削除済みの可能性があります。
    echo.
    pause
    exit /b 0
)

del "%WRAPPER_BAT%" >nul 2>&1

if exist "%WRAPPER_BAT%" (
    echo.
    echo 自動起動用バッチの削除に失敗しました。
    pause
    exit /b 1
)

echo.
echo 自動起動設定を削除しました。
echo.
pause

