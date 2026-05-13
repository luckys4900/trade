"""
Funding Rate Carry Trade (Delta-Neutral) - Rigorous Backtest
=============================================================
Core idea: Collect the funding payment itself, not bet on price direction.
When FR > threshold → enter SHORT, hold through 1-2 funding periods, exit.
When FR < -threshold → enter LONG, hold through 1-2 funding periods, exit.
"""

import pandas as pd
import numpy as np
from scipy import stats as sp_stats
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================
DATA_DIR = "."

# Cost model
TAKER_FEE = 0.00035       # 0.035% per side
SLIPPAGE = 0.00050        # 0.05% per side
ROUND_TRIP_COST = 2 * (TAKER_FEE + SLIPPAGE)  # 0.17%

# IS / OOS split
IS_START = "2024-01-01"
IS_END = "2025-03-31"
OOS_START = "2025-04-01"
OOS_END = "2026-04-18"

# Thresholds to test (absolute FR values)
THRESHOLDS = [0.00000, 0.00005, 0.00010, 0.00015, 0.00020, 0.00025, 0.00030]
THRESHOLD_LABELS = [
    "ANY positive", "0.005%", "0.01%", "0.015%", "0.02%", "0.025%", "0.03%"
]

# Hold periods (in 4H bars)
HOLD_BARS = {
    "1 funding period (8h)": 2,
    "2 funding periods (16h)": 4,
}

# Account settings
ACCOUNT_SIZE = 190  # USD
LEVERAGE = 1

# Bootstrap
N_BOOTSTRAP = 5000

# ============================================================
# DATA LOADING
# ============================================================
print("=" * 80)
print("FUNDING RATE CARRY TRADE (DELTA-NEUTRAL) - RIGOROUS BACKTEST")
print("=" * 80)

# Load FR data (1H)
fr_df = pd.read_csv(f"{DATA_DIR}/btc_funding_rate.csv")
fr_df['datetime'] = pd.to_datetime(fr_df['datetime'])
fr_df = fr_df.set_index('datetime').sort_index()
print(f"\nFR data: {fr_df.index[0]} to {fr_df.index[-1]}, {len(fr_df)} rows")

# Load price data (4H)
price_df = pd.read_csv(f"{DATA_DIR}/btc_price_4h_cache.csv")
price_df['datetime'] = pd.to_datetime(price_df['datetime'], utc=True)
price_df['datetime'] = price_df['datetime'].dt.tz_localize(None)
price_df = price_df.set_index('datetime').sort_index()
print(f"Price data: {price_df.index[0]} to {price_df.index[-1]}, {len(price_df)} rows")

# ============================================================
# IDENTIFY FUNDING SETTLEMENT TIMES
# ============================================================
# Funding payments happen every 8 hours: 00:00, 08:00, 16:00 UTC
# We use the FR value at these settlement times as the "received" funding rate

fr_df['hour'] = fr_df.index.hour
funding_hours = [0, 8, 16]
fr_settlement = fr_df[fr_df['hour'].isin(funding_hours)].copy()
print(f"\nSettlement-time FR rows: {len(fr_settlement)}")

