import pandas as pd
from backtesting import Backtest, Strategy
import talib
import json
from datetime import datetime

class SimpleTripleTopBreakout(Strategy):
    """
    簡易版トリプルトップブレイクアウト戦略
    TA-Libのピボット機能を使用せず、ローカル高値/安値を簡易検出
    """
    bb_period = 20
    bb_std = 2.0
    atr_period = 14
    volume_mult = 2.0
    sl_atr_mult = 2.5
    tp_atr_mult = 4.0
    max_hold_bars = 15
    risk_per_trade = 0.02
    use_volume_filter = True
    use_bb_filter = True

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume

        self.atr = self.I(talib.ATR, high, low, close, self.atr_period)
        
        bb_upper, bb_middle, bb_lower = talib.BBANDS(
            close, timeperiod=self.bb_period,
            nbdevup=self.bb_std, nbdevdn=self.bb_std, matype=0
        )
        self.bb_upper = self.I(lambda: bb_upper)
        self.bb_middle = self.I(lambda: bb_middle)
        self.bb_lower = self.I(lambda: bb_lower)
        self.vol_sma = self.I(talib.SMA, volume, 20)
        
        self._highs = []
        self._lows = []
        self._bar_count = 0

    def next(self):
        self._bar_count += 1
        
        high = self.data.High[-1]
        low = self.data.Low[-1]
        
        self._highs.append(high)
        self._lows.append(low)
        
        if len(self._highs) > 50:
            self._highs.pop(0)
            self._lows.pop(0)

        if self.position:
            if self._entry_bar is not None:
                held = self._bar_count - self._entry_bar
                if held >= self.max_hold_bars:
                    self.position.close()
                    self._entry_bar = None
                    return
            return

        if len(self.data.Close) < max(self.atr_period, self.bb_period) + 10:
            return

        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        close = self.data.Close[-1]
        volume_current = self.data.Volume[-1]
        vol_avg = self.vol_sma[-1] if len(self.vol_sma) > 0 else 0

        volume_ok = not self.use_volume_filter or (vol_avg > 0 and volume_current > vol_avg * self.volume_mult)
        bb_ok = not self.use_bb_filter or (close > self.bb_upper[-1])

        if not volume_ok or not bb_ok:
            return

        recent_highs = sorted(self._highs[-10:], reverse=True)[:3]
        if len(recent_highs) < 3:
            return

        avg_high = sum(recent_highs) / len(recent_highs)
        price_range = (max(recent_highs) - min(recent_highs)) / avg_high
        
        near_high_band = (close >= avg_high * 0.99) and (close <= avg_high * 1.01)
        price_band_valid = price_range <= 0.03

        if not (near_high_band and price_band_valid):
            return

        recent_lows = sorted(self._lows[-10:])
        lows_rising = len(recent_lows) >= 2 and recent_lows[-1] > recent_lows[-2]

        if not lows_rising:
            return

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult

        risk_dist = close - sl
        if risk_dist <= 0:
            return

        risk_amount = self.equity * self.risk_per_trade
        size = risk_amount / risk_dist
        if size <= 0:
            return

        self.buy(size=size, sl=sl, tp=tp)
        self._entry_bar = self._bar_count

def calculate_ev_metrics(stats):
    trades = stats['_trades']
    if trades.empty:
        return None

    trades_df = trades.copy()
    trades_df['pnl_pct'] = trades_df['PnL'] / trades_df['EntryPrice'] * 100

    winning_trades = trades_df[trades_df['PnL'] > 0]
    losing_trades = trades_df[trades_df['PnL'] < 0]

    total_trades = len(trades_df)
    winning_count = len(winning_trades)
    losing_count = len(losing_trades)
    win_rate = winning_count / total_trades * 100 if total_trades > 0 else 0

    avg_win = winning_trades['pnl_pct'].mean() if winning_count > 0 else 0
    avg_loss = losing_trades['pnl_pct'].mean() if losing_count > 0 else 0

    ev = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * abs(avg_loss))
    avg_trade = trades_df['pnl_pct'].mean()

    gross_profit = winning_trades['PnL'].sum() if winning_count > 0 else 0
    gross_loss = abs(losing_trades['PnL'].sum()) if losing_count > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    return {
        '総トレード数': total_trades,
        '勝率 [%]': round(win_rate, 2),
        '勝ちトレード数': winning_count,
        '負けトレード数': losing_count,
        '平均勝ち [%]': round(avg_win, 4),
        '平均負け [%]': round(avg_loss, 4),
        'リスクリワード比': round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
        '期待値 EV [%]': round(ev, 4),
        '平均トレード [%]': round(avg_trade, 4),
        'プロフィットファクター': round(profit_factor, 2),
        '総利益': round(gross_profit, 4),
        '総損失': round(gross_loss, 4),
    }

