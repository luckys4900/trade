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

def run_backtest(data_path, timeframe_name, params):
    print(f"\n{'='*80}")
    print(f"{timeframe_name}データでのバックテスト")
    print(f"{'='*80}")

    df = pd.read_csv(data_path, index_col=0, parse_dates=True)
    df.columns = [col.capitalize() for col in df.columns]

    print(f"データ期間: {df.index[0]} 〜 {df.index[-1]}")
    print(f"データ数: {len(df):,} 本")
    print(f"パラメータ: {params}\n")

    bt = Backtest(
        df,
        TripleTopBreakout,
        cash=10000,
        commission=0.00045,
        exclusive_orders=True,
        trade_on_close=False
    )

    print("バックテスト実行中...")
    stats = bt.run(**params)

    print(f"トレード数: {stats['# Trades']}")

    ev_metrics = calculate_ev_metrics(stats)

    if ev_metrics:
        print("\n" + "=" * 80)
        print("期待値分析結果")
        print("=" * 80)
        for key, value in ev_metrics.items():
            print(f"{key:20s}: {value}")

        print("\n" + "=" * 80)
        print("主要パフォーマンス指標")
        print("=" * 80)
        print(f"総リターン            : {stats['Return [%]']:.2f}%")
        print(f"年間リターン          : {stats['Return (Ann.) [%]']:.2f}%")
        print(f"シャープレシオ        : {stats['Sharpe Ratio']:.2f}")
        print(f"最大ドローダウン      : {stats['Max. Drawdown [%]']:.2f}%")
        print(f"平均保有時間          : {stats['Avg. Trade Duration']}")

        return {
            'timeframe': timeframe_name,
            'params': params,
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
        }
    else:
        print("トレードが生成されませんでした")
        return None

def main():
    param_sets = [
        {
            'name': '極めて緩和',
            'params': {
                'min_high_count': 1,
                'price_tolerance_pct': 5.0,
                'volume_mult': 1.5,
                'use_volume_filter': False,
                'use_bb_filter': False,
                'use_regime_filter': False,
                'sl_atr_mult': 2.0,
                'tp_atr_mult': 4.0,
                'max_hold_bars': 30,
            }
        },
        {
            'name': '緩和',
            'params': {
                'min_high_count': 2,
                'price_tolerance_pct': 3.0,
                'volume_mult': 1.5,
                'use_volume_filter': True,
                'use_bb_filter': False,
                'use_regime_filter': False,
                'sl_atr_mult': 2.0,
                'tp_atr_mult': 4.0,
                'max_hold_bars': 20,
            }
        },
        {
            'name': '標準',
            'params': {
                'min_high_count': 3,
                'price_tolerance_pct': 1.5,
                'volume_mult': 2.5,
                'use_volume_filter': True,
                'use_bb_filter': True,
                'use_regime_filter': True,
                'sl_atr_mult': 2.5,
                'tp_atr_mult': 4.0,
                'max_hold_bars': 15,
            }
        },
    ]

    results = []

    data_files = [
        ('./data/raw/BTC_5m_hyperliquid.csv', '5分足'),
    ]

    for data_path, tf_name in data_files:
        if not pd.io.common.file_exists(data_path):
            print(f"データファイルが見つかりません: {data_path}")
            continue

        for param_set in param_sets:
            result = run_backtest(data_path, f"{tf_name} - {param_set['name']}", param_set['params'])
            if result:
                results.append(result)

    output_file = f'triple_top_ev_relaxed_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n\n全結果は {output_file} に保存されました")

    if results:
        print("\n\n" + "=" * 80)
        print("全パラメータセットの比較")
        print("=" * 80)
        for r in results:
            ev = r['ev_metrics']
            print(f"\n{r['timeframe']}:")
            print(f"  トレード数: {ev['総トレード数']}")
            print(f"  勝率: {ev['勝率 [%]']}%")
            print(f"  期待値 EV: {ev['期待値 EV [%]']}%")
            print(f"  プロフィットファクター: {ev['プロフィットファクター']}")

if __name__ == "__main__":
    main()
