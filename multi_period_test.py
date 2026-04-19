# -*- coding: utf-8 -*-
"""
Multi-Period Backtest for v5 Adaptive RSI
Tests strategy across multiple timeframes to verify stability
"""

import subprocess
import re

periods = [
    (60, "2 months"),
    (90, "3 months"),
    (180, "6 months"),
    (365, "1 year"),
    (730, "2 years"),
]

print("=" * 100)
print(" BTC/USDT 4H ADAPTIVE RSI v5 - MULTI-PERIOD BACKTEST")
print("=" * 100)

results = []

for days, desc in periods:
    print(f"\n{'='*100}")
    print(f" Testing: {desc} ({days} days)")
    print(f"{'='*100}")
    
    # Run backtest
    result = subprocess.run(
        ["python", "force_run.py", "--mode", "backtest", "--days", str(days)],
        cwd="c:\\Users\\user\\Desktop\\cursor\\trade",
        capture_output=True,
        text=True
    )
    
    output = result.stdout
    
    # Extract metrics from output
    final_value = 0
    total_return = 0
    max_dd = 0
    sharpe = 0
    trades = 0
    win_rate = 0
    profit_factor = 0
    expectancy = 0
    sl_rate = 0
    rsi_rate = 0
    long_trades = 0
    short_trades = 0
    long_wr = 0
    short_wr = 0
    
    for line in output.split('\n'):
        if 'Final Value' in line:
            m = re.search(r'\$([\d,]+\.?\d*)', line)
            if m:
                final_value = float(m.group(1).replace(',', ''))
        elif 'Total Return' in line:
            m = re.search(r'([+-]?\d+\.?\d*)%', line)
            if m:
                total_return = float(m.group(1))
        elif 'Max Drawdown' in line:
            m = re.search(r'([\d,]+\.?\d*)%', line)
            if m:
                max_dd = float(m.group(1).replace(',', ''))
        elif 'Sharpe' in line and '(ann.)' not in line:
            m = re.search(r'([+-]?\d+\.?\d*)', line)
            if m:
                sharpe = float(m.group(1))
        elif 'Trades' in line and 'LONG' not in line and 'SHORT' not in line:
            m = re.search(r':\s*(\d+)', line)
            if m:
                trades = int(m.group(1))
        elif 'Win Rate' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)%', line)
            if m:
                win_rate = float(m.group(1).replace(',', ''))
        elif 'Profit Factor' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)', line)
            if m:
                profit_factor = float(m.group(1).replace(',', ''))
        elif 'Expectancy' in line:
            m = re.search(r'\$([+-]?[\d,]+\.?\d*)', line)
            if m:
                expectancy = float(m.group(1).replace(',', ''))
        elif 'Stop Loss rate' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)%', line)
            if m:
                sl_rate = float(m.group(1).replace(',', ''))
        elif 'RSI Exit rate' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)%', line)
            if m:
                rsi_rate = float(m.group(1).replace(',', ''))
        elif 'LONG trades' in line:
            m = re.search(r':\s*(\d+)', line)
            if m:
                long_trades = int(m.group(1))
        elif 'SHORT trades' in line:
            m = re.search(r':\s*(\d+)', line)
            if m:
                short_trades = int(m.group(1))
        elif 'WR' in line and 'LONG' in line:
            m = re.search(r'WR\s*([\d,]+\.?\d*)%', line)
            if m:
                long_wr = float(m.group(1).replace(',', ''))
        elif 'WR' in line and 'SHORT' in line:
            m = re.search(r'WR\s*([\d,]+\.?\d*)%', line)
            if m:
                short_wr = float(m.group(1).replace(',', ''))
    
    results.append({
        "period": desc,
        "days": days,
        "final_value": final_value,
        "total_return": total_return,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "trades": trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "sl_rate": sl_rate,
        "rsi_rate": rsi_rate,
        "long_trades": long_trades,
        "short_trades": short_trades,
        "long_wr": long_wr,
        "short_wr": short_wr
    })

# Summary Report
print("\n" + "=" * 100)
print(" MULTI-PERIOD BACKTEST SUMMARY")
print("=" * 100)

print(f"{'Period':<15} {'Return':>10} {'MaxDD':>8} {'Sharpe':>8} {'Trades':>8} {'WR':>6} {'PF':>6} {'EV':>12} {'SL%':>6} {'LONG':>6} {'SHORT':>6}")
print("-" * 100)

for r in results:
    return_str = f"{r['total_return']:+.2f}%"
    print(f"{r['period']:<15} {return_str:>10} {r['max_dd']:>7.2f}% {r['sharpe']:>8.4f} {r['trades']:>8} {r['win_rate']:>5.1f}% {r['profit_factor']:>6.2f} ${r['expectancy']:>+10,.2f} {r['sl_rate']:>5.1f}% {r['long_trades']:>6} {r['short_trades']:>6}")

print("=" * 100)

# Analysis
print("\n" + "=" * 70)
print(" STABILITY ANALYSIS")
print("=" * 70)

positive_returns = sum(1 for r in results if r['total_return'] > 0)
total_results = len(results)

print(f"\nProfitable Periods: {positive_returns}/{total_results} ({positive_returns/total_results*100:.1f}%)")

if positive_returns == total_results:
    print("\n>>> EXCELLENT: Strategy profitable across ALL periods")
elif positive_results >= total_results * 0.75:
    print("\n>>> GOOD: Strategy profitable in most periods")
else:
    print("\n>>> CONCERN: Strategy inconsistent across periods")

avg_return = sum(r['total_return'] for r in results) / total_results
print(f"Average Return: {avg_return:+.2f}%")

avg_dd = sum(r['max_dd'] for r in results) / total_results
print(f"Average MaxDD: {avg_dd:.2f}%")

avg_wr = sum(r['win_rate'] for r in results) / total_results
print(f"Average Win Rate: {avg_wr:.1f}%")

avg_pf = sum(r['profit_factor'] for r in results) / total_results
print(f"Average Profit Factor: {avg_pf:.2f}")

# Long vs Short analysis
total_long = sum(r['long_trades'] for r in results)
total_short = sum(r['short_trades'] for r in results)
print(f"\nTotal LONG trades: {total_long}")
print(f"Total SHORT trades: {total_short}")

long_periods_wins = sum(1 for r in results if r['long_trades'] > 0)
short_periods_wins = sum(1 for r in results if r['short_trades'] > 0)
print(f"Periods with LONG trades: {long_periods_wins}/{total_results}")
print(f"Periods with SHORT trades: {short_periods_wins}/{total_results}")

print("\n" + "=" * 70)
print(" FINAL VERDICT")
print("=" * 70)

if positive_returns == total_results and avg_wr > 50 and avg_pf > 1.5:
    print("\n>>> ROBUST: Strategy is stable and profitable across all tested periods")
    print(">>> Recommendation: READY for paper trading")
elif positive_returns >= total_results * 0.75 and avg_wr > 45:
    print("\n>>> MODERATE: Strategy shows promise but needs monitoring")
    print(">>> Recommendation: Proceed with caution, extend testing")
else:
    print("\n>>> WEAK: Strategy performance is inconsistent")
    print(">>> Recommendation: Re-evaluate parameters or approach")

print("=" * 70)