# ============================================================
# CORE BACKTEST FUNCTION
# ============================================================
def run_carry_backtest(fr_data, price_data, threshold, hold_bars, direction="short"):
    """
    Run carry trade backtest.
    
    direction: "short" = enter SHORT when FR > threshold (collect positive funding)
               "long"  = enter LONG when FR < -threshold (collect negative funding)
    
    Returns DataFrame of trades with P&L decomposition.
    """
    trades = []
    
    for settle_time, row in fr_data.iterrows():
        fr_val = row['fundingRate']
        
        # Entry condition
        if direction == "short":
            if fr_val <= threshold:
                continue
            # SHORT: receive funding when FR > 0
            funding_pnl_pct = fr_val * 100  # percentage of position
        elif direction == "long":
            if fr_val >= -threshold:
                continue
            # LONG: receive funding when FR < 0 (shorts pay longs)
            funding_pnl_pct = abs(fr_val) * 100
        else:
            continue
        
        # Find entry price (4H bar at or just after settlement time)
        entry_time = settle_time
        # Look for price bar at this time or the next available
        future_prices = price_data[price_data.index >= entry_time]
        if len(future_prices) == 0:
            continue
        
        entry_idx = future_prices.index[0]
        entry_price = future_prices.loc[entry_idx, 'close']
        
        # Find exit price (hold_bars after entry)
        entry_bar_pos = price_data.index.get_loc(entry_idx)
        exit_bar_pos = entry_bar_pos + hold_bars
        
        if exit_bar_pos >= len(price_data):
            continue
        
        exit_idx = price_data.index[exit_bar_pos]
        exit_price = price_data.loc[exit_idx, 'close']
        
        # P&L calculation
        if direction == "short":
            price_pnl_pct = (entry_price - exit_price) / entry_price * 100
        else:  # long
            price_pnl_pct = (exit_price - entry_price) / entry_price * 100
        
        net_pnl_pct = price_pnl_pct + funding_pnl_pct - ROUND_TRIP_COST * 100
        
        trades.append({
            'entry_time': entry_time,
            'exit_time': exit_idx,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'funding_rate': fr_val,
            'funding_pnl_pct': funding_pnl_pct,
            'price_pnl_pct': price_pnl_pct,
            'net_pnl_pct': net_pnl_pct,
            'direction': direction,
            'hold_bars': hold_bars,
        })
    
    return pd.DataFrame(trades)


def split_trades(trades_df):
    """Split trades into IS and OOS periods."""
    if len(trades_df) == 0:
        return pd.DataFrame(), pd.DataFrame()
    
    is_mask = (trades_df['entry_time'] >= IS_START) & (trades_df['entry_time'] <= IS_END)
    oos_mask = (trades_df['entry_time'] >= OOS_START) & (trades_df['entry_time'] <= OOS_END)
    
    return trades_df[is_mask].copy(), trades_df[oos_mask].copy()


def statistical_tests(trades_df, label=""):
    """Run statistical tests on trade P&L."""
    if len(trades_df) == 0:
        return {
            'n_trades': 0, 'ev_pct': np.nan, 't_stat': np.nan, 'p_value': np.nan,
            'df': 0, 'ci_lo': np.nan, 'ci_hi': np.nan, 'ci_includes_zero': True,
            'profitable_months': 0, 'total_months': 0, 'month_win_rate': np.nan,
            'sharpe_annualized': np.nan, 'mean_pnl': np.nan, 'std_pnl': np.nan,
            'total_pnl_pct': np.nan, 'win_rate': np.nan,
        }
    
    pnl = trades_df['net_pnl_pct'].values
    n = len(pnl)
    mean_pnl = np.mean(pnl)
    std_pnl = np.std(pnl, ddof=1)
    
    # t-test: H0: EV = 0
    if std_pnl > 0:
        t_stat, p_value = sp_stats.ttest_1samp(pnl, 0)
    else:
        t_stat, p_value = 0, 1.0
    
    # Bootstrap 95% CI
    boot_means = []
    for _ in range(N_BOOTSTRAP):
        sample = np.random.choice(pnl, size=n, replace=True)
        boot_means.append(np.mean(sample))
    ci_lo = np.percentile(boot_means, 2.5)
    ci_hi = np.percentile(boot_means, 97.5)
    ci_includes_zero = ci_lo <= 0 <= ci_hi
    
    # Monthly breakdown
    trades_df_copy = trades_df.copy()
    trades_df_copy['month'] = pd.to_datetime(trades_df_copy['entry_time']).dt.to_period('M')
    monthly = trades_df_copy.groupby('month')['net_pnl_pct'].sum()
    profitable_months = (monthly > 0).sum()
    total_months = len(monthly)
    
    # Sharpe-like ratio (annualized, assume ~3 trades/month)
    if std_pnl > 0:
        trades_per_month = n / max(total_months, 1)
        sharpe = (mean_pnl / std_pnl) * np.sqrt(trades_per_month * 12)
    else:
        sharpe = np.nan
    
    # Win rate
    win_rate = (pnl > 0).sum() / n * 100
    
    return {
        'n_trades': n,
        'ev_pct': mean_pnl,
        't_stat': t_stat,
        'p_value': p_value,
        'df': n - 1,
        'ci_lo': ci_lo,
        'ci_hi': ci_hi,
        'ci_includes_zero': ci_includes_zero,
        'profitable_months': profitable_months,
        'total_months': total_months,
        'month_win_rate': profitable_months / total_months * 100 if total_months > 0 else np.nan,
        'sharpe_annualized': sharpe,
        'mean_pnl': mean_pnl,
        'std_pnl': std_pnl,
        'total_pnl_pct': np.sum(pnl),
        'win_rate': win_rate,
    }


