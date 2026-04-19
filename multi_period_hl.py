# -*- coding: utf-8 -*-
"""Multi-period backtest for Hyperliquid version"""

import os
import subprocess

periods = [
    (60, "2 months"),
    (90, "3 months"),
    (180, "6 months"),
    (365, "1 year"),
]

print("=" * 100)
print(" BTC/USDT 4H ADAPTIVE RSI v5 - HYPERLIQUID EDITION")
print(" MULTI-PERIOD BACKTEST")
print("=" * 100)

results = []

for days, desc in periods:
    print(f"\n{'='*100}")
    print(f" Testing: {desc} ({days} days)")
    print(f"{'='*100}")
    
    # Delete cache
    csv_path = "btc_usdt_4h.csv"
    if os.path.exists(csv_path):
        os.remove(csv_path)
        print(f"Cache deleted for fresh data")
    
    # Run backtest
    result = subprocess.run(
        ["python", "force_run_hl.py", "--mode", "backtest", "--days", str(days)],
        cwd="c:\\Users\\user\\Desktop\\cursor\\trade",
        capture_output=True,
        text=True
    )
    
    output = result.stdout
    
    # Parse output
    import re
    final_value = total_return = max_dd = sharpe = 0
    trades = win_rate = profit_factor = expectancy = 0
    sl_rate = rsi_rate = 0
    long_trades = short_trades = long_wr = short_wr = 0
    
    for line in output.split('\n'):
        if 'Final Value' in line:
            m = re.search(r'\$([\d,]+\.?\d*)', line)
            if m: final_value = float(m.group(1).replace(',', ''))
        elif 'Total Return' in line:
            m = re.search(r'([+-]?\d+\.?\d*)%', line)
            if m: total_return = float(m.group(1))
        elif 'Max Drawdown' in line:
            m = re.search(r'([\d,]+\.?\d*)%', line)
            if m: max_dd = float(m.group(1).replace(',', ''))
        elif 'Sharpe' in line and '(ann.)' not in line:
            m = re.search(r'([+-]?\d+\.?\d*)', line)
            if m: sharpe = float(m.group(1))
        elif 'Trades' in line and 'LONG' not in line and 'SHORT' not in line:
            m = re.search(r':\s*(\d+)', line)
            if m: trades = int(m.group(1))
        elif 'Win Rate' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)%', line)
            if m: win_rate = float(m.group(1).replace(',', ''))
        elif 'Profit Factor' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)', line)
            if m: profit_factor = float(m.group(1).replace(',', ''))
        elif 'Expectancy' in line:
            m = re.search(r'\$([+-]?[\d,]+\.?\d*)', line)
            if m: expectancy = float(m.group(1).replace(',', ''))
        elif 'Stop Loss rate' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)%', line)
            if m: sl_rate = float(m.group(1).replace(',', ''))
        elif 'RSI Exit rate' in line:
            m = re.search(r':\s*([\d,]+\.?\d*)%', line)
            if m: rsi_rate = float(m.group(1).replace(',', ''))
        elif 'LONG trades' in line:
            m = re.search(r':\s*(\d+)', line)
            if m: long_trades = int(m.group(1))
        elif 'SHORT trades' in line:
            m = re.search(r':\s*(\d+)', line)
            if m: short_trades = int(m.group(1))
        elif 'WR' in line and 'LONG' in line:
            m = re.search(r'WR\s*([\d,]+\.?\d*)%', line)
            if m: long_wr = float(m.group(1).replace(',', ''))
        elif 'WR' in line and 'SHORT' in line:
            m = re.search(r'WR\s*([\d,]+\.?\d*)%', line)
            if m: short_wr = float(m.group(1).replace(',', ''))
    
    results.append({
        "period": desc, "days": days, "final_value": final_value,
        "total_return": total_return, "max_dd": max_dd, "sharpe": sharpe,
        "trades": trades, "win_rate": win_rate, "profit_factor": profit_factor,
        "expectancy": expectancy, "sl_rate": sl_rate, "rsi_rate": rsi_rate,
        "long_trades": long_trades, "short_trades": short_trades,
        "long_wr": long_wr, "short_wr": short_wr
    })

# Summary
print("\n" + "=" * 100)
print(" MULTI-PERIOD BACKTEST SUMMARY (Hyperliquid Edition)")
print("=" * 100)
print(f"{'Period':<15} {'Return':>10} {'MaxDD':>8} {'Trades':>8} {'WR':>6} {'PF':>6} {'EV':>12} {'SL%':>6} {'LONG':>6} {'SHORT':>6}")
print("-" * 100)

for r in results:
    return_str = f"{r['total_return']:+.2f}%"
    print(f"{r['period']:<15} {return_str:>10} {r['max_dd']:>7.2f}% {r['trades']:>8} {r['win_rate']:>5.1f}% {r['profit_factor']:>6.2f} ${r['expectancy']:>+10,.2f} {r['sl_rate']:>5.1f}% {r['long_trades']:>6} {r['short_trades']:>6}")

print("=" * 100)

# Analysis
positive = sum(1 for r in results if r['total_return'] > 0)
avg_return = sum(r['total_return'] for r in results) / len(results)
avg_dd = sum(r['max_dd'] for r in results) / len(results)
avg_wr = sum(r['win_rate'] for r in results) / len(results)
avg_pf = sum(r['profit_factor'] for r in results) / len(results)

print(f"\nProfitable Periods: {positive}/{len(results)}")
print(f"Average Return: {avg_return:+.2f}%")
print(f"Average MaxDD: {avg_dd:.2f}%")
print(f"Average WR: {avg_wr:.1f}%")
print(f"Average PF: {avg_pf:.2f}")

if positive == len(results) and avg_wr > 50 and avg_pf > 1.5:
    print("\n>>> ROBUST: Strategy stable across all periods - READY for paper trading")
elif positive >= len(results) * 0.75:
    print("\n>>> MODERATE: Strategy shows promise - Proceed with caution")
else:
    print("\n>>> WEAK: Inconsistent performance - Needs improvement")
