import pandas as pd
import numpy as np
from itertools import product
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ── Load data ──
df = pd.read_csv('btc_price_4h_cache.csv')
df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
df = df.sort_values('datetime').reset_index(drop=True)

# ── ATR helper ──
def calc_atr(h, l, c, period):
    tr = np.maximum(h[1:] - l[1:],
        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    tr = np.concatenate([[np.nan], tr])
    atr = pd.Series(tr).rolling(period).mean().values
    return atr

# ── Inside bar detection & backtest engine ──
def run_backtest(df, atr_period, tp_mult, sl_mult, max_hold, cost_pct):
    o = df['open'].values; h = df['high'].values; l = df['low'].values
    c = df['close'].values; dt = df['datetime'].values

    atr = calc_atr(h, l, c, atr_period)
    n = len(df)
    trades = []

    i = max(atr_period + 1, 2)
    while i < n - 1:
        if np.isnan(atr[i]):
            i += 1; continue
        # Inside bar: bar[i] inside bar[i-1]
        if h[i] < h[i-1] and l[i] > l[i-1]:
            prev_high = h[i-1]; prev_low = l[i-1]
            atr_val = atr[i]
            # Entry at bar[i+1]
            j = i + 1
            if j >= n: break
            # Determine direction
            long_sig = c[j] > prev_high
            short_sig = c[j] < prev_low
            if long_sig and short_sig:
                direction = 1 if c[j] > o[j] else -1
            elif long_sig:
                direction = 1
            elif short_sig:
                direction = -1
            else:
                i += 1; continue

            entry_price = c[j]
            if direction == 1:
                tp_price = entry_price + tp_mult * atr_val
                sl_price = entry_price - sl_mult * atr_val
            else:
                tp_price = entry_price - tp_mult * atr_val
                sl_price = entry_price + sl_mult * atr_val

            # Walk bars to find exit
            exit_price = None; exit_bar = None
            for k in range(j+1, min(j + max_hold + 1, n)):
                if direction == 1:
                    if h[k] >= tp_price:
                        exit_price = tp_price; exit_bar = k; break
                    if l[k] <= sl_price:
                        exit_price = sl_price; exit_bar = k; break
                else:
                    if l[k] <= tp_price:
                        exit_price = tp_price; exit_bar = k; break
                    if h[k] >= sl_price:
                        exit_price = sl_price; exit_bar = k; break
            if exit_price is None:
                exit_bar = min(j + max_hold, n - 1)
                exit_price = c[exit_bar]

            pnl_raw = direction * (exit_price - entry_price)
            cost = cost_pct / 100.0 * entry_price
            pnl_net = pnl_raw - cost
            trades.append({
                'entry_dt': dt[j], 'exit_dt': dt[exit_bar],
                'direction': direction, 'entry': entry_price,
                'exit': exit_price, 'pnl_raw': pnl_raw,
                'cost': cost, 'pnl_net': pnl_net
            })
            i = exit_bar + 1
        else:
            i += 1
    return trades

# ── Metrics ──
def calc_metrics(trades_list):
    if len(trades_list) < 2:
        return None
    pnls = np.array([t['pnl_net'] for t in trades_list])
    n = len(pnls)
    wins = pnls > 0
    wr = wins.mean()
    ev = pnls.mean()
    std = pnls.std(ddof=1)
    sharpe = ev / std if std > 0 else 0
    avg_win = pnls[wins].mean() if wins.any() else 0
    avg_loss = pnls[~wins].mean() if (~wins).any() else 0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    gross_win = pnls[wins].sum() if wins.any() else 0
    gross_loss = abs(pnls[~wins].sum()) if (~wins).any() else 0
    pf = gross_win / gross_loss if gross_loss > 0 else 0
    # Max DD
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = dd.min()
    # Kelly
    kelly = (wr * payoff - (1 - wr)) / payoff if payoff > 0 else 0
    return {
        'n': n, 'wr': wr, 'ev': ev, 'std': std, 'sharpe': sharpe,
        'avg_win': avg_win, 'avg_loss': avg_loss, 'payoff': payoff,
        'pf': pf, 'max_dd': max_dd, 'kelly': kelly, 'pnls': pnls
    }

# ── IS/OOS split ──
is_end = pd.Timestamp('2025-03-31')
oos_start = pd.Timestamp('2025-04-01')

def split_trades(trades, is_end, oos_start):
    is_t = [t for t in trades if pd.Timestamp(t['entry_dt']) <= is_end]
    oos_t = [t for t in trades if pd.Timestamp(t['entry_dt']) >= oos_start]
    return is_t, oos_t

# ── Grid search ──
atr_periods = [10, 14, 20]
tp_mults = [1.5, 2.0, 3.0]
sl_mults = [0.75, 1.0, 1.5]
max_holds = [8, 10, 15]

results = []
print("Running grid search (81 combos × 2 cost models)...")
for atr_p, tp_m, sl_m, mh in product(atr_periods, tp_mults, sl_mults, max_holds):
    for cost_label, cost_pct in [('taker', 0.17), ('maker', 0.10)]:
        trades = run_backtest(df, atr_p, tp_m, sl_m, mh, cost_pct)
        is_t, oos_t = split_trades(trades, is_end, oos_start)
        is_m = calc_metrics(is_t)
        oos_m = calc_metrics(oos_t)
        results.append({
            'atr': atr_p, 'tp': tp_m, 'sl': sl_m, 'mh': mh,
            'cost': cost_label, 'is_m': is_m, 'oos_m': oos_m,
            'is_trades': is_t, 'oos_trades': oos_t
        })

# ── Filter OOS_n >= 10 and rank by OOS Sharpe ──
valid = [r for r in results if r['oos_m'] is not None and r['oos_m']['n'] >= 10]
valid.sort(key=lambda x: x['oos_m']['sharpe'], reverse=True)

print("\n" + "="*120)
print("TOP 10 PARAMETER SETS BY OOS SHARPE (OOS_n >= 10)")
print("="*120)
print(f"{'ATR':>4} | {'TP':>4} | {'SL':>4} | {'MH':>3} | {'Cost':>5} | "
      f"{'IS_n':>5} | {'IS_WR':>6} | {'IS_EV':>10} | {'IS_Sh':>7} | "
      f"{'OOS_n':>5} | {'OOS_WR':>6} | {'OOS_EV':>10} | {'OOS_Sh':>7}")
print("-"*120)
for r in valid[:10]:
    im = r['is_m']; om = r['oos_m']
    print(f"{r['atr']:>4} | {r['tp']:>4} | {r['sl']:>4} | {r['mh']:>3} | {r['cost']:>5} | "
          f"{im['n']:>5} | {im['wr']:>6.1%} | {im['ev']:>10.2f} | {im['sharpe']:>7.3f} | "
          f"{om['n']:>5} | {om['wr']:>6.1%} | {om['ev']:>10.2f} | {om['sharpe']:>7.3f}")

# ── Best config detailed analysis ──
best = valid[0]
bm = best['oos_m']
bt_is = best['is_m']
print("\n" + "="*80)
print(f"DETAILED ANALYSIS: BEST OOS CONFIG")
print(f"ATR={best['atr']} TP={best['tp']} SL={best['sl']} MH={best['mh']} Cost={best['cost']}")
print("="*80)

pnls = bm['pnls']
# t-test
t_stat, p_val = stats.ttest_1samp(pnls, 0)
print(f"\n[1] t-test OOS EV > 0:")
print(f"    t-stat = {t_stat:.4f}, p-value = {p_val:.4f}")

# Bootstrap CI
np.random.seed(42)
boot_means = []
for _ in range(5000):
    sample = np.random.choice(pnls, size=len(pnls), replace=True)
    boot_means.append(sample.mean())
ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])
print(f"\n[2] Bootstrap 95% CI for OOS EV:")
print(f"    [{ci_lo:.2f}, {ci_hi:.2f}]")

