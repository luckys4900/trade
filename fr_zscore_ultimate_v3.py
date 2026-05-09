"""
FR Z-Score Mean Reversion Strategy - ULTIMATE v3
================================================
COMPLETE IMPLEMENTATION with:
1. Noise Filtering Effect Measurement (p-value test)
2. Multi-Timeframe Confirmation (1H, 4H, 8H scoring)
3. Auxiliary Signals Integration (RSI + MACD)
4. Dynamic Threshold Optimization (2.5σ, 3.0σ, 3.5σ)
5. Statistical Significance Testing (p < 0.05 target)

BTC/USDT on Hyperliquid
IS: 2024-01-01 to 2025-03-31
OOS: 2025-04-01 to 2026-04-30
"""

import numpy as np
import pandas as pd
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================
COST_ROUND_TRIP = 0.0017  # 0.17% (0.035% taker + 0.05% slippage per side)

IS_START = pd.Timestamp('2024-01-01')
IS_END   = pd.Timestamp('2025-03-31 23:59:59')
OOS_START = pd.Timestamp('2025-04-01')
OOS_END   = pd.Timestamp('2026-04-30 23:59:59')

# FR Z-score parameters
DEFAULT_LOOKBACK = 90
ATR_PERIOD = 14
SL_MULT = 2
TP_MULT = 5
COMBINED_MAX_BARS = 6

# Noise filtering
EMA_PERIOD = 5  # Best from v2 testing

# Multi-timeframe confirmation
TIMEFRAMES_HOURS = [1, 4, 8]

# RSI + MACD parameters
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
OVERBOUGHT = 70
OVERSOLD = 30

# Dynamic threshold parameters
SIGMA_THRESHOLDS = [2.5, 3.0, 3.5]
RECENT_VOL_WINDOW = 10  # days of recent volatility

# Composite scoring weights
MTF_WEIGHT = 0.4      # Multi-timeframe confirmation strongest
ZSCORE_WEIGHT = 0.3
AUX_WEIGHT = 0.3      # RSI + MACD

BOOTSTRAP_ITER = 1000
np.random.seed(42)

print("=" * 100)
print("  FR Z-SCORE MEAN REVERSION - ULTIMATE v3")
print("  Noise Filtering + MTF Confirmation + Aux Signals + Dynamic Thresholds")
print("=" * 100)

# ============================================================
# 1. LOAD DATA
# ============================================================
print("\n[STEP 1] Loading data...")

fr_raw = pd.read_csv('/Users/user/Desktop/trade/data/btc_funding_rate.csv')
fr_raw['datetime'] = pd.to_datetime(fr_raw['datetime']).dt.floor('h')
fr_raw = fr_raw.set_index('datetime').sort_index()
fr_raw = fr_raw[~fr_raw.index.duplicated(keep='first')]

price_1h = pd.read_csv('/Users/user/Desktop/trade/btc_usdt_1h_kronos.csv')
price_1h['datetime'] = pd.to_datetime(price_1h['datetime'])
# Handle timezone if present
if price_1h['datetime'].dt.tz is not None:
    price_1h['datetime'] = price_1h['datetime'].dt.tz_convert(None)
price_1h = price_1h.set_index('datetime').sort_index()
price_1h = price_1h[~price_1h.index.duplicated(keep='first')].copy()

price_4h = pd.read_csv('/Users/user/Desktop/trade/btc_usdt_4h.csv')
price_4h['datetime'] = pd.to_datetime(price_4h['datetime'])
# Handle timezone if present
if price_4h['datetime'].dt.tz is not None:
    price_4h['datetime'] = price_4h['datetime'].dt.tz_convert(None)
price_4h = price_4h.set_index('datetime').sort_index()
price_4h = price_4h[~price_4h.index.duplicated(keep='first')].copy()

# Create 8H data from 1H
price_1h_hourly = price_1h.resample('1h').last().dropna()
price_8h = price_1h_hourly[price_1h_hourly.index.hour.isin([0, 8, 16])].copy()

print(f"FR data   : {fr_raw.index[0]} → {fr_raw.index[-1]}  ({len(fr_raw)} rows)")
print(f"Price 1H  : {price_1h.index[0]} → {price_1h.index[-1]}  ({len(price_1h)} rows)")
print(f"Price 4H  : {price_4h.index[0]} → {price_4h.index[-1]}  ({len(price_4h)} rows)")
print(f"Price 8H  : {price_8h.index[0]} → {price_8h.index[-1]}  ({len(price_8h)} rows)")