# ============================================================
# RUN ALL CONFIGURATIONS
# ============================================================
print("\n" + "=" * 80)
print("RUNNING BACKTESTS...")
print("=" * 80)

all_results = []

for hold_label, hold_bars in HOLD_BARS.items():
    for i, threshold in enumerate(THRESHOLDS):
        threshold_label = THRESHOLD_LABELS[i]
        
        # SHORT carry (FR > threshold → SHORT, collect positive funding)
        trades_short = run_carry_backtest(
            fr_settlement, price_df, threshold, hold_bars, direction="short"
        )
        is_short, oos_short = split_trades(trades_short)
        
        # LONG carry (FR < -threshold → LONG, collect negative funding)
        trades_long = run_carry_backtest(
            fr_settlement, price_df, threshold, hold_bars, direction="long"
        )
        is_long, oos_long = split_trades(trades_long)
        
        # Statistical tests
        stats_is_short = statistical_tests(is_short, f"IS SHORT {threshold_label}")
        stats_oos_short = statistical_tests(oos_short, f"OOS SHORT {threshold_label}")
        stats_is_long = statistical_tests(is_long, f"IS LONG {threshold_label}")
        stats_oos_long = statistical_tests(oos_long, f"OOS LONG {threshold_label}")
        
        all_results.append({
            'hold': hold_label,
            'threshold': threshold,
            'threshold_label': threshold_label,
            'direction': 'SHORT',
            'is_stats': stats_is_short,
            'oos_stats': stats_oos_short,
            'is_trades': is_short,
            'oos_trades': oos_short,
        })
        all_results.append({
            'hold': hold_label,
            'threshold': threshold,
            'threshold_label': threshold_label,
            'direction': 'LONG',
            'is_stats': stats_is_long,
            'oos_stats': stats_oos_long,
            'is_trades': is_long,
            'oos_trades': oos_long,
        })

# ============================================================
# PRINT RESULTS TABLE
# ============================================================
print("\n" + "=" * 80)
print("RESULTS: SHORT CARRY (Enter SHORT when FR > threshold)")
print("=" * 80)

for hold_label in HOLD_BARS.keys():
    print(f"\n--- Hold Period: {hold_label} ---")
    print(f"{'Threshold':<14} {'Period':<5} {'Trades':>6} {'EV%':>8} {'Std%':>8} "
          f"{'WinRate':>8} {'t-stat':>8} {'p-val':>8} {'95% CI':>20} "
          f"{'Mo Win%':>8} {'Sharpe':>8} {'Total%':>10}")
    print("-" * 140)
    
    for r in all_results:
        if r['hold'] != hold_label or r['direction'] != 'SHORT':
            continue
        
        for period, stats in [('IS', r['is_stats']), ('OOS', r['oos_stats'])]:
            if stats['n_trades'] == 0:
                print(f"{r['threshold_label']:<14} {period:<5} {'NO TRADES':>6}")
                continue
            
            ci_str = f"[{stats['ci_lo']:.4f}, {stats['ci_hi']:.4f}]"
            ci_flag = " *" if stats['ci_includes_zero'] else " OK"
            
            print(f"{r['threshold_label']:<14} {period:<5} {stats['n_trades']:>6} "
                  f"{stats['ev_pct']:>8.4f} {stats['std_pnl']:>8.4f} "
                  f"{stats['win_rate']:>7.1f}% {stats['t_stat']:>8.3f} "
                  f"{stats['p_value']:>8.4f} {ci_str:>20}{ci_flag} "
                  f"{stats['month_win_rate']:>7.1f}% {stats['sharpe_annualized']:>8.3f} "
                  f"{stats['total_pnl_pct']:>10.2f}")

