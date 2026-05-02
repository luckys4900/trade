import pandas as pd
import numpy as np
import itertools
import multiprocessing as mp
from backtesting import Backtest
from strategies.vsrev_enhanced import VSRevEnhanced, VSRevMultiConfirm, VSRevAdaptive
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def calc_ev(stats):
    trades = stats['_trades']
    if trades.empty:
        return None
    df = trades.copy()
    df['pnl_pct'] = df['PnL'] / df['EntryPrice'] * 100
    w = df[df['PnL'] > 0]
    l = df[df['PnL'] < 0]
    n = len(df)
    wr = len(w) / n * 100
    avg_w = w['pnl_pct'].mean() if len(w) > 0 else 0
    avg_l = l['pnl_pct'].mean() if len(l) > 0 else 0
    ev = (wr / 100 * avg_w) - ((100 - wr) / 100 * abs(avg_l))
    gp = w['PnL'].sum() if len(w) > 0 else 0
    gl = abs(l['PnL'].sum()) if len(l) > 0 else 0
    pf = gp / gl if gl > 0 else float('inf')
    med = df['pnl_pct'].median()
    return {'n': n, 'wins': len(w), 'losses': len(l), 'wr': round(wr, 2),
            'avg_w': round(avg_w, 4), 'avg_l': round(avg_l, 4),
            'rr': round(abs(avg_w / avg_l), 2) if avg_l != 0 else 0,
            'ev': round(ev, 4), 'ev_med': round(med, 4),
            'pf': round(pf, 2), 'max_w': round(df['pnl_pct'].max(), 4),
            'max_l': round(df['pnl_pct'].min(), 4)}

def run(df, cls, params, label):
    bt = Backtest(df, cls, cash=100000, commission=0.00045,
                  exclusive_orders=True, trade_on_close=False)
    stats = bt.run(**params)
    ev = calc_ev(stats)
    sr = stats['Sharpe Ratio']
    sr = round(sr, 2) if sr == sr else 'nan'
    r = {'label': label, 'params': params, 'ev': ev,
         'ret': round(stats['Return [%]'], 2), 'sharpe': sr,
         'dd': round(stats['Max. Drawdown [%]'], 2), 'n': stats['# Trades'],
         'wr': round(stats['Win Rate [%]'], 2), 'avg_t': round(stats['Avg. Trade [%]'], 4)}
    if ev:
        print(f"  {label:55s} | N={ev['n']:3d} WR={ev['wr']:5.1f}% EV={ev['ev']:7.4f}% PF={ev['pf']:5.2f} RR={ev['rr']:4.2f} Ret={r['ret']:7.2f}% SR={sr} DD={r['dd']:6.2f}%")
    else:
        print(f"  {label:55s} | NO TRADES")
    return r

# Helper for multiprocessing – accepts a tuple of arguments
def run_task(args):
    df, cls, params, label = args
    return run(df, cls, params, label)

def generate_multiconfirm_grid():
    """Generate parameter grid for VSRevMultiConfirm.
    Returns a list of dicts with combinations of:
    - vol_ratio_threshold: [1.5, 1.8, 2.0, 2.2]
    - rsi_long_threshold: [25, 30, 35]
    - rsi_short_threshold: [65, 70, 75]
    - tp_atr_mult: [4.5, 5.0, 5.5]
    - max_hold_bars: [6, 8, 10]
    """
    vol_ratios = [1.5, 1.8, 2.0, 2.2]
    rsi_long_vals = [25, 30, 35]
    rsi_short_vals = [65, 70, 75]
    tp_atr_vals = [4.5, 5.0, 5.5]
    max_hold_vals = [6, 8, 10]
    grid = []
    for vr, rl, rs, tp, mh in itertools.product(vol_ratios, rsi_long_vals, rsi_short_vals, tp_atr_vals, max_hold_vals):
        params = {
            'vol_ratio_threshold': vr,
            'rsi_long_threshold': float(rl),
            'rsi_short_threshold': float(rs),
            'sl_atr_mult': 2.0,
            'tp_atr_mult': tp,
            'max_hold_bars': mh,
            'require_bb_touch': True,
        }
        grid.append(params)
    return grid

