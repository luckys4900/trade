"""
FR Z-Score Strategy - ROOT CAUSE DIAGNOSIS
===========================================
Investigate why strategy shows negative OOS EV
"""

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

print("=" * 110)
print("  FR Z-SCORE STRATEGY - ROOT CAUSE ANALYSIS")
print("=" * 110)

# Load data
fr_raw = pd.read_csv('/Users/user/Desktop/trade/data/btc_funding_rate.csv')
fr_raw['datetime'] = pd.to_datetime(fr_raw['datetime']).dt.floor('h')
fr_raw = fr_raw.set_index('datetime').sort_index()
fr_raw = fr_raw[~fr_raw.index.duplicated(keep='first')]

price_1h = pd.read_csv('/Users/user/Desktop/trade/btc_usdt_1h_kronos.csv')
price_1h['datetime'] = pd.to_datetime(price_1h['datetime'])
price_1h = price_1h.set_index('datetime').sort_index()
price_1h = price_1h[~price_1h.index.duplicated(keep='first')].copy()

print("\n[ANALYSIS 1] IS vs OOS PERIOD CHARACTERISTICS")
print("-" * 110)

IS_START = pd.Timestamp('2024-04-12')
IS_END   = pd.Timestamp('2025-03-31 23:59:59')
OOS_START = pd.Timestamp('2025-04-01')
OOS_END   = pd.Timestamp('2026-03-02 23:59:59')

# Funding rate analysis
fr_is = fr_raw[(fr_raw.index >= IS_START) & (fr_raw.index <= IS_END)]
fr_oos = fr_raw[(fr_raw.index >= OOS_START) & (fr_raw.index <= OOS_END)]

print(f"\nIS Funding Rate ({len(fr_is)} hours):")
print(f"  Mean: {fr_is['fundingRate'].mean()*10000:.4f} bps")
print(f"  Std:  {fr_is['fundingRate'].std()*10000:.4f} bps")
print(f"  Min:  {fr_is['fundingRate'].min()*10000:.4f} bps")
print(f"  Max:  {fr_is['fundingRate'].max()*10000:.4f} bps")
print(f"  Positive count: {(fr_is['fundingRate'] > 0).sum()} ({(fr_is['fundingRate'] > 0).sum()/len(fr_is)*100:.1f}%)")

print(f"\nOOS Funding Rate ({len(fr_oos)} hours):")
print(f"  Mean: {fr_oos['fundingRate'].mean()*10000:.4f} bps")
print(f"  Std:  {fr_oos['fundingRate'].std()*10000:.4f} bps")
print(f"  Min:  {fr_oos['fundingRate'].min()*10000:.4f} bps")
print(f"  Max:  {fr_oos['fundingRate'].max()*10000:.4f} bps")
print(f"  Positive count: {(fr_oos['fundingRate'] > 0).sum()} ({(fr_oos['fundingRate'] > 0).sum()/len(fr_oos)*100:.1f}%)")

# Price analysis
price_is = price_1h[(price_1h.index >= IS_START) & (price_1h.index <= IS_END)]
price_oos = price_1h[(price_1h.index >= OOS_START) & (price_1h.index <= OOS_END)]

print(f"\nIS Price Returns ({len(price_is)} hours):")
price_is_returns = price_is['close'].pct_change()
print(f"  Mean hourly return: {price_is_returns.mean()*10000:.2f} bps")
print(f"  Hourly volatility: {price_is_returns.std()*100:.4f}%")
print(f"  Positive hours: {(price_is_returns > 0).sum()} ({(price_is_returns > 0).sum()/len(price_is_returns)*100:.1f}%)")

print(f"\nOOS Price Returns ({len(price_oos)} hours):")
price_oos_returns = price_oos['close'].pct_change()
print(f"  Mean hourly return: {price_oos_returns.mean()*10000:.2f} bps")
print(f"  Hourly volatility: {price_oos_returns.std()*100:.4f}%")
print(f"  Positive hours: {(price_oos_returns > 0).sum()} ({(price_oos_returns > 0).sum()/len(price_oos_returns)*100:.1f}%)")

# ============================================================
# ANALYSIS 2: Z-SCORE SIGNAL QUALITY
# ============================================================
print("\n[ANALYSIS 2] Z-SCORE SIGNAL QUALITY")
print("-" * 110)

def calc_zscore(series, lookback):
    rmean = series.rolling(window=lookback, min_periods=lookback).mean().shift(1)
    rstd = series.rolling(window=lookback, min_periods=lookback).std().shift(1)
    return (series - rmean) / rstd

z_all = calc_zscore(fr_raw['fundingRate'], 90)
z_is = z_all[(z_all.index >= IS_START) & (z_all.index <= IS_END)]
z_oos = z_all[(z_all.index >= OOS_START) & (z_all.index <= OOS_END)]