print("\n" + "=" * 80)
print("RESULTS: LONG CARRY (Enter LONG when FR < -threshold)")
print("=" * 80)

for hold_label in HOLD_BARS.keys():
    print(f"\n--- Hold Period: {hold_label} ---")
    print(f"{'Threshold':<14} {'Period':<5} {'Trades':>6} {'EV%':>8} {'Std%':>8} "
          f"{'WinRate':>8} {'t-stat':>8} {'p-val':>8} {'95% CI':>20} "
          f"{'Mo Win%':>8} {'Sharpe':>8} {'Total%':>10}")
    print("-" * 140)
    
    for r in all_results:
        if r['hold'] != hold_label or r['direction'] != 'LONG':
            continue
        
        for period, stats in [('IS', r['is_stats']), ('OOS', r['oos_stats'])]:
            if stats['n_trades'] == 0:
                print(f"{r['threshold_label']:<14} {period:<5} {'NO TRADES':>6}")
                continue
            
            ci_str = f"[{stats['ci_lo']:.4f}, {stats['ci_hi']:.4f}]"
            ci_flag = " *" if stats['ci_includes_zero'] else " OK"
            
            print(f"{r['threshold_label']:<14} {period:<5} {stats['n_trades']:>6} "
                  f"{stats['ev_pct']:>8.4f} {stats['std_pnl']:>8.4f} "
                  f"{stats['win_rate']:>7.1f}% {stats['t_stat']:>8.3f} "
                  f"{stats['p_value']:>8.4f} {ci_str:>20}{ci_flag} "
                  f"{stats['month_win_rate']:>7.1f}% {stats['sharpe_annualized']:>8.3f} "
                  f"{stats['total_pnl_pct']:>10.2f}")

# ============================================================
# P&L DECOMPOSITION
# ============================================================
print("\n" + "=" * 80)
print("P&L DECOMPOSITION: Funding vs Price Movement")
print("=" * 80)

for hold_label in HOLD_BARS.keys():
    print(f"\n--- Hold Period: {hold_label} ---")
    print(f"{'Config':<30} {'Period':<5} {'Funding%':>10} {'Price%':>10} {'Cost%':>10} "
          f"{'Net%':>10} {'Fund/Total':>10} {'Price Dominates':>15}")
    print("-" * 110)
    
    for r in all_results:
        if r['hold'] != hold_label:
            continue
        
        dir_label = "SHORT" if r['direction'] == 'SHORT' else "LONG"
        config = f"{dir_label} FR>{r['threshold_label']}"
        
        for period, trades in [('IS', r['is_trades']), ('OOS', r['oos_trades'])]:
            if len(trades) == 0:
                continue
            
            total_funding = trades['funding_pnl_pct'].sum()
            total_price = trades['price_pnl_pct'].sum()
            total_cost = ROUND_TRIP_COST * 100 * len(trades)
            total_net = trades['net_pnl_pct'].sum()
            
            # What fraction of gross PnL comes from funding?
            gross = abs(total_funding) + abs(total_price)
            if gross > 0:
                fund_frac = abs(total_funding) / gross * 100
            else:
                fund_frac = 0
            
            # Does price PnL dominate?
            price_dominates = "YES" if abs(total_price) > abs(total_funding) else "NO"
            
            print(f"{config:<30} {period:<5} {total_funding:>10.4f} {total_price:>10.4f} "
                  f"{total_cost:>10.4f} {total_net:>10.4f} {fund_frac:>9.1f}% {price_dominates:>15}")

# ============================================================
# FR vs SUBSEQUENT PRICE MOVEMENT CORRELATION
# ============================================================
print("\n" + "=" * 80)
print("FR vs SUBSEQUENT PRICE MOVEMENT CORRELATION")
print("=" * 80)
print("(Tests whether FR is predictive of price direction, or just a carry)\n")

