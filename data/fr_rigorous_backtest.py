"""
Funding Rate Z-score Mean Reversion - Rigorous Backtest
========================================================
BTC/USDT on Hyperliquid
IS: 2024-01-01 to 2025-03-31
OOS: 2025-04-01 to 2026-04-18
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
OOS_END   = pd.Timestamp('2026-04-18 23:59:59')

THRESHOLDS = [2.0, 2.5, 3.0, 3.5]
DEFAULT_LOOKBACK = 90
FIXED_HORIZONS = [2, 4, 6, 8]  # in 4h bars
ATR_PERIOD = 14
SL_MULT = 2
TP_MULT = 5
COMBINED_MAX_BARS = 6  # 4h bars
MAX_HOLD_ATR = 50      # max 4h bars for ATR-only exit

BOOTSTRAP_ITER = 1000
np.random.seed(42)

# ============================================================
# 1. LOAD DATA
# ============================================================
print("=" * 90)
print("  FUNDING RATE Z-SCORE MEAN REVERSION - RIGOROUS BACKTEST")
print("=" * 90)

fr_raw = pd.read_csv('btc_funding_rate.csv')
fr_raw['datetime'] = pd.to_datetime(fr_raw['datetime']).dt.floor('h')
fr_raw = fr_raw.set_index('datetime').sort_index()
fr_raw = fr_raw[~fr_raw.index.duplicated(keep='first')]

price_raw = pd.read_csv('btc_price_4h_cache.csv')
price_raw['datetime'] = pd.to_datetime(price_raw['datetime']).dt.tz_convert(None)
price_raw = price_raw.set_index('datetime').sort_index()
price_raw = price_raw[~price_raw.index.duplicated(keep='first')]

print(f"\nFR data   : {fr_raw.index[0]} → {fr_raw.index[-1]}  ({len(fr_raw)} rows)")
print(f"Price data : {price_raw.index[0]} → {price_raw.index[-1]}  ({len(price_raw)} rows)")

# ============================================================
# 2. RESAMPLE FR TO 8H (hours 0, 8, 16)
# ============================================================
fr_8h = fr_raw[fr_raw.index.hour.isin([0, 8, 16])].copy()
print(f"FR 8h     : {len(fr_8h)} rows")

# ============================================================
# 3. PREPARE PRICE DATA
# ============================================================
# ATR on 4h bars
price_raw['tr']  = price_raw['high'] - price_raw['low']
price_raw['atr'] = price_raw['tr'].rolling(window=ATR_PERIOD, min_periods=ATR_PERIOD).mean()

# 8h price bars (align with FR)
price_8h = price_raw[price_raw.index.hour.isin([0, 8, 16])].copy()

# ============================================================
# 4. MERGE FR + PRICE (8h)
# ============================================================
merged = price_8h.join(fr_8h['fundingRate'], how='inner')
merged = merged.dropna(subset=['fundingRate'])
merged = merged.sort_index()

print(f"Merged 8h : {len(merged)} rows,  {merged.index[0]} → {merged.index[-1]}")

# ============================================================
# 5. Z-SCORE CALCULATION
# ============================================================
def calc_zscore(series, lookback):
    """Rolling Z-score EXCLUDING current bar (shift(1) on rolling stats)."""
    rmean = series.rolling(window=lookback, min_periods=lookback).mean().shift(1)
    rstd  = series.rolling(window=lookback, min_periods=lookback).std().shift(1)
    return (series - rmean) / rstd

merged['z_score'] = calc_zscore(merged['fundingRate'], DEFAULT_LOOKBACK)

# Quick sanity check
valid_z = merged['z_score'].dropna()
print(f"\nZ-score range : {valid_z.min():.3f} to {valid_z.max():.3f}")
print(f"Z-score mean  : {valid_z.mean():.3f},  std: {valid_z.std():.3f}")

# ============================================================
# 6. TRADE SIMULATION ENGINE
# ============================================================
def simulate_trades(merged_df, price_4h, threshold, exit_method, lookback=DEFAULT_LOOKBACK):
    """
    Simulate all trades for a given threshold & exit method.
    Returns dict with 'IS' and 'OOS' keys, each a list of trade dicts.
    """
    z = calc_zscore(merged_df['fundingRate'], lookback)

    results = {}
    for label, (d0, d1) in [('IS', (IS_START, IS_END)), ('OOS', (OOS_START, OOS_END))]:
        mask = (merged_df.index >= d0) & (merged_df.index <= d1)
        period = merged_df[mask].copy()
        period['z'] = z[mask]

        trades = []
        for idx, row in period.iterrows():
            zv = row['z']
            if pd.isna(zv):
                continue
            if pd.isna(row.get('atr', np.nan)) or row['atr'] <= 0:
                continue

            # Signal
            if zv > threshold:
                direction = -1   # SHORT
            elif zv < -threshold:
                direction = 1    # LONG
            else:
                continue

            entry_price = row['close']
            atr_val     = row['atr']
            entry_time  = idx

            # Future 4h bars for exit tracking
            future = price_4h[price_4h.index > entry_time]
            if len(future) == 0:
                continue

            pnl_raw, pnl_net = _exit_trade(
                direction, entry_price, atr_val, future, exit_method
            )
            if pnl_raw is None:
                continue

            trades.append({
                'time': idx,
                'direction': direction,
                'z': zv,
                'entry_price': entry_price,
                'pnl_raw': pnl_raw,
                'pnl_net': pnl_net,
            })

        results[label] = trades
    return results


def _exit_trade(direction, entry, atr, future, exit_method):
    """Determine exit price and return (pnl_raw, pnl_net)."""
    sl_dist = SL_MULT * atr
    tp_dist = TP_MULT * atr

    if exit_method.startswith('fixed_'):
        n = int(exit_method.split('_')[1])
        if len(future) < n:
            return None, None
        exit_price = future.iloc[n - 1]['close']
        pnl_raw = direction * (exit_price - entry) / entry
        return pnl_raw, pnl_raw - COST_ROUND_TRIP

    elif exit_method == 'atr_sl_tp':
        max_bars = min(MAX_HOLD_ATR, len(future))
        for i in range(max_bars):
            bar = future.iloc[i]
            hit = _check_sl_tp(direction, entry, sl_dist, tp_dist, bar)
            if hit is not None:
                pnl_raw = direction * (hit - entry) / entry
                return pnl_raw, pnl_raw - COST_ROUND_TRIP
        # timeout - exit at last bar
        exit_price = future.iloc[max_bars - 1]['close']
        pnl_raw = direction * (exit_price - entry) / entry
        return pnl_raw, pnl_raw - COST_ROUND_TRIP

    elif exit_method == 'combined':
        max_bars = min(COMBINED_MAX_BARS, len(future))
        for i in range(max_bars):
            bar = future.iloc[i]
            hit = _check_sl_tp(direction, entry, sl_dist, tp_dist, bar)
            if hit is not None:
                pnl_raw = direction * (hit - entry) / entry
                return pnl_raw, pnl_raw - COST_ROUND_TRIP
        # time limit reached
        exit_price = future.iloc[max_bars - 1]['close']
        pnl_raw = direction * (exit_price - entry) / entry
        return pnl_raw, pnl_raw - COST_ROUND_TRIP

    return None, None


def _check_sl_tp(direction, entry, sl_dist, tp_dist, bar):
    """
    Check if SL or TP is hit within a bar.
    Returns exit price if hit, None otherwise.
    Conservative: if both could hit, SL takes priority.
    """
    if direction == 1:  # LONG
        if bar['low'] <= entry - sl_dist:
            return entry - sl_dist   # SL hit
        if bar['high'] >= entry + tp_dist:
            return entry + tp_dist   # TP hit
    else:  # SHORT
        if bar['high'] >= entry + sl_dist:
            return entry + sl_dist   # SL hit
        if bar['low'] <= entry - tp_dist:
            return entry - tp_dist   # TP hit
    return None


# ============================================================
# 7. RUN ALL BACKTESTS
# ============================================================
exit_methods = [f'fixed_{n}' for n in FIXED_HORIZONS] + ['atr_sl_tp', 'combined']
exit_labels  = [f'Fixed {n} bars' for n in FIXED_HORIZONS] + ['ATR SL/TP', 'Combined']

all_results = {}   # key = (threshold, exit_method)

print("\n" + "=" * 90)
print("  RUNNING BACKTESTS ...")
print("=" * 90)

for thr in THRESHOLDS:
    for em in exit_methods:
        key = (thr, em)
        res = simulate_trades(merged, price_raw, thr, em)
        all_results[key] = res

print("  Done.\n")

# ============================================================
# 8. RESULTS TABLE
# ============================================================
print("=" * 90)
print("  RESULTS TABLE")
print("=" * 90)

header = (f"{'Threshold':>10} | {'Exit':>14} | "
          f"{'IS_n':>5} {'IS_WR':>7} {'IS_EVraw':>9} {'IS_EVnet':>9} | "
          f"{'OOS_n':>5} {'OOS_WR':>7} {'OOS_EVraw':>9} {'OOS_EVnet':>9} | {'Verdict':>12}")
print(header)
print("-" * len(header))

best_oos_ev = -999
best_key = None

for thr in THRESHOLDS:
    for i, em in enumerate(exit_methods):
        key = (thr, em)
        res = all_results[key]
        label = exit_labels[i]

        rows = []
        for period in ['IS', 'OOS']:
            trades = res[period]
            n = len(trades)
            if n > 0:
                pnls_net = [t['pnl_net'] for t in trades]
                pnls_raw = [t['pnl_raw'] for t in trades]
                wr = sum(1 for p in pnls_net if p > 0) / n
                ev_raw = np.mean(pnls_raw)
                ev_net = np.mean(pnls_net)
            else:
                wr = ev_raw = ev_net = 0.0
            rows.append((n, wr, ev_raw, ev_net))

        is_n, is_wr, is_evr, is_evn = rows[0]
        oos_n, oos_wr, oos_evr, oos_evn = rows[1]

        # Verdict
        if oos_n < 10:
            verdict = "FEW TRADES"
        elif oos_evn > 0 and is_evn > 0:
            verdict = "PROMISING"
        elif oos_evn > 0:
            verdict = "UNSTABLE"
        else:
            verdict = "REJECT"

        print(f"{thr:>10.1f} | {label:>14} | "
              f"{is_n:>5} {is_wr:>6.1%} {is_evr:>9.5%} {is_evn:>9.5%} | "
              f"{oos_n:>5} {oos_wr:>6.1%} {oos_evr:>9.5%} {oos_evn:>9.5%} | {verdict:>12}")

        # Track best OOS EV
        if oos_n >= 10 and oos_evn > best_oos_ev:
            best_oos_ev = oos_evn
            best_key = key

print()

# ============================================================
# 9. STATISTICAL SIGNIFICANCE TESTS (best OOS)
# ============================================================
print("=" * 90)
print("  STATISTICAL SIGNIFICANCE - BEST OOS RESULT")
print("=" * 90)

if best_key is not None:
    best_thr, best_em = best_key
    best_idx = exit_methods.index(best_em)
    best_label = exit_labels[best_idx]
    best_res = all_results[best_key]

    oos_trades = best_res['OOS']
    oos_pnls = np.array([t['pnl_net'] for t in oos_trades])
    n_oos = len(oos_pnls)

    print(f"\n  Best strategy: threshold={best_thr}, exit={best_label}")
    print(f"  OOS trades: {n_oos},  EV_net: {np.mean(oos_pnls):.5%}")

    # --- t-test ---
    t_stat, p_val = stats.ttest_1samp(oos_pnls, 0)
    print(f"\n  t-test:")
    print(f"    t-statistic = {t_stat:.4f}")
    print(f"    p-value     = {p_val:.6f}")
    print(f"    Significant at 5%?  {'YES' if p_val < 0.05 else 'NO'}")

    # --- Bootstrap CI ---
    boot_means = []
    for _ in range(BOOTSTRAP_ITER):
        sample = np.random.choice(oos_pnls, size=n_oos, replace=True)
        boot_means.append(np.mean(sample))
    boot_means = np.array(boot_means)
    ci_lo = np.percentile(boot_means, 2.5)
    ci_hi = np.percentile(boot_means, 97.5)
    print(f"\n  Bootstrap ({BOOTSTRAP_ITER} resamples):")
    print(f"    95% CI for EV_net: [{ci_lo:.5%}, {ci_hi:.5%}]")
    print(f"    CI includes 0?     {'YES (not significant)' if ci_lo <= 0 <= ci_hi else 'NO (significant)'}")
else:
    print("  No valid OOS result found.")

# ============================================================
# 10. MONTHLY BREAKDOWN (best strategy)
# ============================================================
print("\n" + "=" * 90)
print("  MONTHLY BREAKDOWN - BEST OOS STRATEGY")
print("=" * 90)

if best_key is not None:
    oos_trades = best_res['OOS']
    # Group by month
    monthly = {}
    for t in oos_trades:
        ym = t['time'].strftime('%Y-%m')
        monthly.setdefault(ym, []).append(t['pnl_net'])

    print(f"\n  {'Month':>9} | {'n':>4} | {'WinRate':>7} | {'EV_net':>9}")
    print("  " + "-" * 40)
    losing_months = 0
    for ym in sorted(monthly.keys()):
        pnls = monthly[ym]
        n = len(pnls)
        wr = sum(1 for p in pnls if p > 0) / n if n > 0 else 0
        ev = np.mean(pnls)
        marker = " <<<" if ev < 0 else ""
        if ev < 0:
            losing_months += 1
        print(f"  {ym:>9} | {n:>4} | {wr:>6.1%} | {ev:>9.5%}{marker}")

    total_months = len(monthly)
    print(f"\n  Losing months: {losing_months} / {total_months}")

# ============================================================
# 11. ROBUSTNESS CHECK - Vary lookback
# ============================================================
print("\n" + "=" * 90)
print("  ROBUSTNESS CHECK - VARY LOOKBACK WINDOW")
print("=" * 90)

lookbacks = [60, 90, 120, 180]
print(f"\n  Using best threshold={best_thr}, exit={best_label}")
print(f"\n  {'Lookback':>8} | {'IS_n':>5} {'IS_EVnet':>9} | {'OOS_n':>5} {'OOS_EVnet':>9} | {'Hold?':>6}")
print("  " + "-" * 55)

for lb in lookbacks:
    res = simulate_trades(merged, price_raw, best_thr, best_em, lookback=lb)
    is_t = res['IS']
    oos_t = res['OOS']
    is_n = len(is_t)
    oos_n = len(oos_t)
    is_ev = np.mean([t['pnl_net'] for t in is_t]) if is_n > 0 else 0
    oos_ev = np.mean([t['pnl_net'] for t in oos_t]) if oos_n > 0 else 0
    hold = "YES" if oos_ev > 0 else "NO"
    print(f"  {lb:>8} | {is_n:>5} {is_ev:>9.5%} | {oos_n:>5} {oos_ev:>9.5%} | {hold:>6}")

# ============================================================
# 12. ROBUSTNESS CHECK - Vary IS/OOS split
# ============================================================
print("\n" + "=" * 90)
print("  ROBUSTNESS CHECK - VARY IS/OOS SPLIT DATE")
print("=" * 90)

split_dates = [
    (pd.Timestamp('2025-03-01'), "2025-03-01"),
    (pd.Timestamp('2025-04-01'), "2025-04-01 (default)"),
    (pd.Timestamp('2025-05-01'), "2025-05-01"),
]

print(f"\n  Using threshold={best_thr}, exit={best_label}, lookback={DEFAULT_LOOKBACK}")
print(f"\n  {'Split Date':>22} | {'IS_n':>5} {'IS_EVnet':>9} | {'OOS_n':>5} {'OOS_EVnet':>9} | {'Hold?':>6}")
print("  " + "-" * 65)

for split_dt, split_label in split_dates:
    # Temporarily override
    _is_end = split_dt - pd.Timedelta(seconds=1)
    _oos_start = split_dt

    z = calc_zscore(merged['fundingRate'], DEFAULT_LOOKBACK)
    is_trades = []
    oos_trades_rb = []

    mask_is  = (merged.index >= IS_START) & (merged.index <= _is_end)
    mask_oos = (merged.index >= _oos_start) & (merged.index <= OOS_END)

    for mask, trade_list in [(mask_is, is_trades), (mask_oos, oos_trades_rb)]:
        period = merged[mask].copy()
        for idx, row in period.iterrows():
            zv = z.loc[idx] if idx in z.index else np.nan
            if pd.isna(zv) or pd.isna(row.get('atr', np.nan)) or row['atr'] <= 0:
                continue
            if zv > best_thr:
                direction = -1
            elif zv < -best_thr:
                direction = 1
            else:
                continue
            entry_price = row['close']
            atr_val = row['atr']
            future = price_raw[price_raw.index > idx]
            if len(future) == 0:
                continue
            pnl_raw, pnl_net = _exit_trade(direction, entry_price, atr_val, future, best_em)
            if pnl_raw is not None:
                trade_list.append({'pnl_net': pnl_net})

    is_n = len(is_trades)
    oos_n = len(oos_trades_rb)
    is_ev = np.mean([t['pnl_net'] for t in is_trades]) if is_n > 0 else 0
    oos_ev = np.mean([t['pnl_net'] for t in oos_trades_rb]) if oos_n > 0 else 0
    hold = "YES" if oos_ev > 0 else "NO"
    print(f"  {split_label:>22} | {is_n:>5} {is_ev:>9.5%} | {oos_n:>5} {oos_ev:>9.5%} | {hold:>6}")

# ============================================================
# 13. KELLY CRITERION
# ============================================================
print("\n" + "=" * 90)
print("  KELLY CRITERION - BEST OOS STRATEGY")
print("=" * 90)

if best_key is not None:
    oos_pnls_arr = np.array([t['pnl_net'] for t in best_res['OOS']])
    n = len(oos_pnls_arr)
    wins = oos_pnls_arr[oos_pnls_arr > 0]
    losses = oos_pnls_arr[oos_pnls_arr <= 0]

    p = len(wins) / n if n > 0 else 0
    q = 1 - p
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 1e-9
    b = avg_win / avg_loss if avg_loss > 0 else 1e9

    # f* = (p*b - q) / b
    kelly = (p * b - q) / b if b > 0 else 0

    print(f"\n  Win rate (p)   : {p:.4f}")
    print(f"  Loss rate (q)  : {q:.4f}")
    print(f"  Avg win        : {avg_win:.5%}")
    print(f"  Avg loss       : {avg_loss:.5%}")
    print(f"  Win/Loss ratio  : {b:.4f}")
    print(f"  Kelly fraction  : {kelly:.4f} ({kelly*100:.2f}%)")
    print(f"\n  → Suggested risk per trade: {max(kelly, 0)*100:.2f}% of capital")
    if kelly <= 0:
        print(f"  ⚠ Kelly ≤ 0 → strategy has NEGATIVE edge, do NOT trade!")

# ============================================================
# 14. MAXIMUM DRAWDOWN
# ============================================================
print("\n" + "=" * 90)
print("  MAXIMUM DRAWDOWN - BEST OOS STRATEGY")
print("=" * 90)

if best_key is not None:
    oos_trades_sorted = sorted(best_res['OOS'], key=lambda t: t['time'])
    pnls = [t['pnl_net'] for t in oos_trades_sorted]

    # Equity curve starting at 1.0, each trade adds pnl_net fraction
    equity = [1.0]
    for p in pnls:
        equity.append(equity[-1] * (1 + p))

    # Drawdown series
    peak = np.maximum.accumulate(equity)
    dd = [(e - p) / p for e, p in zip(equity, peak)]
    max_dd = min(dd)
    max_dd_duration = 0
    current_duration = 0
    for d in dd:
        if d < 0:
            current_duration += 1
            max_dd_duration = max(max_dd_duration, current_duration)
        else:
            current_duration = 0

    print(f"\n  Total OOS trades : {len(pnls)}")
    print(f"  Final equity     : {equity[-1]:.4f}")
    print(f"  Max drawdown     : {max_dd:.5%}")
    print(f"  Max DD duration  : {max_dd_duration} trades")

# ============================================================
# 15. FINAL VERDICT
# ============================================================
print("\n" + "=" * 90)
print("  +" + "=" * 70 + "+")
print("  |                        FINAL VERDICT                             |")
print("  +" + "=" * 70 + "+")

if best_key is not None:
    oos_pnls_arr = np.array([t['pnl_net'] for t in best_res['OOS']])
    t_stat, p_val = stats.ttest_1samp(oos_pnls_arr, 0)

    sig = p_val < 0.05
    print(f"\n  Best strategy: threshold={best_thr}, exit={best_label}")
    print(f"  OOS EV_net: {np.mean(oos_pnls_arr):.5%}")
    print(f"  OOS trades: {len(oos_pnls_arr)}")
    print(f"  OOS win rate: {np.mean(oos_pnls_arr > 0):.1%}")
    print()
    print(f"  Statistical significance (t-test):")
    print(f"    t-stat = {t_stat:.4f},  p-value = {p_val:.6f}")
    print(f"    OOS EV significantly different from 0?  {'YES' if sig else 'NO'} (p={p_val:.4f})")
    print()

    # Robustness summary
    robust_count = 0
    robust_total = 0
    for lb in lookbacks:
        res = simulate_trades(merged, price_raw, best_thr, best_em, lookback=lb)
        oos_t = res['OOS']
        if len(oos_t) > 0:
            oos_ev = np.mean([t['pnl_net'] for t in oos_t])
            robust_total += 1
            if oos_ev > 0:
                robust_count += 1

    robust_split_count = 0
    for split_dt, _ in split_dates:
        _is_end = split_dt - pd.Timedelta(seconds=1)
        _oos_start = split_dt
        z = calc_zscore(merged['fundingRate'], DEFAULT_LOOKBACK)
        mask_oos = (merged.index >= _oos_start) & (merged.index <= OOS_END)
        oos_trades_rb = []
        period = merged[mask_oos]
        for idx, row in period.iterrows():
            zv = z.loc[idx] if idx in z.index else np.nan
            if pd.isna(zv) or pd.isna(row.get('atr', np.nan)) or row['atr'] <= 0:
                continue
            if zv > best_thr:
                direction = -1
            elif zv < -best_thr:
                direction = 1
            else:
                continue
            entry_price = row['close']
            atr_val = row['atr']
            future = price_raw[price_raw.index > idx]
            if len(future) == 0:
                continue
            pnl_raw, pnl_net = _exit_trade(direction, entry_price, atr_val, future, best_em)
            if pnl_raw is not None:
                oos_trades_rb.append({'pnl_net': pnl_net})
        if len(oos_trades_rb) > 0:
            oos_ev = np.mean([t['pnl_net'] for t in oos_trades_rb])
            if oos_ev > 0:
                robust_split_count += 1

    print(f"  Robustness across lookback windows:")
    print(f"    Positive OOS EV in {robust_count}/{robust_total} lookback settings")
    print(f"  Robustness across IS/OOS splits:")
    print(f"    Positive OOS EV in {robust_split_count}/3 split settings")
    robust = (robust_count >= 3) and (robust_split_count >= 2)
    print(f"    Strategy robust?  {'YES' if robust else 'NO'}")
    print()

    # Expected monthly P&L for $190 account
    avg_ev = np.mean(oos_pnls_arr)
    trades_per_month = len(oos_pnls_arr) / max(1, len(set(t['time'].strftime('%Y-%m') for t in best_res['OOS'])))
    monthly_pnl = 190 * avg_ev * trades_per_month
    print(f"  Expected monthly P&L for $190 account:")
    print(f"    Avg EV per trade  : {avg_ev:.5%}")
    print(f"    Avg trades/month  : {trades_per_month:.1f}")
    print(f"    Expected monthly  : ${monthly_pnl:.2f}")
    print()

    # Final recommendation
    if sig and robust and avg_ev > 0:
        rec = "IMPLEMENT"
    elif not sig or not robust:
        rec = "REJECT"
    else:
        rec = "NEEDS MORE DATA"

    print(f"  +---------------------------------------------+")
    print(f"  |  RECOMMENDATION:  {rec:<26}|")
    print(f"  +---------------------------------------------+")
    print()
    print(f"  Reasoning:")
    if not sig:
        print(f"    - OOS EV is NOT statistically significant (p={p_val:.4f} > 0.05)")
    else:
        print(f"    - OOS EV IS statistically significant (p={p_val:.4f} < 0.05)")
    if not robust:
        print(f"    - Strategy is NOT robust across parameter variations")
    else:
        print(f"    - Strategy IS robust across parameter variations")
    if avg_ev > 0:
        print(f"    - Positive expected value: {avg_ev:.5%} per trade")
    else:
        print(f"    - Negative expected value: {avg_ev:.5%} per trade")
    print(f"    - Max drawdown: {max_dd:.5%}")
    print(f"    - Kelly fraction: {kelly:.4f}")

print("\n" + "=" * 90)
print("  BACKTEST COMPLETE")
print("=" * 90)