import pandas as pd
from backtesting import Backtest
from strategies.triple_top_breakout import TripleTopBreakout
import json
from datetime import datetime

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

    bt = Backtest(
        df,
        TripleTopBreakout,
        cash=10000,
        commission=0.00045,
        exclusive_orders=True,
        trade_on_close=False
    )

    print("バックテスト実行中...")
    stats = bt.run()

    if stats['# Trades'] == 0:
        print("\nトレードが生成されませんでした。条件を緩和して再実行します...")

        bt2 = Backtest(
            df,
            TripleTopBreakout,
            cash=10000,
            commission=0.00045,
            exclusive_orders=True,
            trade_on_close=False
        )
        stats = bt2.run(
            price_tolerance_pct=3.0,
            min_high_count=2,
            volume_mult=1.8,
            sl_atr_mult=2.0,
            tp_atr_mult=5.0
        )
        print(f"再実行後のトレード数: {stats['# Trades']}")

    ev_metrics = calculate_ev_metrics(stats)

    print("\n" + "=" * 80)
    print("トリプルトップブレイクアウト戦略 - 期待値分析")
    print("=" * 80)

    if ev_metrics:
        for key, value in ev_metrics.items():
            print(f"{key:20s}: {value}")

        print("\n" + "=" * 80)
        print("主要パフォーマンス指標（backtesting.py標準）")
        print("=" * 80)
        print(f"総リターン            : {stats['Return [%]']:.2f}%")
        print(f"年間リターン          : {stats['Return (Ann.) [%]']:.2f}%")
        print(f"シャープレシオ        : {stats['Sharpe Ratio']:.2f}")
        print(f"最大ドローダウン      : {stats['Max. Drawdown [%]']:.2f}%")
        print(f"平均保有時間          : {stats['Avg. Trade Duration']}")

        results = {
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
            'parameters': {
                'pivot_length': 7,
                'price_tolerance_pct': 1.5,
                'min_high_count': 3,
                'bb_period': 20,
                'bb_std': 1.8,
                'atr_period': 14,
                'sl_atr_mult': 2.5,
                'tp_atr_mult': 4.0,
                'max_hold_bars': 15,
                'volume_mult': 2.5,
                'risk_per_trade': 0.02,
            }
        }

        output_file = f'triple_top_ev_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n結果は {output_file} に保存されました")

        bt.plot(filename='./backtest_results/triple_top_ev_analysis.html', open_browser=False)
        print("チャート: backtest_results/triple_top_ev_analysis.html")
    else:
        print("トレードが生成されませんでした")

if __name__ == "__main__":
    main()