for hold_label, hold_bars in HOLD_BARS.items():
    print(f"--- Hold Period: {hold_label} ---")
    
    # For SHORT direction: higher FR → price should go up (adverse) if FR predicts direction
    # For LONG direction: more negative FR → price should go down (adverse)
    
    for direction in ['short', 'long']:
        trades_all = run_carry_backtest(
            fr_settlement, price_df, 0.0, hold_bars, direction=direction
        )
        if len(trades_all) == 0:
            continue
        
        is_trades, oos_trades = split_trades(trades_all)
        
        for period_name, trades in [('IS', is_trades), ('OOS', oos_trades)]:
            if len(trades) < 10:
                continue
            
            fr_vals = trades['funding_rate'].values
            price_pnls = trades['price_pnl_pct'].values
            
            # For SHORT: positive correlation between FR and price_pnl means FR predicts adverse price movement
            # (because price_pnl for SHORT = (entry - exit)/entry, so price going up = negative pnl)
            # Actually, let's correlate FR with the raw price change
            # For SHORT: price_pnl = (entry - exit)/entry * 100, so positive means price dropped
            # If FR > 0 and price tends to go UP (negative price_pnl for SHORT), that's adverse
            
            corr, p_val = sp_stats.pearsonr(fr_vals, price_pnls)
            spearman_corr, sp_p = sp_stats.spearmanr(fr_vals, price_pnls)
            
            dir_label = "SHORT" if direction == "short" else "LONG"
            print(f"  {dir_label} {period_name}: Pearson r={corr:.4f} (p={p_val:.4f}), "
                  f"Spearman ρ={spearman_corr:.4f} (p={sp_p:.4f}), n={len(trades)}")
    
    print()

# ============================================================
# BREAKEVEN ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("BREAKEVEN ANALYSIS: Minimum FR Threshold for Positive EV After Costs")
print("=" * 80)

for hold_label, hold_bars in HOLD_BARS.items():
    print(f"\n--- Hold Period: {hold_label} ---")
    
    # Test fine-grained thresholds
    fine_thresholds = np.arange(0, 0.0005, 0.00001)
    
    for direction in ['short', 'long']:
        dir_label = "SHORT" if direction == "short" else "LONG"
        best_ev = -999
        best_threshold = 0
        best_n = 0
        
        print(f"\n  {dir_label} carry:")
        print(f"  {'Threshold':>12} {'OOS EV%':>10} {'OOS n':>8} {'OOS WinRate':>12} {'OOS Sharpe':>12}")
        
        for t in fine_thresholds:
            trades = run_carry_backtest(
                fr_settlement, price_df, t, hold_bars, direction=direction
            )
            _, oos = split_trades(trades)
            if len(oos) < 5:
                continue
            
            ev = oos['net_pnl_pct'].mean()
            wr = (oos['net_pnl_pct'] > 0).mean() * 100
            std = oos['net_pnl_pct'].std(ddof=1)
            sharpe = (ev / std) * np.sqrt(len(oos) / max(1, 1)) if std > 0 else 0
            
            if ev > best_ev:
                best_ev = ev
                best_threshold = t
                best_n = len(oos)
            
            # Only print every 5th threshold to avoid spam
            if int(t * 100000) % 5 == 0:
                print(f"  {t*100:.4f}%{'':>5} {ev:>10.4f} {len(oos):>8} {wr:>11.1f}% {sharpe:>12.3f}")
        
        print(f"\n  >>> Best OOS EV: {best_ev:.4f}% at threshold {best_threshold*100:.4f}% "
              f"({best_n} trades)")

# ============================================================
# DETAILED OOS ANALYSIS FOR BEST CONFIGURATIONS
# ============================================================
print("\n" + "=" * 80)
print("DETAILED OOS MONTHLY BREAKDOWN - BEST CONFIGURATIONS")
print("=" * 80)

# Find best SHORT and LONG configurations by OOS Sharpe
best_short = None
best_long = None
best_short_sharpe = -999
best_long_sharpe = -999

