@echo off
title Qwen Unified Backtest & Dashboard
echo ============================================================
echo  Running Backtest with Latest Data...
echo ============================================================
python qwen_unified_strategy.py

echo.
echo ============================================================
echo  Generating TradingView Interactive Chart...
echo ============================================================
python generate_tv_dashboard.py

echo.
echo Chart opened in your default web browser!
pause