import pandas as pd, numpy as np
from backtesting import Backtest
from strategies.triple_top_breakout import TripleTopBreakout

df = pd.read_csv('data/btc_price_4h_cache.csv', index_col=0)
df.index = pd.to_datetime(df.index, utc=True)
df = df.dropna(subset=['open','high','low','close']).sort_index()
df.columns = [c.capitalize() for c in df.columns]
end = df.index[-1]
df720 = df[end - pd.Timedelta(days=720):]

bt = Backtest(df720, TripleTopBreakout, cash=100000, commission=0.00045, exclusive_orders=True)
stats = bt.run(
    pivot_length=7, price_tolerance_pct=2.0, min_high_count=3,
    volume_mult=1.5, use_bb_filter=True, use_regime_filter=False,
    sl_atr_mult=2.0, tp_atr_mult=4.0, max_hold_bars=15,
    use_lows_rising_filter=False,
)
dc = bt._strategy._debug_counts
print(f"trades: {stats['# Trades']}")
print(f"debug: {dc}")
if stats['# Trades'] > 0:
    print(f"return: {stats['Return [%]']:.2f}%")
    print(f"win_rate: {stats['Win Rate [%]']:.2f}%")
    print(f"sharpe: {stats['Sharpe Ratio']:.2f}")
    t = stats['_trades']
    t['pnl_pct'] = t['PnL'] / t['EntryPrice'] * 100
    print(f"avg_trade: {t['pnl_pct'].mean():.4f}%")
    print(f"ev: {t['pnl_pct'].mean():.4f}%")