# Monthly breakdown
oos_trades = best['oos_trades']
monthly = {}
for t in oos_trades:
    m = pd.Timestamp(t['entry_dt']).strftime('%Y-%m')
    monthly.setdefault(m, []).append(t['pnl_net'])
print(f"\n[3] Monthly OOS breakdown:")
print(f"    {'Month':>9} | {'n':>4} | {'WR':>6} | {'Net EV':>10} | {'Cum P&L':>10}")
cum = 0
for m in sorted(monthly.keys()):
    mp = np.array(monthly[m])
    n = len(mp); wr = (mp > 0).mean(); ev = mp.sum()
    cum += ev
    print(f"    {m:>9} | {n:>4} | {wr:>6.1%} | {ev:>10.2f} | {cum:>10.2f}")

# Full metrics
print(f"\n[4] Full OOS metrics:")
print(f"    Win Rate:       {bm['wr']:.1%}")
print(f"    Avg Win:        {bm['avg_win']:.2f}")
print(f"    Avg Loss:       {bm['avg_loss']:.2f}")
print(f"    Payoff Ratio:   {bm['payoff']:.2f}")
print(f"    Profit Factor:  {bm['pf']:.3f}")
print(f"    Max Drawdown:   {bm['max_dd']:.2f}")
print(f"    Kelly Criterion:{bm['kelly']:.3f}")
print(f"    IS Sharpe:      {bt_is['sharpe']:.3f}")
print(f"    OOS Sharpe:     {bm['sharpe']:.3f}")