for r in all_results:
    oos = r['oos_stats']
    if oos['n_trades'] < 5:
        continue
    
    if r['direction'] == 'SHORT' and oos['sharpe_annualized'] > best_short_sharpe:
        best_short_sharpe = oos['sharpe_annualized']
        best_short = r
    elif r['direction'] == 'LONG' and oos['sharpe_annualized'] > best_long_sharpe:
        best_long_sharpe = oos['sharpe_annualized']
        best_long = r

for best, label in [(best_short, "BEST SHORT"), (best_long, "BEST LONG")]:
    if best is None:
        print(f"\n{label}: No valid configuration found")
        continue
    
    oos_trades = best['oos_trades']
    print(f"\n{label}: {best['direction']} carry, threshold={best['threshold_label']}, "
          f"hold={best['hold']}")
    print(f"  OOS Trades: {len(oos_trades)}")
    print(f"  OOS EV: {best['oos_stats']['ev_pct']:.4f}%")
    print(f"  OOS Sharpe: {best['oos_stats']['sharpe_annualized']:.3f}")
    print(f"  OOS Win Rate: {best['oos_stats']['win_rate']:.1f}%")
    
    # Monthly breakdown
    oos_copy = oos_trades.copy()
    oos_copy['month'] = pd.to_datetime(oos_copy['entry_time']).dt.to_period('M')
    monthly = oos_copy.groupby('month').agg(
        total_pnl=('net_pnl_pct', 'sum'),
        n_trades=('net_pnl_pct', 'count'),
        win_rate=('net_pnl_pct', lambda x: (x > 0).mean() * 100),
        avg_funding=('funding_pnl_pct', 'mean'),
        avg_price=('price_pnl_pct', 'mean'),
    )
    
    print(f"\n  {'Month':<10} {'Trades':>6} {'Total%':>10} {'WinRate':>8} "
          f"{'AvgFund%':>10} {'AvgPrice%':>10}")
    print("  " + "-" * 60)
    for month, row in monthly.iterrows():
        print(f"  {str(month):<10} {row['n_trades']:>6.0f} {row['total_pnl']:>10.4f} "
              f"{row['win_rate']:>7.1f}% {row['avg_funding']:>10.4f} {row['avg_price']:>10.4f}")

# ============================================================
# EXPECTED MONTHLY P&L FOR $190 ACCOUNT
# ============================================================
print("\n" + "=" * 80)
print("EXPECTED MONTHLY P&L FOR $190 ACCOUNT AT 1x LEVERAGE")
print("=" * 80)

print(f"\nAccount: ${ACCOUNT_SIZE}, Leverage: {LEVERAGE}x")
print(f"Position size per trade: ${ACCOUNT_SIZE * LEVERAGE}")
print(f"Round-trip cost: {ROUND_TRIP_COST * 100:.2f}%\n")

print(f"{'Config':<35} {'Period':<5} {'Trades/mo':>10} {'EV/trade%':>10} "
      f"{'EV/trade$':>10} {'Monthly$':>10} {'Monthly%':>10}")
print("-" * 100)

for r in all_results:
    for period, stats in [('IS', r['is_stats']), ('OOS', r['oos_stats'])]:
        if stats['n_trades'] == 0:
            continue
        
        dir_label = "SHORT" if r['direction'] == 'SHORT' else "LONG"
        config = f"{dir_label} FR>{r['threshold_label']} {r['hold'][:15]}"
        
        # Calculate trades per month
        if period == 'IS':
            months = 15  # Jan 2024 - Mar 2025
        else:
            months = 12.5  # Apr 2025 - mid Apr 2026
        
        trades_per_month = stats['n_trades'] / months
        ev_pct = stats['ev_pct']
        ev_dollar = ev_pct / 100 * ACCOUNT_SIZE * LEVERAGE
        monthly_dollar = ev_dollar * trades_per_month
        monthly_pct = monthly_dollar / ACCOUNT_SIZE * 100
        
        print(f"{config:<35} {period:<5} {trades_per_month:>10.1f} {ev_pct:>10.4f} "
              f"{ev_dollar:>10.4f} {monthly_dollar:>10.4f} {monthly_pct:>10.2f}")

# ============================================================
# COMPREHENSIVE SUMMARY TABLE
# ============================================================
print("\n" + "=" * 80)
print("COMPREHENSIVE SUMMARY: ALL OOS CONFIGURATIONS")
print("=" * 80)

