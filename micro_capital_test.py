# -*- coding: utf-8 -*-
"""Micro-capital ($100) multi-period test"""

import os
import subprocess

periods = [
    (60, "2 months"),
    (90, "3 months"),
    (180, "6 months"),
    (365, "1 year"),
]

print("=" * 100)
print(" BTC/USDT 4H ADAPTIVE RSI v5 - MICRO-CAPITAL ($100) TEST")
print(" HYPERLIQUID EDITION")
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
    skipped_count = 0  # Track min notional skips
    
    for line in output.split('\n'):
        if 'SKIP' in line and 'Notional' in line:
            skipped_count += 1
        elif 'Final Value' in line:
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
        "long_wr": long_wr, "short_wr": short_wr, "skipped": skipped_count
    })

# Summary
print("\n" + "=" * 100)
print(" MICRO-CAPITAL ($100) BACKTEST SUMMARY")
print("=" * 100)
print(f"{'Period':<15} {'Return':>10} {'MaxDD':>8} {'Trades':>8} {'WR':>6} {'PF':>6} {'EV':>10} {'SL%':>6} {'LONG':>6} {'SHORT':>6} {'Skip':>6}")
print("-" * 100)

for r in results:
    return_str = f"{r['total_return']:+.2f}%"
    print(f"{r['period']:<15} {return_str:>10} {r['max_dd']:>7.2f}% {r['trades']:>8} {r['win_rate']:>5.1f}% {r['profit_factor']:>6.2f} ${r['expectancy']:>+8.2f} {r['sl_rate']:>5.1f}% {r['long_trades']:>6} {r['short_trades']:>6} {r['skipped']:>6}")

print("=" * 100)

# Analysis
positive = sum(1 for r in results if r['total_return'] > 0)
total_skips = sum(r['skipped'] for r in results)
avg_return = sum(r['total_return'] for r in results) / len(results)
avg_dd = sum(r['max_dd'] for r in results) / len(results)
avg_wr = sum(r['win_rate'] for r in results) / len(results)
avg_pf = sum(r['profit_factor'] for r in results) / len(results)

print(f"\nProfitable Periods: {positive}/{len(results)}")
print(f"Total Skipped (Min Notional): {total_skips}")
print(f"Average Return: {avg_return:+.2f}%")
print(f"Average MaxDD: {avg_dd:.2f}%")
print(f"Average WR: {avg_wr:.1f}%")
print(f"Average PF: {avg_pf:.2f}")

# Comparison with $100k
print("\n" + "=" * 100)
print(" COMPARISON: $100k (Standard) vs $100 (Micro-Capital)")
print("=" * 100)

# Standard results from earlier test (6 months)
std_return = +7.64
std_dd = 2.81
std_wr = 60.0
std_pf = 10.00
std_trades = 5

# Micro results (6 months)
micro_return = [r['total_return'] for r in results if r['days'] == 180][0] if results else 0
micro_dd = [r['max_dd'] for r in results if r['days'] == 180][0] if results else 0
micro_wr = [r['win_rate'] for r in results if r['days'] == 180][0] if results else 0
micro_pf = [r['profit_factor'] for r in results if r['days'] == 180][0] if results else 0
micro_trades = [r['trades'] for r in results if r['days'] == 180][0] if results else 0

print(f"{'Metric':<20} {'Standard ($100k)':>20} {'Micro ($100)':>15} {'Diff':>10}")
print("-" * 100)
print(f"{'Total Return':<20} {std_return:>+15.2f}% {micro_return:>+15.2f}% {(micro_return/std_return-1)*100:+.2f}%")
print(f"{'Max Drawdown':<20} {std_dd:>15.2f}% {micro_dd:>15.2f}% {(micro_dd/std_dd-1)*100:+.2f}%")
print(f"{'Win Rate':<20} {std_wr:>15.1f}% {micro_wr:>15.1f}% {(micro_wr/std_wr-1)*100:+.2f}%")
print(f"{'Profit Factor':<20} {std_pf:>15.2f} {micro_pf:>15.2f} {(micro_pf/std_pf-1)*100:+.2f}%")
print(f"{'Trades':<20} {std_trades:>15} {micro_trades:>15} {(micro_trades/std_trades-1)*100:+.2f}%")

print("=" * 100)

# Conclusion
if positive == len(results) and avg_wr > 50 and avg_pf > 1.5:
    verdict = ">>> ROBUST: Strategy works with $100 capital - READY for micro-trading <<<"
elif positive >= len(results) * 0.75:
    verdict = ">>> MODERATE: Strategy shows promise - Proceed with caution <<<"
else:
    verdict = ">>> WEAK: Inconsistent performance - Needs improvement <<<"

print("\n" + "=" * 100)
print(" FINAL VERDICT")
print("=" * 100)
print(verdict)
print("=" * 100)