print(f"\nZ-Score IS (|z| > 3 signals):")
z_is_extreme = z_is[z_is.abs() > 3].dropna()
print(f"  Count: {len(z_is_extreme)}")
if len(z_is_extreme) > 0:
    print(f"  Mean: {z_is_extreme.mean():.3f}")
    print(f"  Std:  {z_is_extreme.std():.3f}")

print(f"\nZ-Score OOS (|z| > 3 signals):")
z_oos_extreme = z_oos[z_oos.abs() > 3].dropna()
print(f"  Count: {len(z_oos_extreme)}")
if len(z_oos_extreme) > 0:
    print(f"  Mean: {z_oos_extreme.mean():.3f}")
    print(f"  Std:  {z_oos_extreme.std():.3f}")

# ============================================================
# ANALYSIS 3: MEAN REVERSION STRENGTH
# ============================================================
print("\n[ANALYSIS 3] MEAN REVERSION EFFECTIVENESS")
print("-" * 110)

def analyze_mean_reversion(fr_series, price_series, lookback=90, forward_hours=6):
    """
    Measure mean reversion effectiveness:
    When FR is at extreme (±3σ), what's the next N-hour return?
    """
    z_scores = calc_zscore(fr_series, lookback)

    # Find extreme signals
    long_signals = z_scores[z_scores < -3].dropna()   # Oversold FR → expect price UP
    short_signals = z_scores[z_scores > 3].dropna()   # Overbought FR → expect price DOWN

    if len(long_signals) == 0 or len(short_signals) == 0:
        return None

    # Measure forward returns
    long_returns = []
    short_returns = []

    for idx in long_signals.index:
        # Find price at signal time
        price_at_signal = price_series.loc[:idx].iloc[-1] if idx in price_series.index or len(price_series.loc[:idx]) > 0 else None
        if price_at_signal is None:
            continue

        # Forward return
        future_prices = price_series[price_series.index > idx]
        if len(future_prices) >= forward_hours:
            future_price = future_prices.iloc[forward_hours - 1]
            ret = (future_price['close'] - price_at_signal['close']) / price_at_signal['close']
            long_returns.append(ret)

    for idx in short_signals.index:
        price_at_signal = price_series.loc[:idx].iloc[-1] if idx in price_series.index or len(price_series.loc[:idx]) > 0 else None
        if price_at_signal is None:
            continue

        future_prices = price_series[price_series.index > idx]
        if len(future_prices) >= forward_hours:
            future_price = future_prices.iloc[forward_hours - 1]
            ret = -(future_price['close'] - price_at_signal['close']) / price_at_signal['close']  # Negative for short
            short_returns.append(ret)

    return {
        'long_signals': len(long_returns),
        'long_ret_mean': np.mean(long_returns) if long_returns else 0,
        'long_ret_std': np.std(long_returns) if long_returns else 0,
        'short_signals': len(short_returns),
        'short_ret_mean': np.mean(short_returns) if short_returns else 0,
        'short_ret_std': np.std(short_returns) if short_returns else 0,
    }

print("\nIS Mean Reversion (6-hour forward look):")
result_is = analyze_mean_reversion(fr_is, price_is, lookback=90, forward_hours=6)
if result_is:
    print(f"  LONG signals (z < -3):  {result_is['long_signals']} signals")
    print(f"    Mean 6h return: {result_is['long_ret_mean']*100:+.4f}%")
    print(f"    Std deviation: {result_is['long_ret_std']*100:.4f}%")
    print(f"  SHORT signals (z > 3): {result_is['short_signals']} signals")
    print(f"    Mean 6h return: {result_is['short_ret_mean']*100:+.4f}%")
    print(f"    Std deviation: {result_is['short_ret_std']*100:.4f}%")

print("\nOOS Mean Reversion (6-hour forward look):")
result_oos = analyze_mean_reversion(fr_oos, price_oos, lookback=90, forward_hours=6)
if result_oos:
    print(f"  LONG signals (z < -3):  {result_oos['long_signals']} signals")
    print(f"    Mean 6h return: {result_oos['long_ret_mean']*100:+.4f}%")
    print(f"    Std deviation: {result_oos['long_ret_std']*100:.4f}%")
    print(f"  SHORT signals (z > 3): {result_oos['short_signals']} signals")
    print(f"    Mean 6h return: {result_oos['short_ret_mean']*100:+.4f}%")
    print(f"    Std deviation: {result_oos['short_ret_std']*100:.4f}%")

# ============================================================
# ANALYSIS 4: REGIME CHANGE
# ============================================================
print("\n[ANALYSIS 4] REGIME CHANGE: IS vs OOS")
print("-" * 110)