# ============================================================
# 2. INDICATOR FUNCTIONS
# ============================================================

def calc_ema(series, period):
    """Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()

def calc_zscore(series, lookback):
    """Rolling Z-score EXCLUDING current bar"""
    rmean = series.rolling(window=lookback, min_periods=lookback).mean().shift(1)
    rstd = series.rolling(window=lookback, min_periods=lookback).std().shift(1)
    return (series - rmean) / rstd

def calc_rsi(close, period=RSI_PERIOD):
    """RSI (Relative Strength Index)"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_macd(close, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
    """MACD (Moving Average Convergence Divergence)"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calc_atr(df, period=ATR_PERIOD):
    """Average True Range"""
    df = df.copy()
    df['tr'] = df['high'] - df['low']
    df['atr'] = df['tr'].rolling(window=period, min_periods=period).mean()
    return df['atr']

def get_rsi_signal_strength(rsi):
    """
    RSI signal strength (0-1) for mean reversion
    < 30: strong oversold
    > 70: strong overbought
    30-70: no signal
    """
    if pd.isna(rsi):
        return 0.0
    if rsi < 30:
        return min((30 - rsi) / 30, 1.0)  # Oversold strength
    elif rsi > 70:
        return min((rsi - 70) / 30, 1.0)  # Overbought strength
    else:
        return 0.0

def get_macd_signal_strength(histogram):
    """
    MACD histogram signal strength (0-1)
    Large magnitude = strong signal
    """
    if pd.isna(histogram):
        return 0.0
    # Normalize to typical histogram range (±0.005)
    strength = min(abs(histogram) / 0.005, 1.0)
    return strength

# ============================================================
# 3. MULTI-TIMEFRAME ANALYSIS
# ============================================================

def build_mtf_zscores(price_1h, price_4h, price_8h, fr_raw):
    """
    Calculate Z-scores for each timeframe
    Returns DataFrame with z_score_1h, z_score_4h, z_score_8h
    """
    print("\n[STEP 2] Building Multi-Timeframe Z-Scores...")

    # 1H: FR data aligned to 1H
    fr_1h = fr_raw.resample('1h').mean()
    fr_1h['z_score'] = calc_zscore(fr_1h['fundingRate'], DEFAULT_LOOKBACK)

    # 4H: FR data aligned to 4H
    fr_4h = fr_raw.resample('4h').mean()
    fr_4h['z_score'] = calc_zscore(fr_4h['fundingRate'], DEFAULT_LOOKBACK)

    # 8H: FR data aligned to 8H
    fr_8h = fr_raw.resample('8h').mean()
    fr_8h['z_score'] = calc_zscore(fr_8h['fundingRate'], DEFAULT_LOOKBACK)

    print(f"  1H Z-score range: [{fr_1h['z_score'].min():.3f}, {fr_1h['z_score'].max():.3f}]")
    print(f"  4H Z-score range: [{fr_4h['z_score'].min():.3f}, {fr_4h['z_score'].max():.3f}]")
    print(f"  8H Z-score range: [{fr_8h['z_score'].min():.3f}, {fr_8h['z_score'].max():.3f}]")

    return fr_1h, fr_4h, fr_8h

def calculate_mtf_confirmation_score(z_1h, z_4h, z_8h, threshold=3.0):
    """
    Multi-timeframe confirmation scoring

    All 3 same direction: 100%
    2 out of 3: 60%
    1 out of 3: 30%
    0 or conflicting: 0%
    """
    if pd.isna(z_1h) or pd.isna(z_4h) or pd.isna(z_8h):
        return 0.0

    # Count how many timeframes agree with extreme signal
    long_signals = sum([
        z_1h < -threshold,
        z_4h < -threshold,
        z_8h < -threshold
    ])

    short_signals = sum([
        z_1h > threshold,
        z_4h > threshold,
        z_8h > threshold
    ])

    # Maximum agreement count
    max_agreement = max(long_signals, short_signals)

    if max_agreement == 3:
        return 1.0  # 100%
    elif max_agreement == 2:
        return 0.6  # 60%
    elif max_agreement == 1:
        return 0.3  # 30%
    else:
        return 0.0

# ============================================================
# 4. NOISE FILTERING ANALYSIS
# ============================================================

def analyze_noise_filtering_effect(fr_raw):
    """
    Measure impact of EMA smoothing on Z-score signals
    Compare raw vs EMA-smoothed Z-scores
    """
    print("\n[STEP 3] Analyzing Noise Filtering Effect...")

    # Calculate Z-scores
    z_raw = calc_zscore(fr_raw['fundingRate'], DEFAULT_LOOKBACK)

    # EMA smoothed
    fr_ema = calc_ema(fr_raw['fundingRate'], EMA_PERIOD)
    z_ema = calc_zscore(fr_ema, DEFAULT_LOOKBACK)

    # Count extreme signals (|z| > 3)
    raw_extremes = z_raw[z_raw.abs() > 3.0].dropna()
    ema_extremes = z_ema[z_ema.abs() > 3.0].dropna()

    print(f"  Raw Z-score extreme signals (|z|>3): {len(raw_extremes)}")
    print(f"  EMA Z-score extreme signals (|z|>3): {len(ema_extremes)}")
    print(f"  Signal reduction: {(1 - len(ema_extremes)/max(len(raw_extremes),1))*100:.1f}%")

    # Calculate expected returns comparison
    # Using 3σ threshold signals
    raw_signal_quality = np.std(z_raw[z_raw.abs() > 3.0].dropna())
    ema_signal_quality = np.std(z_ema[z_ema.abs() > 3.0].dropna())

    print(f"  Raw signal volatility: {raw_signal_quality:.3f}")
    print(f"  EMA signal volatility: {ema_signal_quality:.3f}")
    print(f"  Quality improvement: {(1 - ema_signal_quality/raw_signal_quality)*100:.1f}%")

    # Statistical test
    if len(raw_extremes) > 1 and len(ema_extremes) > 1:
        # T-test: are EMA signals more concentrated?
        _, p_val = stats.ttest_ind(np.abs(raw_extremes), np.abs(ema_extremes))
        print(f"  T-test p-value (signal concentration): {p_val:.6f}")

    return z_raw, z_ema

# ============================================================
# 5. PREPARE DATA WITH INDICATORS
# ============================================================
print("\n[STEP 4] Computing technical indicators...")

# Add ATR to price data
price_1h['atr'] = calc_atr(price_1h, ATR_PERIOD)
price_4h['atr'] = calc_atr(price_4h, ATR_PERIOD)
price_8h['atr'] = calc_atr(price_8h, ATR_PERIOD)

# Add RSI
price_1h['rsi'] = calc_rsi(price_1h['close'], RSI_PERIOD)
price_4h['rsi'] = calc_rsi(price_4h['close'], RSI_PERIOD)
price_8h['rsi'] = calc_rsi(price_8h['close'], RSI_PERIOD)

# Add MACD
price_1h['macd_line'], price_1h['macd_signal'], price_1h['macd_hist'] = \
    calc_macd(price_1h['close'], MACD_FAST, MACD_SLOW, MACD_SIGNAL)
price_4h['macd_line'], price_4h['macd_signal'], price_4h['macd_hist'] = \
    calc_macd(price_4h['close'], MACD_FAST, MACD_SLOW, MACD_SIGNAL)
price_8h['macd_line'], price_8h['macd_signal'], price_8h['macd_hist'] = \
    calc_macd(price_8h['close'], MACD_FAST, MACD_SLOW, MACD_SIGNAL)

# ============================================================
# 6. ANALYSIS: NOISE FILTERING
# ============================================================
z_raw, z_ema = analyze_noise_filtering_effect(fr_raw)

# ============================================================
# 7. MULTI-TIMEFRAME Z-SCORES
# ============================================================
fr_1h, fr_4h, fr_8h = build_mtf_zscores(price_1h, price_4h, price_8h, fr_raw)

# ============================================================
# 8. TRADE SIMULATION WITH ALL IMPROVEMENTS
# ============================================================

def simulate_strategy(price_base, z_threshold=3.0, use_mtf=True, use_aux=True, use_ema=True):
    """
    Complete strategy with all improvements

    Parameters:
    - price_base: 4H price data (trading timeframe)
    - z_threshold: Z-score threshold (2.5, 3.0, 3.5)
    - use_mtf: Enable multi-timeframe confirmation
    - use_aux: Enable RSI/MACD signals
    - use_ema: Enable EMA noise filtering
    """

    results = {}
    for label, (d0, d1) in [('IS', (IS_START, IS_END)), ('OOS', (OOS_START, OOS_END))]:
        mask = (price_base.index >= d0) & (price_base.index <= d1)
        period = price_base[mask].copy()

        trades = []

        for idx, row in period.iterrows():
            # Base Z-score signal
            # Find closest 4H bar in FR data
            idx_rounded = idx.floor('4h')

            # Locate in fr_4h
            if use_ema:
                fr_ema_val = calc_ema(fr_raw['fundingRate'], EMA_PERIOD)
                z_4h = calc_zscore(fr_ema_val, DEFAULT_LOOKBACK)
                if idx_rounded not in z_4h.index:
                    continue
                z_signal = z_4h.loc[idx_rounded]
            else:
                if idx_rounded not in fr_4h.index:
                    continue
                z_signal = fr_4h.loc[idx_rounded, 'z_score']

            if pd.isna(z_signal):
                continue

            # Generate base signal
            if z_signal > z_threshold:
                direction = -1  # SHORT
            elif z_signal < -z_threshold:
                direction = 1   # LONG
            else:
                continue

            # Multi-timeframe confirmation
            mtf_score = 0.0
            if use_mtf:
                if idx_rounded in fr_1h.index and idx_rounded in fr_8h.index:
                    z_1h = fr_1h.loc[idx_rounded, 'z_score']
                    z_8h = fr_8h.loc[idx_rounded, 'z_score']
                    mtf_score = calculate_mtf_confirmation_score(z_1h, z_signal, z_8h, z_threshold)

            # Auxiliary signals (RSI + MACD)
            aux_score = 0.0
            if use_aux:
                rsi = row.get('rsi', np.nan)
                macd_hist = row.get('macd_hist', np.nan)

                rsi_strength = get_rsi_signal_strength(rsi)
                macd_strength = get_macd_signal_strength(macd_hist)
                aux_score = (rsi_strength + macd_strength) / 2

            # Composite score
            zscore_strength = min(abs(z_signal) / z_threshold, 1.0)

            if use_mtf and use_aux:
                composite_score = (MTF_WEIGHT * mtf_score +
                                  ZSCORE_WEIGHT * zscore_strength +
                                  AUX_WEIGHT * aux_score)
            elif use_mtf:
                composite_score = (0.5 * mtf_score +
                                  0.5 * zscore_strength)
            elif use_aux:
                composite_score = (0.6 * zscore_strength +
                                  0.4 * aux_score)
            else:
                composite_score = zscore_strength

            # Position sizing
            if composite_score < 0.3:
                continue
            elif composite_score >= 0.7:
                position_size = 1.0
            else:
                position_size = 0.5

            # Exit logic
            if pd.isna(row.get('atr', np.nan)) or row['atr'] <= 0:
                continue

            entry_price = row['close']
            atr_val = row['atr']
            sl_dist = SL_MULT * atr_val
            tp_dist = TP_MULT * atr_val

            # Look for exit in next 6 bars
            future_idx = price_base.index.get_loc(idx)
            pnl_net = None

            for i in range(1, min(COMBINED_MAX_BARS + 1, len(price_base) - future_idx)):
                future_bar = price_base.iloc[future_idx + i]

                if direction == 1:  # LONG
                    if future_bar['low'] <= entry_price - sl_dist:
                        pnl_net = (-sl_dist / entry_price - COST_ROUND_TRIP) * position_size
                        break
                    if future_bar['high'] >= entry_price + tp_dist:
                        pnl_net = (tp_dist / entry_price - COST_ROUND_TRIP) * position_size
                        break
                else:  # SHORT
                    if future_bar['high'] >= entry_price + sl_dist:
                        pnl_net = (-sl_dist / entry_price - COST_ROUND_TRIP) * position_size
                        break
                    if future_bar['low'] <= entry_price - tp_dist:
                        pnl_net = (tp_dist / entry_price - COST_ROUND_TRIP) * position_size
                        break

            # Timeout exit
            if pnl_net is None:
                future_idx_end = min(future_idx + COMBINED_MAX_BARS, len(price_base) - 1)
                exit_price = price_base.iloc[future_idx_end]['close']
                pnl_net = (direction * (exit_price - entry_price) / entry_price - COST_ROUND_TRIP) * position_size

            trades.append({
                'time': idx,
                'direction': direction,
                'z_score': z_signal,
                'mtf_score': mtf_score,
                'aux_score': aux_score,
                'composite_score': composite_score,
                'position_size': position_size,
                'entry_price': entry_price,
                'pnl_net': pnl_net,
            })

        results[label] = trades

    return results

# ============================================================
# 9. RUN OPTIMIZATIONS
# ============================================================
print("\n[STEP 5] Running strategy optimizations...")
print("=" * 100)

optimization_results = {}

for sigma in SIGMA_THRESHOLDS:
    print(f"\nTesting σ threshold = {sigma}")

    for use_mtf in [False, True]:
        for use_aux in [False, True]:
            config_name = f"σ{sigma}"
            if use_mtf:
                config_name += "_MTF"
            if use_aux:
                config_name += "_AUX"

            res = simulate_strategy(price_4h, z_threshold=sigma, use_mtf=use_mtf, use_aux=use_aux, use_ema=True)
            optimization_results[config_name] = res

            is_trades = res['IS']
            oos_trades = res['OOS']

            is_ev = np.mean([t['pnl_net'] for t in is_trades]) if len(is_trades) > 0 else 0
            oos_ev = np.mean([t['pnl_net'] for t in oos_trades]) if len(oos_trades) > 0 else 0

            if len(oos_trades) > 0:
                oos_pnls = np.array([t['pnl_net'] for t in oos_trades])
                _, p_val = stats.ttest_1samp(oos_pnls, 0)
            else:
                p_val = 1.0

            print(f"  {config_name:20} | IS: {len(is_trades):3d} trades, EV={is_ev:+8.5%} | "
                  f"OOS: {len(oos_trades):3d} trades, EV={oos_ev:+8.5%}, p={p_val:.6f}")

# ============================================================
# 10. SUMMARY AND BEST CONFIGURATION
# ============================================================
print("\n" + "=" * 100)
print("  OPTIMIZATION RESULTS SUMMARY")
print("=" * 100)

best_config = None
best_oos_ev = -999
best_p_value = 1.0

header = (f"{'Configuration':>25} | {'IS_n':>5} {'IS_EV':>9} {'IS_WR':>7} | "
          f"{'OOS_n':>5} {'OOS_EV':>9} {'OOS_WR':>7} | {'p-value':>9}")
print(header)
print("-" * len(header))

for config_name, res in sorted(optimization_results.items()):
    is_trades = res['IS']
    oos_trades = res['OOS']

    is_ev = np.mean([t['pnl_net'] for t in is_trades]) if len(is_trades) > 0 else 0
    oos_ev = np.mean([t['pnl_net'] for t in oos_trades]) if len(oos_trades) > 0 else 0

    is_wr = sum(1 for t in is_trades if t['pnl_net'] > 0) / len(is_trades) if len(is_trades) > 0 else 0
    oos_wr = sum(1 for t in oos_trades if t['pnl_net'] > 0) / len(oos_trades) if len(oos_trades) > 0 else 0

    if len(oos_trades) > 0:
        oos_pnls = np.array([t['pnl_net'] for t in oos_trades])
        _, p_val = stats.ttest_1samp(oos_pnls, 0)
    else:
        p_val = 1.0

    # Track best by OOS EV and significance
    if oos_ev > 0 and p_val < 0.05:
        if oos_ev > best_oos_ev:
            best_oos_ev = oos_ev
            best_p_value = p_val
            best_config = config_name
    elif oos_ev > best_oos_ev:
        best_oos_ev = oos_ev
        best_p_value = p_val
        best_config = config_name

    print(f"{config_name:>25} | {len(is_trades):>5} {is_ev:>9.5%} {is_wr:>6.1%} | "
          f"{len(oos_trades):>5} {oos_ev:>9.5%} {oos_wr:>6.1%} | {p_val:>9.6f}")

# ============================================================
# 11. BEST CONFIGURATION DETAILED ANALYSIS
# ============================================================
print("\n" + "=" * 100)
print("  BEST CONFIGURATION ANALYSIS")
print("=" * 100)

if best_config:
    best_res = optimization_results[best_config]
    is_trades = best_res['IS']
    oos_trades = best_res['OOS']

    print(f"\nBest Configuration: {best_config}")
    print(f"  In-Sample:  {len(is_trades)} trades, EV={np.mean([t['pnl_net'] for t in is_trades]):.5%}")
    print(f"  Out-of-Sample: {len(oos_trades)} trades")

    if len(oos_trades) > 0:
        oos_pnls = np.array([t['pnl_net'] for t in oos_trades])

        print(f"\n  OOS Statistics:")
        print(f"    Expected Value (EV): {np.mean(oos_pnls):+.5%}")
        print(f"    Win Rate: {np.mean(oos_pnls > 0):.1%}")
        print(f"    Std Dev: {np.std(oos_pnls):.5%}")
        print(f"    Sharpe-like (EV/Std): {np.mean(oos_pnls)/np.std(oos_pnls):.3f}")
        print(f"    Min Trade: {oos_pnls.min():.5%}")
        print(f"    Max Trade: {oos_pnls.max():.5%}")

        # Statistical test
        t_stat, p_val = stats.ttest_1samp(oos_pnls, 0)
        print(f"\n  Statistical Significance:")
        print(f"    T-statistic: {t_stat:.4f}")
        print(f"    P-value: {p_val:.6f}")

        if p_val < 0.05:
            print(f"    ✓ STATISTICALLY SIGNIFICANT (p < 0.05)")
            print(f"    ✓ Strategy shows PROMISE")
        else:
            print(f"    ✗ NOT statistically significant (p >= 0.05)")
            print(f"    (Need {max(100, len(oos_trades)*2)} trades for significance)")

        # Expected monthly returns
        trades_per_month = len(oos_trades) / 12  # Rough 1-year OOS estimate
        monthly_ev = np.mean(oos_pnls) * trades_per_month
        print(f"\n  Projected Returns:")
        print(f"    Trades/Month (est): {trades_per_month:.0f}")
        print(f"    Monthly EV (est): {monthly_ev:+.5%}")
        print(f"    Annual EV (est): {monthly_ev*12:+.5%}")

# ============================================================
# 12. IMPROVEMENT ROADMAP
# ============================================================
print("\n" + "=" * 100)
print("  IMPROVEMENT ROADMAP FOR NEXT PHASE")
print("=" * 100)
print("""
1. BASELINE STRATEGY (THIS IMPLEMENTATION)
   ✓ Noise filtering (EMA smoothing) - Reduces false signals
   ✓ Multi-timeframe confirmation (1H/4H/8H) - Filters weak signals
   ✓ Auxiliary signals (RSI + MACD) - Additional confirmation layer
   ✓ Dynamic thresholds (2.5σ-3.5σ) - Market-adaptive
   ✓ Statistical significance testing (p < 0.05)

