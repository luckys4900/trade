import pandas as pd
import numpy as np
from backtesting import Backtest
from strategies.triple_top_breakout import TripleTopBreakout
import json
from datetime import datetime

def calc_ev(stats):
    trades = stats['_trades']
    if trades.empty:
        return None
    df = trades.copy()
    df['pnl_pct'] = df['PnL'] / df['EntryPrice'] * 100
    w = df[df['PnL'] > 0]
    l = df[df['PnL'] < 0]
    n = len(df)
    wr = len(w) / n * 100 if n > 0 else 0
    avg_w = w['pnl_pct'].mean() if len(w) > 0 else 0
    avg_l = l['pnl_pct'].mean() if len(l) > 0 else 0
    ev = (wr / 100 * avg_w) - ((100 - wr) / 100 * abs(avg_l))
    gp = w['PnL'].sum() if len(w) > 0 else 0
    gl = abs(l['PnL'].sum()) if len(l) > 0 else 0
    pf = gp / gl if gl > 0 else float('inf')
    return {
        'n': n, 'wins': len(w), 'losses': len(l),
        'win_rate': round(wr, 2),
        'avg_win_pct': round(avg_w, 4),
        'avg_loss_pct': round(avg_l, 4),
        'rr_ratio': round(abs(avg_w / avg_l), 2) if avg_l != 0 else 0,
        'ev_pct': round(ev, 4),
        'avg_trade_pct': round(df['pnl_pct'].mean(), 4),
        'pf': round(pf, 2),
        'gross_profit': round(gp, 2),
        'gross_loss': round(gl, 2),
        'max_win_pct': round(df['pnl_pct'].max(), 4),
        'max_loss_pct': round(df['pnl_pct'].min(), 4),
    }

def run_bt(df, params, label):
    print(f"\n{'='*70}")
    print(f" {label}")
    print(f" params: {params}")
    print(f"{'='*70}")
    bt = Backtest(df, TripleTopBreakout, cash=100000, commission=0.00045,
                  exclusive_orders=True, trade_on_close=False)
    stats = bt.run(**params)
    # Debug counts from strategy
    if hasattr(bt, '_strategy'):
        dc = bt._strategy._debug_counts if hasattr(bt._strategy, '_debug_counts') else {}
        if dc:
            print(f" DEBUG: pivots={dc.get('pivots',0)}, tt_ok={dc.get('tt_ok',0)}, near_ok={dc.get('near_ok',0)}, lr_ok={dc.get('lr_ok',0)}, vol_ok={dc.get('vol_ok',0)}, bb_ok={dc.get('bb_ok',0)}, regime_ok={dc.get('regime_ok',0)}, entries={dc.get('entries',0)}")
    ev = calc_ev(stats)
    print(f" trades: {stats['# Trades']}")
    if ev:
        print(f" win_rate:   {ev['win_rate']}%")
        print(f" EV:         {ev['ev_pct']}%")
        print(f" avg_trade:  {ev['avg_trade_pct']}%")
        print(f" PF:         {ev['pf']}")
        print(f" RR_ratio:   {ev['rr_ratio']}")
        print(f" total_ret:  {stats['Return [%]']:.2f}%")
        print(f" sharpe:     {stats['Sharpe Ratio']:.2f}")
        print(f" max_DD:     {stats['Max. Drawdown [%]']:.2f}%")
        print(f" avg_hold:   {stats['Avg. Trade Duration']}")
        print(f" max_win:    {ev['max_win_pct']}%")
        print(f" max_loss:   {ev['max_loss_pct']}%")
    else:
        print(" NO TRADES")
    return {'label': label, 'params': params, 'ev': ev,
            'return': stats['Return [%]'], 'sharpe': stats['Sharpe Ratio'],
            'max_dd': stats['Max. Drawdown [%]'], 'trades': stats['# Trades'],
            'win_rate': stats['Win Rate [%]'], 'avg_trade': stats['Avg. Trade [%]']}