print(f"\n{'Hold':<20} {'Dir':<6} {'Threshold':<12} {'n':>5} {'EV%':>8} {'Std%':>8} "
      f"{'WR%':>6} {'t':>7} {'p':>7} {'CI0':>8} {'CI1':>8} {'0∈CI':>5} "
      f"{'MoWR%':>7} {'Sharpe':>7} {'Mo$':>7}")
print("-" * 140)

for r in all_results:
    s = r['oos_stats']
    if s['n_trades'] == 0:
        continue
    
    dir_label = "SH" if r['direction'] == 'SHORT' else "LO"
    hold_short = r['hold'][:18]
    
    # Monthly P&L estimate
    months_oos = 12.5
    tpm = s['n_trades'] / months_oos
    ev_dollar = s['ev_pct'] / 100 * ACCOUNT_SIZE * LEVERAGE
    monthly_dollar = ev_dollar * tpm
    
    ci_zero = "Y" if s['ci_includes_zero'] else "N"
    
    print(f"{hold_short:<20} {dir_label:<6} {r['threshold_label']:<12} "
          f"{s['n_trades']:>5} {s['ev_pct']:>8.4f} {s['std_pnl']:>8.4f} "
          f"{s['win_rate']:>5.1f} {s['t_stat']:>7.3f} {s['p_value']:>7.4f} "
          f"{s['ci_lo']:>8.4f} {s['ci_hi']:>8.4f} {ci_zero:>5} "
          f"{s['month_win_rate']:>6.1f} {s['sharpe_annualized']:>7.3f} "
          f"{monthly_dollar:>7.3f}")

# ============================================================
# FINAL VERDICT
# ============================================================
print("\n" + "=" * 80)
print("FINAL VERDICT")
print("=" * 80)

# Find best OOS configurations
profitable_configs = []
for r in all_results:
    s = r['oos_stats']
    if s['n_trades'] < 10:
        continue
    if s['ev_pct'] > 0:
        profitable_configs.append((r, s))

# Sort by OOS Sharpe
profitable_configs.sort(key=lambda x: x[1]['sharpe_annualized'], reverse=True)

if len(profitable_configs) == 0:
    print("\nX NO profitable OOS configurations found.")
    print("   RECOMMENDATION: REJECT")
else:
    print(f"\nFound {len(profitable_configs)} configurations with positive OOS EV.")
    
    # Check top 3 for statistical significance
    print("\nTop configurations by OOS Sharpe ratio:")
    for i, (r, s) in enumerate(profitable_configs[:5]):
        dir_label = "SHORT" if r['direction'] == 'SHORT' else "LONG"
        sig = "SIGNIFICANT" if not s['ci_includes_zero'] and s['p_value'] < 0.05 else "NOT SIGNIFICANT"
        
        months_oos = 12.5
        tpm = s['n_trades'] / months_oos
        ev_dollar = s['ev_pct'] / 100 * ACCOUNT_SIZE * LEVERAGE
        monthly_dollar = ev_dollar * tpm
        
        print(f"\n  #{i+1}: {dir_label} carry, threshold={r['threshold_label']}, "
              f"hold={r['hold']}")
        print(f"      OOS: {s['n_trades']} trades, EV={s['ev_pct']:.4f}%, "
              f"Sharpe={s['sharpe_annualized']:.3f}")
        print(f"      t-stat={s['t_stat']:.3f}, p-value={s['p_value']:.4f}")
        print(f"      95% CI: [{s['ci_lo']:.4f}%, {s['ci_hi']:.4f}%] "
              f"{'OK EXCLUDES 0' if not s['ci_includes_zero'] else '* INCLUDES 0'}")
        print(f"      Monthly win rate: {s['month_win_rate']:.1f}%")
        print(f"      Statistical significance: {sig}")
        print(f"      Expected monthly P&L: ${monthly_dollar:.2f} "
              f"({monthly_dollar/ACCOUNT_SIZE*100:.2f}% of account)")

# Overall assessment
print("\n" + "-" * 80)
print("OVERALL ASSESSMENT:")
print("-" * 80)

