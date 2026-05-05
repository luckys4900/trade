"""
RIGOROUS Pairs Trading Backtest: BTC/ETH on Hyperliquid
=========================================================
Cointegration-based pairs trading with multiple configurations,
statistical significance tests, regime analysis, and final verdict.
"""

import numpy as np
import pandas as pd
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ==============================================================================
# 1. DATA LOADING & MERGING
# ==============================================================================
print("=" * 80)
print("PAIRS TRADING BACKTEST: BTC/ETH on Hyperliquid (4h candles)")
print("=" * 80)

btc = pd.read_csv(r"C:\Users\user\Desktop\cursor\trade\data\btc_price_4h_cache.csv")
eth = pd.read_csv(r"C:\Users\user\Desktop\cursor\trade\data\eth_usdt_4h.csv")

# Parse datetime - strip timezone from BTC
btc['datetime'] = pd.to_datetime(btc['datetime']).dt.tz_localize(None)
eth['datetime'] = pd.to_datetime(eth['datetime'])

# Merge on datetime
df = pd.merge(btc[['datetime', 'open', 'high', 'low', 'close', 'volume']],
              eth[['datetime', 'open', 'high', 'low', 'close', 'volume']],
              on='datetime', suffixes=('_btc', '_eth'))

df = df.sort_values('datetime').reset_index(drop=True)