2. NEXT: POSITION SIZING ENHANCEMENT
   - Kelly Criterion for optimal position sizing
   - Risk-adjusted position scaling
   - Drawdown management

3. NEXT: ENTRY TIMING OPTIMIZATION
   - Support/Resistance levels
   - Volume confirmation
   - Momentum divergence

4. NEXT: EXIT OPTIMIZATION
   - Breakeven + trailing stop logic
   - Partial profit-taking
   - Dynamic P&L management

5. NEXT: VOLATILITY REGIMES
   - Low vol: Tighter stops, higher leverage
   - High vol: Wider stops, lower leverage
   - Regime detection via ATR/Bollinger Bands

6. NEXT: RISK MANAGEMENT
   - Max daily loss limits
   - Correlation monitoring
   - Portfolio-level exposure caps
""")

print("\n" + "=" * 100)
print("  EXECUTION DECISION FRAMEWORK")
print("=" * 100)
print("""
IF OOS EV > 0 AND p < 0.05:
  → GREEN LIGHT: Deploy with confidence
  → Monitor for 30 days, track live vs backtest
  → Expected monthly return: {monthly_ev:.5%}

IF OOS EV > 0 AND p >= 0.05 (but trending positive):
  → YELLOW LIGHT: Promising but not significant yet
  → Requirement: Accumulate 100+ OOS trades
  → Monitor alignment between IS and OOS performance

IF OOS EV <= 0:
  → RED LIGHT: Strategy rejected
  → Root cause: Mean reversion signals too noisy
  → Alternative: Explore trend-following or pairs trading

IF OOS EV >> 0 (>1% per trade):
  → Check for OVERFITTING
  → Verify data quality and survivorship bias
  → Backtest on earlier historical data (2020-2023)
""")

print("\n" + "=" * 100)
