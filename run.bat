@echo off
setlocal
chcp 65001 >nul
title JPX Consistency Backtest Runner

REM -----------------------------------------------------------------
REM JPX pre-trade consistency + backtest launcher
REM Update these macro inputs before each run (08:30 JST refresh).
REM -----------------------------------------------------------------

set CODE=2802
set START=2023-01-01
set END=2026-04-22
set CASH=1000000

REM Example: +0.88 means +0.88%
set NIKKEI_CHANGE_PCT=0.88
set NIKKEI_FUTURES_CHANGE_PCT=-1.28
set WTI_CHANGE_PCT=0.00

REM Leave blank if unknown. Missing core drivers force GAP=N/A.
set ALPHA_COMPONENT=

set MACRO_SENTIMENT=RISK_ON
set NEWS_BIAS=BEARISH

REM Optional. Empty means "now".
set PDC_TIMESTAMP=

echo ============================================================
echo  JPX Consistency Audit + Backtest
echo ============================================================
echo.
echo Code: %CODE%
echo Period: %START% to %END%
echo Cash: %CASH%
echo Nikkei: %NIKKEI_CHANGE_PCT%%% ^| Futures: %NIKKEI_FUTURES_CHANGE_PCT%%% ^| WTI: %WTI_CHANGE_PCT%%%
echo Regime input: %MACRO_SENTIMENT% + %NEWS_BIAS%
echo.

if "%PDC_TIMESTAMP%"=="" (
  python run_jpx_backtest.py ^
    --code %CODE% ^
    --start %START% ^
    --end %END% ^
    --cash %CASH% ^
    --nikkei-change-pct %NIKKEI_CHANGE_PCT% ^
    --nikkei-futures-change-pct %NIKKEI_FUTURES_CHANGE_PCT% ^
    --wti-change-pct %WTI_CHANGE_PCT% ^
    --macro-sentiment %MACRO_SENTIMENT% ^
    --news-bias %NEWS_BIAS%
) else (
  python run_jpx_backtest.py ^
    --code %CODE% ^
    --start %START% ^
    --end %END% ^
    --cash %CASH% ^
    --nikkei-change-pct %NIKKEI_CHANGE_PCT% ^
    --nikkei-futures-change-pct %NIKKEI_FUTURES_CHANGE_PCT% ^
    --wti-change-pct %WTI_CHANGE_PCT% ^
    --macro-sentiment %MACRO_SENTIMENT% ^
    --news-bias %NEWS_BIAS% ^
    --pdc-timestamp %PDC_TIMESTAMP%
)

echo.
echo Completed.
pause
