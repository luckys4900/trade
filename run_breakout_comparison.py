import pandas as pd
import numpy as np
from backtesting import Backtest
from strategies.resistance_breakout_v1 import ResistanceClusterBreakout
from strategies.ascending_triangle_v2 import AscendingTriangleBreakout
from strategies.confluence_breakout_v3 import ConfluenceBreakout
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
    return {'n': n, 'wins': len(w), 'losses': len(l), 'wr': round(wr, 2),
            'avg_w': round(avg_w, 4), 'avg_l': round(avg_l, 4),
            'rr': round(abs(avg_w / avg_l), 2) if avg_l != 0 else 0,
            'ev': round(ev, 4), 'avg_t': round(df['pnl_pct'].mean(), 4),
            'pf': round(pf, 2), 'max_w': round(df['pnl_pct'].max(), 4),
            'max_l': round(df['pnl_pct'].min(), 4)}

def run(df, cls, params, label):
    bt = Backtest(df, cls, cash=100000, commission=0.00045,
                  exclusive_orders=True, trade_on_close=False)
    stats = bt.run(**params)
    ev = calc_ev(stats)
    r = {'label': label, 'params': params, 'ev': ev,
         'ret': round(stats['Return [%]'], 2), 'sharpe': round(stats['Sharpe Ratio'], 2) if stats['Sharpe Ratio'] == stats['Sharpe Ratio'] else 'nan',
         'dd': round(stats['Max. Drawdown [%]'], 2), 'n': stats['# Trades'],
         'wr': round(stats['Win Rate [%]'], 2), 'avg_t': round(stats['Avg. Trade [%]'], 4)}
    ev_s = f"EV={ev['ev']}% WR={ev['wr']}% PF={ev['pf']}" if ev else "NO TRADES"
    print(f"  {label:40s} | N={r['n']:3d} | {ev_s}")
    return r

