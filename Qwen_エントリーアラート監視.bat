@echo off
echo ============================================================
echo  Qwen OCPM Signal Monitor - Alert System
echo  Monitors BTC/USDT 4H and alerts on entry signals
echo ============================================================
echo.
echo  This window must stay open. Minimize it.
echo  You will get a popup + sound when a signal appears.
echo.
echo  Alert levels:
echo    WARNING = Signal approaching (RSI near threshold)
echo    SIGNAL  = Entry confirmed (popup + sound)
echo.
pause

cd /d "%~dp0"

python qwen_ocpm_signal_monitor.py

pause