# ── Robustness: shifted splits ──
print("\n" + "="*80)
print("ROBUSTNESS CHECK: SHIFTED IS/OOS SPLITS")
print("="*80)
splits = [
    ('2025-02-01', '2025-02-01'),
    ('2025-04-01', '2025-04-01'),
    ('2025-05-01', '2025-05-01'),
]
all_positive = True
for is_end_str, oos_start_str in splits:
    ie = pd.Timestamp(is_end_str)
    os_ = pd.Timestamp(oos_start_str)
    trades = run_backtest(df, best['atr'], best['tp'], best['sl'], best['mh'],
                          0.17 if best['cost'] == 'taker' else 0.10)
    is_t, oos_t = split_trades(trades, ie, os_)
    om = calc_metrics(oos_t)
    if om is None or om['n'] < 5:
        print(f"  Split at {is_end_str}: OOS_n={0 if om is None else om['n']} (insufficient)")
        all_positive = False
    else:
        pos = "POSITIVE" if om['ev'] > 0 else "NEGATIVE"
        if om['ev'] <= 0: all_positive = False
        print(f"  Split at {is_end_str}: OOS_n={om['n']} WR={om['wr']:.1%} "
              f"EV={om['ev']:.2f} Sharpe={om['sharpe']:.3f} → {pos}")

# ── Final verdict ──
print("\n" + "="*80)
print("FINAL VERDICT")
print("="*80)
sig = "YES" if p_val < 0.05 else "NO"
robust = "YES" if all_positive else "NO"
monthly_ev = bm['ev'] * (len(oos_trades) / 27)  # ~27 months in OOS
acct = 190
monthly_pnl = monthly_ev * (acct / 100)  # scale: EV is in price terms, approximate as % of entry
# More accurate: avg EV as % of entry price
avg_entry = np.mean([t['entry'] for t in oos_trades])
ev_pct = bm['ev'] / avg_entry * 100
trades_per_month = len(oos_trades) / 27
monthly_pnl_dollar = ev_pct / 100 * acct * trades_per_month

print(f"  Statistical significance (p<0.05): {sig} (p={p_val:.4f})")
print(f"  Robust across splits:              {robust}")
print(f"  OOS trades/month:                   {trades_per_month:.1f}")
print(f"  OOS EV per trade:                   {bm['ev']:.2f} ({ev_pct:.3f}%)")
print(f"  Expected monthly P&L (${acct} acct):  ${monthly_pnl_dollar:.2f}")
print(f"  Expected annual P&L (${acct} acct):   ${monthly_pnl_dollar*12:.2f}")

if sig == "YES" and robust == "YES" and bm['sharpe'] > 0.5:
    rec = "IMPLEMENT"
elif sig == "YES" and bm['sharpe'] > 0.3:
    rec = "NEEDS MORE DATA"
else:
    rec = "REJECT"
print(f"\n  RECOMMENDATION: {rec}")
print("="*80)