def main():
    df = pd.read_csv('data/btc_price_4h_cache.csv')
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
    df = df.set_index('datetime').sort_index()
    df = df.dropna(subset=['open','high','low','close'])
    df = df.rename(columns={c: c.capitalize() for c in df.columns})
    df = df[~df.index.duplicated(keep='first')]

    end = df.index[-1]
    start_720 = end - pd.Timedelta(days=720)
    df720 = df[start_720:]
    oos_start = end - pd.Timedelta(days=180)
    df_is = df720[df720.index < oos_start]
    df_oos = df720[df720.index >= oos_start]

    if len(df_is) == 0 or len(df_oos) == 0:
        print(f"WARNING: empty split! df720={len(df720)} df_is={len(df_is)} df_oos={len(df_oos)}")
        print(f"end={end} start_720={start_720} oos_start={oos_start}")
        return

    print(f"IS  : {len(df_is)} bars ({df_is.index[0].date()} -> {df_is.index[-1].date()})")
    print(f"OOS : {len(df_oos)} bars ({df_oos.index[0].date()} -> {df_oos.index[-1].date()})")

    configs = [
        ('V1 Resistance Cluster', ResistanceClusterBreakout, [
            {'sl_atr_mult': 2.0, 'tp_atr_mult': 4.0, 'pivot_length': 5, 'price_tolerance_pct': 2.0, 'max_hold_bars': 15},
            {'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'pivot_length': 5, 'price_tolerance_pct': 2.5, 'max_hold_bars': 18},
            {'sl_atr_mult': 1.5, 'tp_atr_mult': 4.5, 'pivot_length': 5, 'price_tolerance_pct': 3.0, 'max_hold_bars': 15},
            {'sl_atr_mult': 2.5, 'tp_atr_mult': 5.0, 'pivot_length': 7, 'price_tolerance_pct': 2.0, 'max_hold_bars': 12},
        ]),
        ('V2 Ascending Triangle', AscendingTriangleBreakout, [
            {'sl_atr_mult': 1.5, 'tp_atr_mult': 3.5, 'pivot_length': 5, 'price_tolerance_pct': 1.5, 'max_hold_bars': 12},
            {'sl_atr_mult': 2.0, 'tp_atr_mult': 4.0, 'pivot_length': 5, 'price_tolerance_pct': 2.0, 'max_hold_bars': 15},
            {'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'pivot_length': 7, 'price_tolerance_pct': 2.0, 'max_hold_bars': 15},
        ]),
        ('V3 Confluence', ConfluenceBreakout, [
            {'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'resistance_lookback': 50, 'rsi_threshold': 50, 'max_hold_bars': 18},
            {'sl_atr_mult': 2.0, 'tp_atr_mult': 4.0, 'resistance_lookback': 40, 'rsi_threshold': 45, 'max_hold_bars': 15},
            {'sl_atr_mult': 1.5, 'tp_atr_mult': 4.5, 'resistance_lookback': 60, 'rsi_threshold': 55, 'max_hold_bars': 20},
            {'sl_atr_mult': 2.5, 'tp_atr_mult': 6.0, 'resistance_lookback': 50, 'rsi_threshold': 50, 'min_touches': 3, 'max_hold_bars': 18},
        ]),
    ]

    all_r = []
    for period_name, df_period in [('IS', df_is), ('OOS', df_oos)]:
        print(f"\n{'#'*70}")
        print(f"# {period_name} BACKTEST")
        print(f"{'#'*70}")
        for strat_name, cls, param_list in configs:
            print(f"\n  --- {strat_name} ---")
            for i, params in enumerate(param_list):
                label = f"{period_name} | {strat_name} P{i+1}"
                r = run(df_period, cls, params, label)
                all_r.append(r)

    print(f"\n\n{'='*100}")
    print(" EXPECTED VALUE COMPARISON (sorted by EV)")
    print(f"{'='*100}")
    tradeable = [r for r in all_r if r['ev'] and r['n'] > 0]
    tradeable.sort(key=lambda x: x['ev']['ev'], reverse=True)
    print(f"{'Label':50s} | {'N':>3s} | {'WR%':>6s} | {'EV%':>8s} | {'PF':>6s} | {'RR':>5s} | {'Ret%':>7s} | {'Sharpe':>6s} | {'DD%':>7s}")
    print("-"*100)
    for r in tradeable:
        e = r['ev']
        s = str(r['sharpe'])
        print(f"{r['label']:50s} | {e['n']:3d} | {e['wr']:6.2f} | {e['ev']:8.4f} | {e['pf']:6.2f} | {e['rr']:5.2f} | {r['ret']:7.2f} | {s:>6s} | {r['dd']:7.2f}")

    print(f"\n\n{'='*100}")
    print(" IS/OOS CONSISTENCY CHECK (same param set, both periods)")
    print(f"{'='*100}")
    is_results = {r['label'].replace('IS | ', ''): r for r in all_r if r['label'].startswith('IS')}
    oos_results = {r['label'].replace('OOS | ', ''): r for r in all_r if r['label'].startswith('OOS')}
    for key in is_results:
        if key in oos_results:
            ir = is_results[key]
            orr = oos_results[key]
            is_ev = ir['ev']['ev'] if ir['ev'] else 'N/A'
            oos_ev = orr['ev']['ev'] if orr['ev'] else 'N/A'
            is_n = ir['n']
            oos_n = orr['n']
            verdict = ""
            if isinstance(is_ev, (int, float)) and isinstance(oos_ev, (int, float)):
                if is_ev > 0 and oos_ev > 0:
                    verdict = "** ROBUST **"
                elif is_ev > 0 and oos_ev <= 0:
                    verdict = "IS only (OOS fail)"
                else:
                    verdict = "No edge"
            print(f"  {key:45s} | IS EV={str(is_ev):>8s} (n={is_n:3d}) | OOS EV={str(oos_ev):>8s} (n={oos_n:3d}) | {verdict}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f'breakout_3variants_{ts}.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(all_r, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n saved to {out}")

if __name__ == "__main__":
    main()