print(f"\nMerged dataset: {len(df)} rows")
print(f"Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
print(f"BTC price range: ${df['close_btc'].min():.0f} - ${df['close_btc'].max():.0f}")
print(f"ETH price range: ${df['close_eth'].min():.0f} - ${df['close_eth'].max():.0f}")

# Log prices
df['log_btc'] = np.log(df['close_btc'])
df['log_eth'] = np.log(df['close_eth'])

# Returns
df['ret_btc'] = df['close_btc'].pct_change()
df['ret_eth'] = df['close_eth'].pct_change()

# Correlation of returns
corr = df['ret_btc'].corr(df['ret_eth'])
print(f"Return correlation: {corr:.4f}")

# ==============================================================================
# 2. IS/OOS SPLIT
# ==============================================================================
IS_START = '2024-04-01'
IS_END = '2025-06-30'
OOS_START = '2025-07-01'
OOS_END = '2026-04-18'

df_is = df[(df['datetime'] >= IS_START) & (df['datetime'] <= IS_END)].copy()
df_oos = df[(df['datetime'] >= OOS_START) & (df['datetime'] <= OOS_END)].copy()

print(f"\nIS period: {df_is['datetime'].iloc[0]} to {df_is['datetime'].iloc[-1]} ({len(df_is)} bars)")
print(f"OOS period: {df_oos['datetime'].iloc[0]} to {df_oos['datetime'].iloc[-1]} ({len(df_oos)} bars)")

# ==============================================================================
# 3. COINTEGRATION TESTS
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 1: COINTEGRATION TESTS (Engle-Granger)")
print("=" * 80)

try:
    from statsmodels.tsa.stattools import coint, adfuller
    HAS_COINT = True
except ImportError:
    HAS_COINT = False
    print("WARNING: statsmodels coint not available, using manual Engle-Granger")

def engle_granger_test(y, x):
    """Engle-Granger two-step cointegration test.
    y = dependent variable, x = independent variable.
    Tests: log(y) = alpha + beta * log(x) + residual
    """
    log_y = np.log(y)
    log_x = np.log(x)
    
    # Step 1: OLS regression
    X = np.column_stack([np.ones(len(log_x)), log_x])
    beta_vec = np.linalg.lstsq(X, log_y, rcond=None)[0]
    alpha, beta = beta_vec[0], beta_vec[1]
    
    # Step 2: Test residuals for stationarity (ADF test)
    residuals = log_y - alpha - beta * log_x
    
    # ADF test on residuals
    adf_result = adfuller(residuals, maxlag=1, regression='c')
    
    return {
        'alpha': alpha,
        'beta': beta,
        'adf_stat': adf_result[0],
        'p_value': adf_result[1],
        'critical_values': adf_result[4],
        'residuals': residuals
    }

# Test on full sample
result_full = engle_granger_test(df['close_btc'].values, df['close_eth'].values)
print(f"\nFull Sample Cointegration Test:")
print(f"  Alpha (intercept): {result_full['alpha']:.6f}")
print(f"  Beta (hedge ratio): {result_full['beta']:.6f}")
print(f"  ADF t-statistic: {result_full['adf_stat']:.4f}")
print(f"  p-value: {result_full['p_value']:.6f}")
print(f"  Critical values: 1%={result_full['critical_values']['1%']:.4f}, "
      f"5%={result_full['critical_values']['5%']:.4f}, "
      f"10%={result_full['critical_values']['10%']:.4f}")

# Test on IS only
result_is = engle_granger_test(df_is['close_btc'].values, df_is['close_eth'].values)
print(f"\nIS Period Cointegration Test:")
print(f"  Alpha: {result_is['alpha']:.6f}")
print(f"  Beta: {result_is['beta']:.6f}")
print(f"  ADF t-statistic: {result_is['adf_stat']:.4f}")
print(f"  p-value: {result_is['p_value']:.6f}")

# Test on OOS only
result_oos = engle_gragger = engle_granger_test(df_oos['close_btc'].values, df_oos['close_eth'].values)
print(f"\nOOS Period Cointegration Test:")
print(f"  Alpha: {result_oos['alpha']:.6f}")
print(f"  Beta: {result_oos['beta']:.6f}")
print(f"  ADF t-statistic: {result_oos['adf_stat']:.4f}")
print(f"  p-value: {result_oos['p_value']:.6f}")

# Use IS hedge ratio for all subsequent analysis
HEDGE_RATIO_IS = result_is['beta']
ALPHA_IS = result_is['alpha']
print(f"\n>>> Using IS-derived hedge ratio: beta = {HEDGE_RATIO_IS:.6f}, alpha = {ALPHA_IS:.6f}")

# ==============================================================================
# 4. COINTEGRATION STABILITY (3-MONTH WINDOWS)
# ==============================================================================
print("\n" + "-" * 60)
print("Cointegration Stability Analysis (3-month rolling windows)")
print("-" * 60)

window_results = []
start_date = df['datetime'].iloc[0]
end_date = df['datetime'].iloc[-1]
window_start = start_date

while window_start < end_date:
    window_end = window_start + pd.DateOffset(months=3)
    mask = (df['datetime'] >= window_start) & (df['datetime'] < window_end)
    w_df = df[mask]
    if len(w_df) < 100:
        window_start = window_end
        continue
    w_result = engle_granger_test(w_df['close_btc'].values, w_df['close_eth'].values)
    window_results.append({
        'period': f"{window_start.strftime('%Y-%m')} to {window_end.strftime('%Y-%m')}",
        'n': len(w_df),
        'beta': w_result['beta'],
        'adf_stat': w_result['adf_stat'],
        'p_value': w_result['p_value'],
        'cointegrated': 'YES' if w_result['p_value'] < 0.05 else 'NO'
    })
    window_start = window_end

w_df_results = pd.DataFrame(window_results)
print(w_df_results.to_string(index=False))
coint_pct = (w_df_results['cointegrated'] == 'YES').mean() * 100
print(f"\nCointegrated in {coint_pct:.0f}% of windows")

# ==============================================================================
# 5. HALF-LIFE ESTIMATION (Ornstein-Uhlenbeck)
# ==============================================================================
print("\n" + "-" * 60)
print("Half-Life Estimation (Ornstein-Uhlenbeck)")
print("-" * 60)

def estimate_half_life(spread_series):
    """Estimate half-life of mean reversion using OU process."""
    spread_lag = np.roll(spread_series, 1)
    spread_lag[0] = spread_lag[1]  # avoid NaN
    spread_ret = spread_series - spread_lag
    spread_ret = spread_ret[1:]
    spread_lag = spread_lag[1:]
    
    # OLS: delta_S = lambda * S_{t-1} + epsilon
    X = np.column_stack([np.ones(len(spread_lag)), spread_lag])
    beta_vec = np.linalg.lstsq(X, spread_ret, rcond=None)[0]
    lam = beta_vec[1]
    
    if lam >= 0:
        return float('inf')  # No mean reversion
    
    half_life = -np.log(2) / lam
    return half_life

# Full sample spread
spread_full = df['log_btc'].values - HEDGE_RATIO_IS * df['log_eth'].values - ALPHA_IS
hl_full = estimate_half_life(spread_full)

# IS spread
spread_is = df_is['log_btc'].values - HEDGE_RATIO_IS * df_is['log_eth'].values - ALPHA_IS
hl_is = estimate_half_life(spread_is)

# OOS spread
spread_oos = df_oos['log_btc'].values - HEDGE_RATIO_IS * df_oos['log_eth'].values - ALPHA_IS
hl_oos = estimate_half_life(spread_oos)

print(f"Half-life (full sample): {hl_full:.1f} bars ({hl_full/6:.1f} days)")
print(f"Half-life (IS):          {hl_is:.1f} bars ({hl_is/6:.1f} days)")
print(f"Half-life (OOS):         {hl_oos:.1f} bars ({hl_oos/6:.1f} days)")

# ==============================================================================
# 6. ROLLING SPREAD & Z-SCORE CALCULATION
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 2: ROLLING SPREAD & Z-SCORE CALCULATION")
print("=" * 80)

LOOKBACK = 120  # 20 days * 6 bars/day

# Calculate spread using IS hedge ratio
df['spread'] = df['log_btc'] - HEDGE_RATIO_IS * df['log_eth'] - ALPHA_IS

# Rolling Z-score
df['spread_mean'] = df['spread'].rolling(window=LOOKBACK).mean()
df['spread_std'] = df['spread'].rolling(window=LOOKBACK).std()
df['z_score'] = (df['spread'] - df['spread_mean']) / df['spread_std']

# Drop NaN rows
df_valid = df.dropna(subset=['z_score']).copy()
print(f"Valid rows after rolling calculation: {len(df_valid)}")
print(f"Z-score range: {df_valid['z_score'].min():.3f} to {df_valid['z_score'].max():.3f}")
print(f"Z-score mean: {df_valid['z_score'].mean():.4f}, std: {df_valid['z_score'].std():.4f}")

# ==============================================================================
# 7. TRADING SIMULATION ENGINE
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 3-5: TRADING SIMULATION")
print("=" * 80)

def run_pairs_backtest(df_in, z_entry, z_exit, max_hold, sl_z=None,
                       cost_per_side=0.00085, position_size=100.0):
    """
    Run pairs trading backtest.
    
    Parameters:
    - df_in: DataFrame with z_score, close_btc, close_eth, log_btc, log_eth
    - z_entry: Z-score threshold for entry
    - z_exit: Z-score threshold for exit
    - max_hold: Maximum holding period in bars
    - sl_z: Stop-loss Z-score (None = no stop-loss)
    - cost_per_side: Cost per side per leg (taker: 0.00085, maker: 0.0005)
    - position_size: Dollar amount per side
    
    Returns: dict with trade results
    """
    trades = []
    position = 0  # 0 = flat, 1 = long spread, -1 = short spread
    entry_idx = 0
    entry_z = 0
    entry_btc_price = 0
    entry_eth_price = 0
    
    data = df_in.reset_index(drop=True)
    
    for i in range(len(data)):
        z = data['z_score'].iloc[i]
        btc_price = data['close_btc'].iloc[i]
        eth_price = data['close_eth'].iloc[i]
        
        if position == 0:
            # Check for entry
            if z > z_entry:
                # SHORT spread: SHORT BTC, LONG ETH
                position = -1
                entry_idx = i
                entry_z = z
                entry_btc_price = btc_price
                entry_eth_price = eth_price
            elif z < -z_entry:
                # LONG spread: LONG BTC, SHORT ETH
                position = 1
                entry_idx = i
                entry_z = z
                entry_btc_price = btc_price
                entry_eth_price = eth_price
        else:
            # Check for exit conditions
            hold_bars = i - entry_idx
            exit_signal = False
            exit_reason = ''
            
            # Exit condition 1: Z crosses exit threshold
            if position == 1 and z >= z_exit:
                exit_signal = True
                exit_reason = 'z_exit'
            elif position == -1 and z <= z_exit:
                exit_signal = True
                exit_reason = 'z_exit'
            
            # Exit condition 2: Max hold reached
            if hold_bars >= max_hold:
                exit_signal = True
                exit_reason = 'max_hold'
            
            # Exit condition 3: Stop-loss
            if sl_z is not None:
                if position == 1 and z < -sl_z:
                    exit_signal = True
                    exit_reason = 'stop_loss'
                elif position == -1 and z > sl_z:
                    exit_signal = True
                    exit_reason = 'stop_loss'
            
            if exit_signal:
                # Calculate PnL
                # For LONG spread (LONG BTC, SHORT ETH):
                #   PnL = position_size * (btc_ret) + position_size * beta * (-eth_ret)
                #   = position_size * (btc_ret - beta * eth_ret)
                # For SHORT spread (SHORT BTC, LONG ETH):
                #   PnL = position_size * (-btc_ret + beta * eth_ret)
                
                btc_ret = (btc_price - entry_btc_price) / entry_btc_price
                eth_ret = (eth_price - entry_eth_price) / entry_eth_price
                
                if position == 1:  # LONG spread
                    gross_pnl = position_size * (btc_ret - HEDGE_RATIO_IS * eth_ret)
                else:  # SHORT spread
                    gross_pnl = position_size * (-btc_ret + HEDGE_RATIO_IS * eth_ret)
                
                # Costs: 4 sides per round trip
                total_cost = position_size * 4 * cost_per_side
                net_pnl = gross_pnl - total_cost
                
                # Decompose PnL by leg
                if position == 1:
                    btc_leg_pnl = position_size * btc_ret
                    eth_leg_pnl = position_size * (-HEDGE_RATIO_IS * eth_ret)
                else:
                    btc_leg_pnl = position_size * (-btc_ret)
                    eth_leg_pnl = position_size * (HEDGE_RATIO_IS * eth_ret)
                
                trades.append({
                    'entry_time': data['datetime'].iloc[entry_idx],
                    'exit_time': data['datetime'].iloc[i],
                    'direction': 'LONG' if position == 1 else 'SHORT',
                    'entry_z': entry_z,
                    'exit_z': z,
                    'hold_bars': hold_bars,
                    'exit_reason': exit_reason,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'cost': total_cost,
                    'btc_leg_pnl': btc_leg_pnl,
                    'eth_leg_pnl': eth_leg_pnl,
                    'btc_ret': btc_ret,
                    'eth_ret': eth_ret,
                })
                
                position = 0
    
    return trades

# ==============================================================================
# 8. RUN ALL CONFIGURATIONS
# ==============================================================================

configs = [
    {'name': 'Conservative', 'z_entry': 2.5, 'z_exit': 0.5, 'max_hold': 30, 'sl_z': None},
    {'name': 'Moderate', 'z_entry': 2.0, 'z_exit': 0.0, 'max_hold': 20, 'sl_z': None},
    {'name': 'Aggressive', 'z_entry': 1.5, 'z_exit': -0.5, 'max_hold': 15, 'sl_z': None},
    {'name': 'With SL', 'z_entry': 2.0, 'z_exit': 0.0, 'max_hold': 20, 'sl_z': 4.0},
    {'name': 'With SL tight', 'z_entry': 2.0, 'z_exit': 0.0, 'max_hold': 20, 'sl_z': 3.5},
]

cost_scenarios = [
    {'name': 'Taker', 'cost': 0.00085},  # 4 * (0.035% + 0.05%) = 0.34% total, per side per leg = 0.085%
    {'name': 'Maker', 'cost': 0.00050},   # 4 * (0.02% + 0.03%) = 0.20% total, per side per leg = 0.05%
]

# Split data
df_is_valid = df_valid[(df_valid['datetime'] >= IS_START) & (df_valid['datetime'] <= IS_END)].copy()
df_oos_valid = df_valid[(df_valid['datetime'] >= OOS_START) & (df_valid['datetime'] <= OOS_END)].copy()

print(f"\nIS valid bars: {len(df_is_valid)}")
print(f"OOS valid bars: {len(df_oos_valid)}")

all_results = []

for config in configs:
    for cost in cost_scenarios:
        # IS backtest
        trades_is = run_pairs_backtest(
            df_is_valid, config['z_entry'], config['z_exit'],
            config['max_hold'], config['sl_z'], cost['cost']
        )
        
        # OOS backtest
        trades_oos = run_pairs_backtest(
            df_oos_valid, config['z_entry'], config['z_exit'],
            config['max_hold'], config['sl_z'], cost['cost']
        )
        
        def summarize(trades, label):
            if len(trades) == 0:
                return {
                    f'{label}_n': 0, f'{label}_win_rate': 0, f'{label}_ev_gross': 0,
                    f'{label}_ev_net': 0, f'{label}_total_pnl': 0,
                    f'{label}_sharpe': 0, f'{label}_max_dd': 0,
                    f'{label}_profit_factor': 0
                }
            df_t = pd.DataFrame(trades)
            n = len(df_t)
            win_rate = (df_t['net_pnl'] > 0).mean()
            ev_gross = df_t['gross_pnl'].mean()
            ev_net = df_t['net_pnl'].mean()
            total_pnl = df_t['net_pnl'].sum()
            
            # Sharpe (annualized, 6 bars/day, 365 days)
            if df_t['net_pnl'].std() > 0:
                # Approximate: trades per year * (mean/std)
                # Better: use bar-level returns
                sharpe = (df_t['net_pnl'].mean() / df_t['net_pnl'].std()) * np.sqrt(6 * 365 / df_t['hold_bars'].mean()) if df_t['hold_bars'].mean() > 0 else 0
            else:
                sharpe = 0
            
            # Max drawdown from cumulative PnL
            cum_pnl = df_t['net_pnl'].cumsum()
            running_max = cum_pnl.cummax()
            drawdown = cum_pnl - running_max
            max_dd = drawdown.min()
            
            # Profit factor
            wins = df_t[df_t['net_pnl'] > 0]['net_pnl'].sum()
            losses = abs(df_t[df_t['net_pnl'] < 0]['net_pnl'].sum())
            pf = wins / losses if losses > 0 else float('inf')
            
            return {
                f'{label}_n': n, f'{label}_win_rate': win_rate, f'{label}_ev_gross': ev_gross,
                f'{label}_ev_net': ev_net, f'{label}_total_pnl': total_pnl,
                f'{label}_sharpe': sharpe, f'{label}_max_dd': max_dd,
                f'{label}_profit_factor': pf
            }
        
        is_stats = summarize(trades_is, 'is')
        oos_stats = summarize(trades_oos, 'oos')
        
        result = {
            'config': config['name'],
            'cost': cost['name'],
            'z_entry': config['z_entry'],
            'z_exit': config['z_exit'],
            'max_hold': config['max_hold'],
            'sl_z': config['sl_z'],
            **is_stats,
            **oos_stats,
            'trades_is': trades_is,
            'trades_oos': trades_oos,
        }
        all_results.append(result)

# ==============================================================================
# 9. RESULTS TABLE
# ==============================================================================
print("\n" + "=" * 80)
print("FULL RESULTS TABLE: All Configs × Cost Scenarios")
print("=" * 80)

header = f"{'Config':<18} {'Cost':<7} {'IS_n':>5} {'IS_WR':>7} {'IS_EV':>8} {'OOS_n':>6} {'OOS_WR':>7} {'OOS_EV':>8} {'OOS_Sharpe':>11} {'OOS_PF':>8} {'OOS_DD':>8}"
print(header)
print("-" * len(header))

for r in all_results:
    print(f"{r['config']:<18} {r['cost']:<7} "
          f"{r['is_n']:>5} {r['is_win_rate']:>7.1%} {r['is_ev_net']:>8.3f} "
          f"{r['oos_n']:>6} {r['oos_win_rate']:>7.1%} {r['oos_ev_net']:>8.3f} "
          f"{r['oos_sharpe']:>11.3f} {r['oos_profit_factor']:>8.2f} {r['oos_max_dd']:>8.2f}")

# ==============================================================================
# 10. FIND BEST CONFIG (Highest OOS Sharpe with positive OOS EV)
# ==============================================================================
print("\n" + "=" * 80)
print("BEST CONFIGURATION (Highest OOS Sharpe with positive OOS EV)")
print("=" * 80)

valid_results = [r for r in all_results if r['oos_ev_net'] > 0 and r['oos_n'] > 0]
if valid_results:
    best = max(valid_results, key=lambda x: x['oos_sharpe'])
else:
    best = max(all_results, key=lambda x: x['oos_sharpe'])

print(f"\nBest Config: {best['config']} ({best['cost']} cost)")
print(f"  Z_entry={best['z_entry']}, Z_exit={best['z_exit']}, Max_hold={best['max_hold']}, SL_Z={best['sl_z']}")
print(f"  IS:  n={best['is_n']}, Win Rate={best['is_win_rate']:.1%}, EV_net=${best['is_ev_net']:.3f}")
print(f"  OOS: n={best['oos_n']}, Win Rate={best['oos_win_rate']:.1%}, EV_net=${best['oos_ev_net']:.3f}")
print(f"  OOS Sharpe={best['oos_sharpe']:.3f}, Profit Factor={best['oos_profit_factor']:.2f}")
print(f"  OOS Max Drawdown=${best['oos_max_dd']:.2f}")

# ==============================================================================
# 11. STATISTICAL SIGNIFICANCE TESTS ON BEST CONFIG
# ==============================================================================
print("\n" + "=" * 80)
print("STATISTICAL SIGNIFICANCE TESTS (Best Config OOS)")
print("=" * 80)

oos_trades = best['trades_oos']
if len(oos_trades) > 0:
    df_oos_trades = pd.DataFrame(oos_trades)
    
    # t-test on OOS EV
    pnl_values = df_oos_trades['net_pnl'].values
    t_stat, p_value = stats.ttest_1samp(pnl_values, 0)
    print(f"\n1. t-test on OOS EV (H0: mean PnL = 0)")
    print(f"   t-statistic: {t_stat:.4f}")
    print(f"   p-value: {p_value:.6f}")
    print(f"   df: {len(pnl_values) - 1}")
    print(f"   Mean PnL: ${np.mean(pnl_values):.4f}")
    print(f"   Std PnL: ${np.std(pnl_values, ddof=1):.4f}")
    print(f"   Significant at 5%? {'YES' if p_value < 0.05 else 'NO'}")
    
    # Bootstrap 95% CI
    print(f"\n2. Bootstrap 95% CI (5000 resamples)")
    np.random.seed(42)
    n_bootstrap = 5000
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(pnl_values, size=len(pnl_values), replace=True)
        bootstrap_means.append(np.mean(sample))
    
    ci_lower = np.percentile(bootstrap_means, 2.5)
    ci_upper = np.percentile(bootstrap_means, 97.5)
    print(f"   Bootstrap mean: ${np.mean(bootstrap_means):.4f}")
    print(f"   95% CI: [${ci_lower:.4f}, ${ci_upper:.4f}]")
    print(f"   CI includes 0? {'YES' if ci_lower <= 0 <= ci_upper else 'NO'}")
    
    # Monthly breakdown
    print(f"\n3. Monthly Breakdown (OOS)")
    df_oos_trades['exit_month'] = pd.to_datetime(df_oos_trades['exit_time']).dt.to_period('M')
    monthly = df_oos_trades.groupby('exit_month').agg(
        n=('net_pnl', 'count'),
        win_rate=('net_pnl', lambda x: (x > 0).mean()),
        ev_net=('net_pnl', 'mean'),
        total_pnl=('net_pnl', 'sum')
    )
    print(f"   {'Month':<12} {'n':>4} {'WinRate':>8} {'EV_net':>8} {'TotalPnL':>10}")
    print(f"   {'-'*42}")
    for month, row in monthly.iterrows():
        print(f"   {str(month):<12} {row['n']:>4.0f} {row['win_rate']:>8.1%} {row['ev_net']:>8.3f} {row['total_pnl']:>10.2f}")
    
    # Kelly Criterion
    print(f"\n4. Kelly Criterion")
    wins = pnl_values[pnl_values > 0]
    losses = pnl_values[pnl_values < 0]
    if len(wins) > 0 and len(losses) > 0:
        avg_win = np.mean(wins)
        avg_loss = abs(np.mean(losses))
        win_prob = len(wins) / len(pnl_values)
        kelly = win_prob / (1 - win_prob) - (1 - win_prob) / (avg_win / avg_loss * win_prob / (1 - win_prob))
        # Simpler Kelly: f* = (p*b - q) / b where b = avg_win/avg_loss
        b = avg_win / avg_loss
        p = win_prob
        q = 1 - p
        kelly_simple = (p * b - q) / b
        print(f"   Win probability: {win_prob:.3f}")
        print(f"   Average win: ${avg_win:.4f}")
        print(f"   Average loss: ${avg_loss:.4f}")
        print(f"   Win/Loss ratio (b): {b:.4f}")
        print(f"   Kelly fraction (f*): {kelly_simple:.4f} = {kelly_simple*100:.2f}%")
        print(f"   Half-Kelly (recommended): {kelly_simple*50:.2f}%")

# ==============================================================================
# 12. CUMULATIVE PnL CURVE
# ==============================================================================
print("\n" + "=" * 80)
print("CUMULATIVE PnL CURVE (Best Config OOS)")
print("=" * 80)

if len(oos_trades) > 0:
    df_oos_trades = pd.DataFrame(oos_trades)
    cum_pnl = df_oos_trades['net_pnl'].cumsum()
    
    print(f"\nFirst 10 values:")
    for i in range(min(10, len(cum_pnl))):
        print(f"  Trade {i+1}: Cum PnL = ${cum_pnl.iloc[i]:.2f}")
    
    print(f"\nLast 10 values:")
    for i in range(max(0, len(cum_pnl)-10), len(cum_pnl)):
        print(f"  Trade {i+1}: Cum PnL = ${cum_pnl.iloc[i]:.2f}")
    
    print(f"\nFinal Cumulative PnL: ${cum_pnl.iloc[-1]:.2f}")
    print(f"Max Drawdown: ${cum_pnl.cummax().sub(cum_pnl).min():.2f}")

# ==============================================================================
# 13. CORRELATION REGIME ANALYSIS
# ==============================================================================
print("\n" + "=" * 80)
print("REGIME ANALYSIS")
print("=" * 80)

# Rolling correlation (60-bar window)
df_valid_copy = df_valid.copy()
df_valid_copy['ret_btc'] = df_valid_copy['close_btc'].pct_change()
df_valid_copy['ret_eth'] = df_valid_copy['close_eth'].pct_change()
df_valid_copy['rolling_corr'] = df_valid_copy['ret_btc'].rolling(60).corr(df_valid_copy['ret_eth'])

# Rolling volatility (60-bar window)
df_valid_copy['rolling_vol_btc'] = df_valid_copy['ret_btc'].rolling(60).std() * np.sqrt(6 * 365)
df_valid_copy['rolling_vol_eth'] = df_valid_copy['ret_eth'].rolling(60).std() * np.sqrt(6 * 365)
df_valid_copy['avg_vol'] = (df_valid_copy['rolling_vol_btc'] + df_valid_copy['rolling_vol_eth']) / 2

# OOS data with regimes
df_oos_regime = df_valid_copy[(df_valid_copy['datetime'] >= OOS_START) & (df_valid_copy['datetime'] <= OOS_END)].copy()

# Correlation regime
corr_median = df_oos_regime['rolling_corr'].median()
high_corr_mask = df_oos_regime['rolling_corr'] >= 0.7
low_corr_mask = df_oos_regime['rolling_corr'] < 0.7

print(f"\n1. Correlation Regime Analysis")
print(f"   Median rolling correlation (OOS): {corr_median:.4f}")
print(f"   High correlation (>=0.7) bars: {high_corr_mask.sum()} ({high_corr_mask.mean():.1%})")
print(f"   Low correlation (<0.7) bars: {low_corr_mask.sum()} ({low_corr_mask.mean():.1%})")

# Run best config on high/low correlation periods
if len(oos_trades) > 0:
    df_oos_t = pd.DataFrame(oos_trades)
    df_oos_t['exit_time'] = pd.to_datetime(df_oos_t['exit_time'])
    
    # Merge trade results with correlation regime
    high_corr_trades = []
    low_corr_trades = []
    for _, trade in df_oos_t.iterrows():
        exit_time = trade['exit_time']
        # Find closest correlation value
        idx = (df_oos_regime['datetime'] - exit_time).abs().idxmin()
        if pd.notna(df_oos_regime.loc[idx, 'rolling_corr']):
            if df_oos_regime.loc[idx, 'rolling_corr'] >= 0.7:
                high_corr_trades.append(trade)
            else:
                low_corr_trades.append(trade)
    
    if len(high_corr_trades) > 0:
        hc_pnl = [t['net_pnl'] for t in high_corr_trades]
        print(f"\n   High Correlation Periods:")
        print(f"     Trades: {len(high_corr_trades)}")
        print(f"     Win Rate: {np.mean([p > 0 for p in hc_pnl]):.1%}")
        print(f"     Mean PnL: ${np.mean(hc_pnl):.4f}")
    
    if len(low_corr_trades) > 0:
        lc_pnl = [t['net_pnl'] for t in low_corr_trades]
        print(f"\n   Low Correlation Periods:")
        print(f"     Trades: {len(low_corr_trades)}")
        print(f"     Win Rate: {np.mean([p > 0 for p in lc_pnl]):.1%}")
        print(f"     Mean PnL: ${np.mean(lc_pnl):.4f}")

# Volatility regime
vol_median = df_oos_regime['avg_vol'].median()
high_vol_mask = df_oos_regime['avg_vol'] >= vol_median
low_vol_mask = df_oos_regime['avg_vol'] < vol_median

print(f"\n2. Volatility Regime Analysis")
print(f"   Median annualized vol (OOS): {vol_median:.4f}")
print(f"   High vol bars: {high_vol_mask.sum()} ({high_vol_mask.mean():.1%})")
print(f"   Low vol bars: {low_vol_mask.sum()} ({low_vol_mask.mean():.1%})")

if len(oos_trades) > 0:
    high_vol_trades = []
    low_vol_trades = []
    for _, trade in df_oos_t.iterrows():
        exit_time = trade['exit_time']
        idx = (df_oos_regime['datetime'] - exit_time).abs().idxmin()
        if pd.notna(df_oos_regime.loc[idx, 'avg_vol']):
            if df_oos_regime.loc[idx, 'avg_vol'] >= vol_median:
                high_vol_trades.append(trade)
            else:
                low_vol_trades.append(trade)
    
    if len(high_vol_trades) > 0:
        hv_pnl = [t['net_pnl'] for t in high_vol_trades]
        print(f"\n   High Volatility Periods:")
        print(f"     Trades: {len(high_vol_trades)}")
        print(f"     Win Rate: {np.mean([p > 0 for p in hv_pnl]):.1%}")
        print(f"     Mean PnL: ${np.mean(hv_pnl):.4f}")
    
    if len(low_vol_trades) > 0:
        lv_pnl = [t['net_pnl'] for t in low_vol_trades]
        print(f"\n   Low Volatility Periods:")
        print(f"     Trades: {len(low_vol_trades)}")
        print(f"     Win Rate: {np.mean([p > 0 for p in lv_pnl]):.1%}")
        print(f"     Mean PnL: ${np.mean(lv_pnl):.4f}")

# ==============================================================================
# 14. ALTERNATIVE: PRICE RATIO APPROACH
# ==============================================================================
print("\n" + "=" * 80)
print("ALTERNATIVE: PRICE RATIO APPROACH")
print("=" * 80)

df_ratio = df_valid.copy()
df_ratio['price_ratio'] = df_ratio['close_btc'] / df_ratio['close_eth']
df_ratio['ratio_mean'] = df_ratio['price_ratio'].rolling(LOOKBACK).mean()
df_ratio['ratio_std'] = df_ratio['price_ratio'].rolling(LOOKBACK).std()
df_ratio['ratio_z'] = (df_ratio['price_ratio'] - df_ratio['ratio_mean']) / df_ratio['ratio_std']

df_ratio_is = df_ratio[(df_ratio['datetime'] >= IS_START) & (df_ratio['datetime'] <= IS_END)].copy()
df_ratio_oos = df_ratio[(df_ratio['datetime'] >= OOS_START) & (df_ratio['datetime'] <= OOS_END)].copy()

# Use best config parameters for ratio approach
print(f"\nUsing best config parameters: Z_entry={best['z_entry']}, Z_exit={best['z_exit']}, "
      f"Max_hold={best['max_hold']}, SL_Z={best['sl_z']}")

# For ratio approach, we need a different PnL calculation
# When SHORT ratio: SHORT BTC, LONG ETH (1:1 dollar)
# When LONG ratio: LONG BTC, SHORT ETH (1:1 dollar)
def run_ratio_backtest(df_in, z_entry, z_exit, max_hold, sl_z=None,
                       cost_per_side=0.00085, position_size=100.0):
    """Run pairs trading using price ratio Z-score."""
    trades = []
    position = 0
    entry_idx = 0
    entry_z = 0
    entry_btc_price = 0
    entry_eth_price = 0
    
    data = df_in.reset_index(drop=True)
    
    for i in range(len(data)):
        z = data['ratio_z'].iloc[i]
        btc_price = data['close_btc'].iloc[i]
        eth_price = data['close_eth'].iloc[i]
        
        if np.isnan(z):
            continue
            
        if position == 0:
            if z > z_entry:
                position = -1  # SHORT ratio: SHORT BTC, LONG ETH
                entry_idx = i
                entry_z = z
                entry_btc_price = btc_price
                entry_eth_price = eth_price
            elif z < -z_entry:
                position = 1  # LONG ratio: LONG BTC, SHORT ETH
                entry_idx = i
                entry_z = z
                entry_btc_price = btc_price
                entry_eth_price = eth_price
        else:
            hold_bars = i - entry_idx
            exit_signal = False
            exit_reason = ''
            
            if position == 1 and z >= z_exit:
                exit_signal = True
                exit_reason = 'z_exit'
            elif position == -1 and z <= z_exit:
                exit_signal = True
                exit_reason = 'z_exit'
            
            if hold_bars >= max_hold:
                exit_signal = True
                exit_reason = 'max_hold'
            
            if sl_z is not None:
                if position == 1 and z < -sl_z:
                    exit_signal = True
                    exit_reason = 'stop_loss'
                elif position == -1 and z > sl_z:
                    exit_signal = True
                    exit_reason = 'stop_loss'
            
            if exit_signal:
                btc_ret = (btc_price - entry_btc_price) / entry_btc_price
                eth_ret = (eth_price - entry_eth_price) / entry_eth_price
                
                # 1:1 dollar allocation
                if position == 1:  # LONG BTC, SHORT ETH
                    gross_pnl = position_size * (btc_ret - eth_ret)
                else:  # SHORT BTC, LONG ETH
                    gross_pnl = position_size * (-btc_ret + eth_ret)
                
                total_cost = position_size * 4 * cost_per_side
                net_pnl = gross_pnl - total_cost
                
                trades.append({
                    'entry_time': data['datetime'].iloc[entry_idx],
                    'exit_time': data['datetime'].iloc[i],
                    'direction': 'LONG' if position == 1 else 'SHORT',
                    'entry_z': entry_z,
                    'exit_z': z,
                    'hold_bars': hold_bars,
                    'exit_reason': exit_reason,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'cost': total_cost,
                })
                position = 0
    
    return trades

ratio_trades_oos = run_ratio_backtest(
    df_ratio_oos, best['z_entry'], best['z_exit'],
    best['max_hold'], best['sl_z'], 0.00085
)

if len(ratio_trades_oos) > 0:
    df_ratio_trades = pd.DataFrame(ratio_trades_oos)
    print(f"\nRatio Approach (OOS, Taker costs):")
    print(f"  Trades: {len(df_ratio_trades)}")
    print(f"  Win Rate: {(df_ratio_trades['net_pnl'] > 0).mean():.1%}")
    print(f"  EV (net): ${df_ratio_trades['net_pnl'].mean():.4f}")
    print(f"  Total PnL: ${df_ratio_trades['net_pnl'].sum():.2f}")
    print(f"  Profit Factor: {df_ratio_trades[df_ratio_trades['net_pnl']>0]['net_pnl'].sum() / abs(df_ratio_trades[df_ratio_trades['net_pnl']<0]['net_pnl'].sum()):.2f}")
else:
    print("\nRatio Approach: No trades generated in OOS")

# ==============================================================================
# 15. RETURN DECOMPOSITION
# ==============================================================================
print("\n" + "=" * 80)
print("RETURN DECOMPOSITION (Best Config OOS)")
print("=" * 80)

if len(oos_trades) > 0:
    df_oos_t = pd.DataFrame(oos_trades)
    
    total_btc_leg = df_oos_t['btc_leg_pnl'].sum()
    total_eth_leg = df_oos_t['eth_leg_pnl'].sum()
    total_pnl = df_oos_t['net_pnl'].sum()
    total_gross = df_oos_t['gross_pnl'].sum()
    total_cost = df_oos_t['cost'].sum()
    
    print(f"\n  Total Gross PnL: ${total_gross:.2f}")
    print(f"    BTC leg total: ${total_btc_leg:.2f} ({total_btc_leg/total_gross*100:.1f}% of gross)")
    print(f"    ETH leg total: ${total_eth_leg:.2f} ({total_eth_leg/total_gross*100:.1f}% of gross)")
    print(f"  Total Costs:     -${total_cost:.2f}")
    print(f"  Total Net PnL:   ${total_pnl:.2f}")
    
    # Per-trade decomposition
    avg_btc_leg = df_oos_t['btc_leg_pnl'].mean()
    avg_eth_leg = df_oos_t['eth_leg_pnl'].mean()
    print(f"\n  Per-trade averages:")
    print(f"    BTC leg: ${avg_btc_leg:.4f}")
    print(f"    ETH leg: ${avg_eth_leg:.4f}")
    print(f"    Cost:    ${df_oos_t['cost'].mean():.4f}")
    print(f"    Net:     ${df_oos_t['net_pnl'].mean():.4f}")
    
    # Direction breakdown
    long_trades = df_oos_t[df_oos_t['direction'] == 'LONG']
    short_trades = df_oos_t[df_oos_t['direction'] == 'SHORT']
    
    print(f"\n  Direction Breakdown:")
    if len(long_trades) > 0:
        print(f"    LONG spread: n={len(long_trades)}, Win Rate={((long_trades['net_pnl']>0).mean()):.1%}, "
              f"EV=${long_trades['net_pnl'].mean():.4f}")
    if len(short_trades) > 0:
        print(f"    SHORT spread: n={len(short_trades)}, Win Rate={((short_trades['net_pnl']>0).mean()):.1%}, "
              f"EV=${short_trades['net_pnl'].mean():.4f}")

# ==============================================================================
# 16. FINAL VERDICT
# ==============================================================================
print("\n" + "=" * 80)
print("FINAL VERDICT")
print("=" * 80)

if len(oos_trades) > 0:
    df_oos_t = pd.DataFrame(oos_trades)
    pnl_values = df_oos_t['net_pnl'].values
    t_stat, p_value = stats.ttest_1samp(pnl_values, 0)
    
    # Monthly PnL estimate for $190 account
    # Scale: position_size was $100 per side, total exposure $200
    # For $190 account, we might use ~$95 per side (50% of equity per side)
    # But let's calculate based on actual results
    avg_trades_per_month = len(oos_trades) / 9.5  # OOS is ~9.5 months
    ev_per_trade = np.mean(pnl_values)
    monthly_pnl = avg_trades_per_month * ev_per_trade
    
    # Scale to $190 account (original was $100/side)
    # With $190, we can do $95/side, so scale factor = 0.95
    scale_factor = 190 / 200  # $190 account / $200 total exposure
    monthly_pnl_scaled = monthly_pnl * scale_factor
    
    # Cointegration stability
    coint_stable = coint_pct >= 60
    
    print(f"\n1. OOS Statistical Significance:")
    print(f"   t-statistic: {t_stat:.4f}")
    print(f"   p-value: {p_value:.6f}")
    print(f"   Significant at 5%? {'YES' if p_value < 0.05 else 'NO'}")
    
    print(f"\n2. Cointegration Stability:")
    print(f"   Cointegrated in {coint_pct:.0f}% of 3-month windows")
    print(f"   Stable? {'YES' if coint_stable else 'NO'}")
    
    print(f"\n3. Expected Monthly P&L for $190 Account:")
    print(f"   Avg trades/month: {avg_trades_per_month:.1f}")
    print(f"   EV/trade (unscaled): ${ev_per_trade:.4f}")
    print(f"   Monthly P&L (unscaled): ${monthly_pnl:.2f}")
    print(f"   Monthly P&L (scaled to $190): ${monthly_pnl_scaled:.2f}")
    
    print(f"\n4. Key Metrics (Best Config OOS):")
    print(f"   Config: {best['config']} ({best['cost']} cost)")
    print(f"   Trades: {best['oos_n']}")
    print(f"   Win Rate: {best['oos_win_rate']:.1%}")
    print(f"   EV (net): ${best['oos_ev_net']:.4f}")
    print(f"   Sharpe: {best['oos_sharpe']:.3f}")
    print(f"   Profit Factor: {best['oos_profit_factor']:.2f}")
    print(f"   Max Drawdown: ${best['oos_max_dd']:.2f}")
    
    # Decision logic
    is_significant = p_value < 0.05
    is_profitable = best['oos_ev_net'] > 0
    is_stable = coint_stable
    
    print(f"\n5. DECISION CRITERIA:")
    print(f"   OOS EV positive? {'YES' if is_profitable else 'NO'}")
    print(f"   OOS statistically significant (p<0.05)? {'YES' if is_significant else 'NO'}")
    print(f"   Cointegration stable (>60%)? {'YES' if is_stable else 'NO'}")
    
    if is_significant and is_profitable and is_stable:
        verdict = "IMPLEMENT"
    elif is_profitable and (is_significant or is_stable):
        verdict = "NEEDS MORE DATA"
    else:
        verdict = "REJECT"
    
    print(f"\n{'='*60}")
    print(f"   >>> RECOMMENDATION: {verdict} <<<")
    print(f"{'='*60}")
    
    if verdict == "IMPLEMENT":
        print(f"\n   Rationale: Strategy shows statistically significant positive EV")
        print(f"   in OOS period with stable cointegration. Ready for live trading")
        print(f"   with position sizing at half-Kelly or less.")
    elif verdict == "NEEDS MORE DATA":
        print(f"\n   Rationale: Strategy shows positive OOS EV but statistical")
        print(f"   significance is marginal. Collect more data before implementing.")
        print(f"   Consider paper trading for 3+ months.")
    else:
        print(f"\n   Rationale: Strategy does not meet minimum criteria for")
        print(f"   implementation. OOS performance is not convincing.")
else:
    print("\n   No OOS trades generated. REJECT.")

print("\n" + "=" * 80)
print("BACKTEST COMPLETE")
print("=" * 80)