def main():
    df = pd.read_csv('data/btc_price_4h_cache.csv', index_col=0)

    if 'datetime' in df.columns:
        df = df.set_index('datetime')
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    df = df[~df.index.duplicated(keep='first')].sort_index()

    cols = {c: c.capitalize() for c in df.columns}
    df = df.rename(columns=cols)

    end_date = df.index[-1]
    start_date = end_date - pd.Timedelta(days=720)
    df_720 = df[start_date:]

    print(f"full range : {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")
    print(f"720d range : {df_720.index[0]} -> {df_720.index[-1]} ({len(df_720)} bars)")

    # IS/OOS split (last 180 days = OOS)
    oos_start = end_date - pd.Timedelta(days=180)
    df_is = df_720[:oos_start]
    df_oos = df_720[oos_start:]
    print(f"IS  : {len(df_is)} bars")
    print(f"OOS : {len(df_oos)} bars")

    param_grid = [
        ('A: strict (Pine default)', {
            'pivot_length': 7, 'price_tolerance_pct': 1.5, 'min_high_count': 3,
            'volume_mult': 2.5, 'use_bb_filter': True, 'use_regime_filter': True,
            'sl_atr_mult': 2.5, 'tp_atr_mult': 4.0, 'max_hold_bars': 12,
        }),
        ('B: relaxed volume', {
            'pivot_length': 7, 'price_tolerance_pct': 1.5, 'min_high_count': 3,
            'volume_mult': 1.5, 'use_bb_filter': True, 'use_regime_filter': True,
            'sl_atr_mult': 2.5, 'tp_atr_mult': 4.0, 'max_hold_bars': 12,
        }),
        ('C: relaxed tolerance', {
            'pivot_length': 7, 'price_tolerance_pct': 2.5, 'min_high_count': 3,
            'volume_mult': 1.8, 'use_bb_filter': True, 'use_regime_filter': True,
            'sl_atr_mult': 2.5, 'tp_atr_mult': 4.0, 'max_hold_bars': 15,
        }),
        ('D: double-top no-lr', {
            'pivot_length': 5, 'price_tolerance_pct': 2.0, 'min_high_count': 2,
            'volume_mult': 1.5, 'use_bb_filter': True, 'use_regime_filter': False,
            'sl_atr_mult': 2.0, 'tp_atr_mult': 5.0, 'max_hold_bars': 15,
            'use_lows_rising_filter': False,
        }),
        ('E: no filters', {
            'pivot_length': 7, 'price_tolerance_pct': 2.0, 'min_high_count': 3,
            'volume_mult': 1.5, 'use_bb_filter': False, 'use_regime_filter': False,
            'sl_atr_mult': 2.0, 'tp_atr_mult': 4.0, 'max_hold_bars': 15,
        }),
        ('F: aggressive RR', {
            'pivot_length': 7, 'price_tolerance_pct': 2.0, 'min_high_count': 3,
            'volume_mult': 1.8, 'use_bb_filter': True, 'use_regime_filter': False,
            'sl_atr_mult': 1.5, 'tp_atr_mult': 6.0, 'max_hold_bars': 20,
        }),
    ]

    all_results = []

    print("\n" + "#"*70)
    print("# IS BACKTEST (first 540 days)")
    print("#"*70)
    for label, params in param_grid:
        r = run_bt(df_is, params, f"IS | {label}")
        all_results.append(r)

    print("\n" + "#"*70)
    print("# OOS BACKTEST (last 180 days)")
    print("#"*70)
    for label, params in param_grid:
        r = run_bt(df_oos, params, f"OOS | {label}")
        all_results.append(r)

    # Summary table
    print("\n\n" + "="*90)
    print(" EXPECTED VALUE SUMMARY")
    print("="*90)
    print(f"{'Label':35s} | {'N':>4s} | {'WR%':>6s} | {'EV%':>8s} | {'PF':>6s} | {'RR':>5s} | {'Ret%':>8s} | {'Sharpe':>7s} | {'DD%':>7s}")
    print("-"*90)
    for r in all_results:
        if r['ev']:
            e = r['ev']
            print(f"{r['label']:35s} | {e['n']:4d} | {e['win_rate']:6.2f} | {e['ev_pct']:8.4f} | {e['pf']:6.2f} | {e['rr_ratio']:5.2f} | {r['return']:8.2f} | {r['sharpe']:7.2f} | {r['max_dd']:7.2f}")
        else:
            print(f"{r['label']:35s} |    0 |     - |        - |      - |     - | {r['return']:8.2f} | {r['sharpe']:7.2f} | {r['max_dd']:7.2f}")

    # Filter positive EV
    positive_ev = [r for r in all_results if r['ev'] and r['ev']['ev_pct'] > 0]
    print(f"\n positive EV strategies: {len(positive_ev)}/{len(all_results)}")
    for r in positive_ev:
        e = r['ev']
        print(f"  {r['label']}: EV={e['ev_pct']}%, WR={e['win_rate']}%, PF={e['pf']}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f'triple_top_4h_ev_{ts}.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n saved to {out_file}")

if __name__ == "__main__":
    main()
