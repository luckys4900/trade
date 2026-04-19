# BTC Whale Discovery & Expected Value Analysis System

## Overview
Automated system that discovers new BTC whale wallets daily, measures expected value through backtesting, and generates reports.

## Daily Execution (UTC 00:00)

### System Flow
1. **Scraping**: Blockchair API → Top 50 BTC whales
2. **Analysis**: ROI calculation from first inflow
3. **Backtesting**: Buy & Hold strategy
4. **Reporting**: JSON + Japanese reports

### Outputs
- `data/whales_daily_YYYYMMDD_HHMMSS.json` - Snapshot
- `data/backtest_results_YYYYMMDD_HHMMSS.json` - Backtest
- `data/backtest_report_YYYYMMDD_HHMMSS.txt` - Report
- `logs/btc_whale_YYYYMMDD.log` - Log

## Running

```bash
python -c "from btc_whale_system import MasterAgent; MasterAgent().run_daily_cycle()"
```

## Scheduler

```bash
python btc_whale_scheduler.py
```