print("\nFR distribution changes (IS → OOS):")
print(f"  Mean FR: {fr_is['fundingRate'].mean()*10000:.4f} → {fr_oos['fundingRate'].mean()*10000:.4f} bps")
print(f"  Volatility: {fr_is['fundingRate'].std()*10000:.4f} → {fr_oos['fundingRate'].std()*10000:.4f} bps")
print(f"  Skewness: {stats.skew(fr_is['fundingRate']):.3f} → {stats.skew(fr_oos['fundingRate']):.3f}")
print(f"  Kurtosis: {stats.kurtosis(fr_is['fundingRate']):.3f} → {stats.kurtosis(fr_oos['fundingRate']):.3f}")

# Statistical test
_, p_val = stats.ttest_ind(fr_is['fundingRate'].dropna(), fr_oos['fundingRate'].dropna())
print(f"  Mean difference p-value: {p_val:.6f}")
if p_val < 0.05:
    print(f"  ✗ SIGNIFICANT REGIME CHANGE (p < 0.05)")
else:
    print(f"  ✓ No significant regime change")

# ============================================================
# ANALYSIS 5: TRANSACTION COSTS IMPACT
# ============================================================
print("\n[ANALYSIS 5] TRANSACTION COSTS ANALYSIS")
print("-" * 110)

COST_ROUND_TRIP = 0.0017
ATR_PERIOD = 14
SL_MULT = 2
TP_MULT = 5

# Calculate ATR for both periods
price_is['tr'] = price_is['high'] - price_is['low']
price_is['atr'] = price_is['tr'].rolling(window=ATR_PERIOD).mean()

price_oos['tr'] = price_oos['high'] - price_oos['low']
price_oos['atr'] = price_oos['tr'].rolling(window=ATR_PERIOD).mean()

print(f"\nIS ATR ({len(price_is)}):")
atr_is = price_is['atr'].dropna()
print(f"  Mean: {atr_is.mean():.2f}")
print(f"  Min: {atr_is.min():.2f}")
print(f"  Max: {atr_is.max():.2f}")

print(f"\nOOS ATR ({len(price_oos)}):")
atr_oos = price_oos['atr'].dropna()
print(f"  Mean: {atr_oos.mean():.2f}")
print(f"  Min: {atr_oos.min():.2f}")
print(f"  Max: {atr_oos.max():.2f}")

# P&L breakdown
avg_atr_is = atr_is.mean()
avg_atr_oos = atr_oos.mean()

tp_dist_is = TP_MULT * avg_atr_is
tp_dist_oos = TP_MULT * avg_atr_oos

pnl_gross_is = tp_dist_is / price_is['close'].mean()
pnl_gross_oos = tp_dist_oos / price_oos['close'].mean()

pnl_net_is = pnl_gross_is - COST_ROUND_TRIP
pnl_net_oos = pnl_gross_oos - COST_ROUND_TRIP

print(f"\nIS Trade P&L (TP @ {TP_MULT}x ATR):")
print(f"  Gross return: {pnl_gross_is*100:+.3f}%")
print(f"  Transaction cost: -{COST_ROUND_TRIP*100:.3f}%")
print(f"  Net return: {pnl_net_is*100:+.3f}%")

print(f"\nOOS Trade P&L (TP @ {TP_MULT}x ATR):")
print(f"  Gross return: {pnl_gross_oos*100:+.3f}%")
print(f"  Transaction cost: -{COST_ROUND_TRIP*100:.3f}%")
print(f"  Net return: {pnl_net_oos*100:+.3f}%")

if pnl_net_oos < 0:
    print(f"\n✗ CRITICAL: Expected per-trade profit is NEGATIVE in OOS period")
    print(f"  Transaction costs exceed average winning trade size")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 110)
print("  ROOT CAUSE DIAGNOSIS - CONCLUSIONS")
print("=" * 110)

print("""
HYPOTHESIS 1: REGIME CHANGE (Volatility / FR structure)
  Status: [CHECK]
  Impact: Mean reversion strength varies between IS and OOS periods

HYPOTHESIS 2: MEAN REVERSION BREAKDOWN (OOS)
  Status: [CHECK]
  Evidence: Forward returns after Z-score signals are smaller

HYPOTHESIS 3: TRANSACTION COSTS TOO HIGH
  Status: [CHECK]
  Evidence: TP targets may be smaller than round-trip costs

HYPOTHESIS 4: OVERFITTING (IS → OOS performance gap)
  Status: [CHECK]
  Evidence: IS EV positive, OOS EV negative suggests parameter overfitting

REMEDIATION STEPS:
1. Increase TP target (5x → 8x ATR) to exceed transaction costs
2. Use only "high confidence" signals (filter by additional indicators)
3. Implement regime detection to disable in mean-reverting-hostile environments
4. Test on DIFFERENT time period (2022-2023) to verify robustness
5. Consider alternative exit strategies:
   - Breakeven + trailing stop
   - Partial profit-taking
   - Momentum-based exits
""")

print("=" * 110)