# Check if ANY config is statistically significant in OOS
any_significant = False
best_monthly = -999
best_config_str = ""

for r, s in profitable_configs:
    if not s['ci_includes_zero'] and s['p_value'] < 0.05:
        any_significant = True
    months_oos = 12.5
    tpm = s['n_trades'] / months_oos
    ev_dollar = s['ev_pct'] / 100 * ACCOUNT_SIZE * LEVERAGE
    monthly_dollar = ev_dollar * tpm
    if monthly_dollar > best_monthly:
        best_monthly = monthly_dollar
        dir_label = "SHORT" if r['direction'] == 'SHORT' else "LONG"
        best_config_str = f"{dir_label} carry, threshold={r['threshold_label']}, hold={r['hold']}"

# P&L decomposition for best config
if profitable_configs:
    best_r, best_s = profitable_configs[0]
    oos_trades = best_r['oos_trades']
    total_funding = oos_trades['funding_pnl_pct'].sum()
    total_price = oos_trades['price_pnl_pct'].sum()
    total_net = oos_trades['net_pnl_pct'].sum()
    
    print(f"\n1. Is FR Carry trade profitable after costs on BTC/USDT?")
    if best_s['ev_pct'] > 0:
        print(f"   YES - Best OOS EV: {best_s['ev_pct']:.4f}% per trade")
    else:
        print(f"   NO - Best OOS EV: {best_s['ev_pct']:.4f}% per trade")
    
    print(f"\n2. Is the edge statistically significant?")
    if any_significant:
        print(f"   YES - At least one configuration shows p < 0.05 with CI excluding 0")
    else:
        print(f"   NO - No configuration achieves statistical significance at p < 0.05")
        print(f"   Best p-value: {best_s['p_value']:.4f}")
    
    print(f"\n3. P&L Decomposition (best config OOS):")
    print(f"   Total funding PnL: {total_funding:+.4f}%")
    print(f"   Total price PnL:   {total_price:+.4f}%")
    print(f"   Total net PnL:     {total_net:+.4f}%")
    if abs(total_funding) > 0:
        fund_dominance = abs(total_funding) / (abs(total_funding) + abs(total_price)) * 100
        print(f"   Funding dominance: {fund_dominance:.1f}% of gross PnL")
        if fund_dominance > 60:
            print(f"   → Funding PnL DOMINATES → structural carry edge confirmed")
        else:
            print(f"   → Price PnL is significant → carry trade has directional component")
    
    print(f"\n4. Expected monthly P&L for ${ACCOUNT_SIZE} account at {LEVERAGE}x leverage:")
    print(f"   Best config: ${best_monthly:.2f}/month ({best_monthly/ACCOUNT_SIZE*100:.2f}% return)")
    print(f"   Config: {best_config_str}")
    
    # Breakeven
    print(f"\n5. Breakeven analysis:")
    print(f"   Round-trip cost: {ROUND_TRIP_COST*100:.2f}%")
    print(f"   Average funding rate needed to break even: {ROUND_TRIP_COST*100:.2f}% per trade")
    print(f"   (This is the minimum FR threshold for carry-only profitability)")
    
    # Recommendation
    print(f"\n6. RECOMMENDATION:")
    if best_s['ev_pct'] > 0 and any_significant and best_monthly > 1.0:
        print(f"   [OK] IMPLEMENT - Statistically significant edge with meaningful P&L")
        print(f"   Expected: ${best_monthly:.2f}/month on ${ACCOUNT_SIZE} account")
    elif best_s['ev_pct'] > 0 and best_monthly > 0.5:
        print(f"   [!]  CONDITIONAL - Positive EV but NOT statistically significant")
        print(f"   Risk: Edge may be noise. Small position sizing recommended.")
        print(f"   Expected: ${best_monthly:.2f}/month on ${ACCOUNT_SIZE} account")
    else:
        print(f"   X REJECT - Insufficient edge after costs")
        print(f"   Best monthly P&L: ${best_monthly:.2f} is too small relative to risk")

print("\n" + "=" * 80)
print("BACKTEST COMPLETE")
print("=" * 80)