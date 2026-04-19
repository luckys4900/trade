@echo off
echo ============================================================
echo  Qwen BTC Auto-Trader - Start Now (Background)
echo ============================================================
echo.
echo Starting the bot as a background task...
echo.

schtasks /run /tn "QwenBTCTrader"

if %errorlevel% equ 0 (
    echo SUCCESS - Bot started in background
    echo.
    echo  View logs:  Qwen_ログ確認.bat
    echo  Stop bot:   Qwen_自動売買_停止.bat
) else (
    echo ERROR - Task not found. Please run:
    echo   Qwen_バックグラウンド常駐設定.bat
    echo first to install the service.
)

pause