def main():
    df = pd.read_csv('data/btc_price_4h_cache.csv')
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
    df = df.set_index('datetime').sort_index()
    df = df.dropna(subset=['open','high','low','close'])
    df = df.rename(columns={c: c.capitalize() for c in df.columns})
    df = df[~df.index.duplicated(keep='first')]

    end = df.index[-1]
    df720 = df[end - pd.Timedelta(days=720):]
    oos_start = end - pd.Timedelta(days=180)
    df_is = df720[df720.index < oos_start]
    df_oos = df720[df720.index >= oos_start]
    df_full = df720

    print(f"IS   : {len(df_is)} bars ({df_is.index[0].date()} -> {df_is.index[-1].date()})")
    print(f"OOS  : {len(df_oos)} bars ({df_oos.index[0].date()} -> {df_oos.index[-1].date()})")
    print(f"FULL : {len(df_full)} bars")

    configs = [
        ('BASELINE VSRev (current)', VSRevEnhanced, [
            {'vol_ratio_threshold': 2.0, 'rsi_long_threshold': 25.0, 'rsi_short_threshold': 80.0,
             'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'max_hold_bars': 6, 'use_bb_squeeze': False},
        ]),
        ('V1 VSRev+BB Squeeze', VSRevEnhanced, [
            {'vol_ratio_threshold': 2.0, 'rsi_long_threshold': 25.0, 'rsi_short_threshold': 80.0,
             'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'max_hold_bars': 6, 'use_bb_squeeze': True, 'bb_squeeze_lookback': 10},
            {'vol_ratio_threshold': 2.0, 'rsi_long_threshold': 25.0, 'rsi_short_threshold': 80.0,
             'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'max_hold_bars': 8, 'use_bb_squeeze': True, 'bb_squeeze_lookback': 15},
        ]),
        ('V2 VSRev MultiConfirm', VSRevMultiConfirm, generate_multiconfirm_grid()),
        ('V3 VSRev Adaptive', VSRevAdaptive, [
            {'vol_ratio_threshold': 2.0, 'rsi_long_threshold': 25.0, 'rsi_short_threshold': 80.0,
             'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'max_hold_bars': 6, 'min_vol_pct': 40, 'max_vol_pct': 95, 'use_trend_filter': False},
            {'vol_ratio_threshold': 2.0, 'rsi_long_threshold': 25.0, 'rsi_short_threshold': 80.0,
             'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'max_hold_bars': 6, 'min_vol_pct': 50, 'max_vol_pct': 90, 'use_trend_filter': True},
            {'vol_ratio_threshold': 2.0, 'rsi_long_threshold': 25.0, 'rsi_short_threshold': 80.0,
             'sl_atr_mult': 2.0, 'tp_atr_mult': 4.0, 'max_hold_bars': 8, 'min_vol_pct': 30, 'max_vol_pct': 95, 'use_trend_filter': False},
            {'vol_ratio_threshold': 1.8, 'rsi_long_threshold': 30.0, 'rsi_short_threshold': 70.0,
             'sl_atr_mult': 1.5, 'tp_atr_mult': 5.0, 'max_hold_bars': 8, 'min_vol_pct': 35, 'max_vol_pct': 90, 'use_trend_filter': False},
        ]),
    ]

    all_r = []
    for period_name, df_period in [('IS', df_is), ('OOS', df_oos), ('FULL', df_full)]:
        print(f"\n{'#'*80}")
        print(f"# {period_name} ({len(df_period)} bars)")
        print(f"{'#'*80}")
        for strat_name, cls, param_list in configs:
            print(f"\n  --- {strat_name} ---")
            if strat_name == 'V2 VSRev MultiConfirm':
                # Parallel execution for the large grid
                tasks = []
                for i, params in enumerate(param_list):
                    label = f"{period_name} | {strat_name} P{i+1}"
                    tasks.append((df_period, cls, params, label))
                with mp.Pool() as pool:
                    results = pool.map(run_task, tasks)
                all_r.extend(results)
            else:
                for i, params in enumerate(param_list):
                    label = f"{period_name} | {strat_name} P{i+1}"
                    r = run(df_period, cls, params, label)
                    all_r.append(r)

    print(f"\n\n{'='*110}")
    print(" EXPECTED VALUE RANKING (positive EV only, sorted by EV)")
    print(f"{'='*110}")
    pos = [r for r in all_r if r['ev'] and r['ev']['ev'] > 0]
    pos.sort(key=lambda x: x['ev']['ev'], reverse=True)
    print(f"{'Label':55s} | {'N':>3s} | {'WR%':>5s} | {'EV%':>7s} | {'Med%':>6s} | {'PF':>5s} | {'RR':>4s} | {'Ret%':>7s} | {'SR':>5s} | {'DD%':>6s}")
    print("-"*110)
    for r in pos:
        e = r['ev']
        s = str(r['sharpe'])
        print(f"{r['label']:55s} | {e['n']:3d} | {e['wr']:5.1f} | {e['ev']:7.4f} | {e['ev_med']:6.4f} | {e['pf']:5.2f} | {e['rr']:4.2f} | {r['ret']:7.2f} | {s:>5s} | {r['dd']:6.2f}")

    print(f"\n\n{'='*110}")
    print(" IS/OOS/FULL CONSISTENCY CHECK")
    print(f"{'='*110}")
    is_r = {r['label'].replace('IS | ', ''): r for r in all_r if r['label'].startswith('IS')}
    oos_r = {r['label'].replace('OOS | ', ''): r for r in all_r if r['label'].startswith('OOS')}
    full_r = {r['label'].replace('FULL | ', ''): r for r in all_r if r['label'].startswith('FULL')}
    for key in is_r:
        ir = is_r[key]
        orr = oos_r.get(key)
        fr = full_r.get(key)
        is_ev = ir['ev']['ev'] if ir['ev'] else 'N/A'
        oos_ev = orr['ev']['ev'] if orr and orr['ev'] else 'N/A'
        full_ev = fr['ev']['ev'] if fr and fr['ev'] else 'N/A'
        is_n = ir['n']
        oos_n = orr['n'] if orr else 0
        full_n = fr['n'] if fr else 0
        v = ""
        if isinstance(is_ev, (int, float)) and isinstance(oos_ev, (int, float)):
            if is_ev > 0 and oos_ev > 0:
                v = "*** ROBUST ***"
            elif is_ev > 0 and oos_ev > is_ev * -0.5:
                v = "Marginal (IS+/OOS weak)"
            elif is_ev > 0:
                v = "IS only (OOS fail)"
        print(f"  {key:55s} | IS={str(is_ev):>7s}({is_n:3d}) OOS={str(oos_ev):>7s}({oos_n:3d}) FULL={str(full_ev):>7s}({full_n:3d}) | {v}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f'vsrev_enhanced_{ts}.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(all_r, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n saved to {out}")

if __name__ == "__main__":
    main()