def main():
    data_path = './data/raw/BTC_5m_hyperliquid.csv'
    
    df = pd.read_csv(data_path, index_col=0, parse_dates=True)
    df.columns = [col.capitalize() for col in df.columns]

    print(f"データ期間: {df.index[0]} 〜 {df.index[-1]}")
    print(f"データ数: {len(df):,} 本\n")

    param_sets = [
        {'name': '緩和設定', 'params': {'volume_mult': 1.5, 'use_bb_filter': True, 'use_volume_filter': True, 'sl_atr_mult': 2.0, 'tp_atr_mult': 4.0}},
        {'name': '標準設定', 'params': {'volume_mult': 2.0, 'use_bb_filter': True, 'use_volume_filter': True, 'sl_atr_mult': 2.5, 'tp_atr_mult': 4.0}},
        {'name': '厳格設定', 'params': {'volume_mult': 2.5, 'use_bb_filter': True, 'use_volume_filter': True, 'sl_atr_mult': 2.5, 'tp_atr_mult': 4.0}},
    ]

    results = []

    for param_set in param_sets:
        print(f"\n{'='*80}")
        print(f"パラメータセット: {param_set['name']}")
        print(f"{'='*80}")

        bt = Backtest(
            df,
            SimpleTripleTopBreakout,
            cash=10000,
            commission=0.00045,
            exclusive_orders=True,
            trade_on_close=False
        )

        print(f"バックテスト実行中... パラメータ: {param_set['params']}")
        stats = bt.run(**param_set['params'])

        print(f"トレード数: {stats['# Trades']}")
        
        ev_metrics = calculate_ev_metrics(stats)
        
        if ev_metrics:
            print("\n期待値分析結果:")
            for key, value in ev_metrics.items():
                print(f"  {key:20s}: {value}")

            print("\n主要パフォーマンス指標:")
            print(f"  総リターン: {stats['Return [%]']:.2f}%")
            print(f"  年間リターン: {stats['Return (Ann.) [%]']:.2f}%")
            print(f"  シャープレシオ: {stats['Sharpe Ratio']:.2f}")
            print(f"  最大ドローダウン: {stats['Max. Drawdown [%]']:.2f}%")

            results.append({
                'parameter_set': param_set['name'],
                'params': param_set['params'],
                'backtest_summary': {
                    'total_return': stats['Return [%]'],
                    'annual_return': stats['Return (Ann.) [%]'],
                    'sharpe_ratio': stats['Sharpe Ratio'],
                    'max_drawdown': stats['Max. Drawdown [%]'],
                    'win_rate': stats['Win Rate [%]'],
                    'num_trades': stats['# Trades'],
                    'avg_trade': stats['Avg. Trade [%]'],
                    'profit_factor': stats.get('Profit Factor', 'N/A'),
                },
                'ev_metrics': ev_metrics,
            })
        else:
            print("トレードが生成されませんでした")

    output_file = f'triple_top_ev_simple_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n\n結果は {output_file} に保存されました")

    if results:
        print("\n\n" + "="*80)
        print("期待値リスト")
        print("="*80)
        for r in results:
            ev = r['ev_metrics']
            print(f"\n{r['parameter_set']}:")
            print(f"  トレード数: {ev['総トレード数']}")
            print(f"  勝率: {ev['勝率 [%]']}%")
            print(f"  期待値 EV: {ev['期待値 EV [%]']}%")
            print(f"  プロフィットファクター: {ev['プロフィットファクター']}")

if __name__ == "__main__":
    main()
