from backtesting import Backtest
import pandas as pd
from strategies.micro_breakout import HyperliquidMicroBreakout
from strategies.mean_reversion import MeanReversionOrderbookImbalance
from strategies.ema_ribbon import EMA_Ribbon_VolumeSpike
from strategies.triple_top_breakout import TripleTopBreakout
import warnings
import os
from pathlib import Path

warnings.filterwarnings('ignore')

def run_comprehensive_backtest():
    """
    包括的バックテスト実行
    - 3つの戦略を比較
    - 最適化
    - レポート生成
    """
    
    # ディレクトリ作成
    Path("./backtest_results").mkdir(parents=True, exist_ok=True)
    
    # データ読み込み
    print("=" * 70)
    print("Hyperliquid BTC 5分足バックテスト開始")
    print("=" * 70)
    
    data_path = './data/raw/BTC_5m_hyperliquid.csv'
    if not os.path.exists(data_path):
        print(f"データファイルが見つかりません: {data_path}")
        print("まずは 'python data/fetch_hyperliquid_data_demo.py' を実行してください")
        return None, None, None
    
    df = pd.read_csv(data_path, index_col=0, parse_dates=True)
    
    # 大文字カラム名に変換（backtesting.py要件）
    df.columns = [col.capitalize() for col in df.columns]
    
    print(f"\nデータ概要")
    print(f"期間: {df.index[0]} ～ {df.index[-1]}")
    print(f"データ数: {len(df):,} 本")
    print(f"期間日数: {(df.index[-1] - df.index[0]).days} 日")
    
    # ===================================================================
    # 戦略1: マイクロブレイクアウト
    # ===================================================================
    print("\n" + "=" * 70)
    print("戦略1: マイクロブレイクアウト")
    print("=" * 70)
    
    bt1 = Backtest(
        df,
        HyperliquidMicroBreakout,
        cash=100,  # 100 USDT
        commission=0.00045,  # Hyperliquid Taker 0.045%
        exclusive_orders=True,
        trade_on_close=False
    )
    
    # パラメータ最適化
    print("\nパラメータ最適化中...")
    stats1 = bt1.optimize(
        bb_period=range(15, 25, 5),
        atr_period=range(10, 18, 2),
        volume_multiplier=[1.3, 1.5, 1.8],
        profit_target_atr=[1.5, 2.0, 2.5],
        stop_loss_atr=[0.8, 1.0, 1.2],
        maximize='Sharpe Ratio',
        constraint=lambda p: p.profit_target_atr > p.stop_loss_atr
    )
    
    print_results("マイクロブレイクアウト", stats1)
    
    # ===================================================================
    # 戦略2: 平均回帰
    # ===================================================================
    print("\n" + "=" * 70)
    print("戦略2: 平均回帰")
    print("=" * 70)
    
    bt2 = Backtest(
        df,
        MeanReversionOrderbookImbalance,
        cash=100,
        commission=0.00015,  # Maker手数料（リベート考慮で低め）
        exclusive_orders=True
    )
    
    stats2 = bt2.optimize(
        rsi_period=range(7, 12, 2),
        rsi_oversold=range(20, 30, 5),
        rsi_overbought=range(70, 80, 5),
        bb_std=[2.0, 2.5, 3.0],
        maximize='Sharpe Ratio'
    )
    
    print_results("平均回帰", stats2)
    
    # ===================================================================
    # 戦略3: EMAリボン
    # ===================================================================
    print("\n" + "=" * 70)
    print("戦略3: EMAリボン + ボリュームスパイク")
    print("=" * 70)
    
    bt3 = Backtest(
        df,
        EMA_Ribbon_VolumeSpike,
        cash=100,
        commission=0.00045,
        exclusive_orders=True
    )
    
    stats3 = bt3.optimize(
        ema_fast=[3, 5, 7],
        ema_mid1=[8, 10, 12],
        ema_slow=[40, 50, 60],
        volume_spike_multiplier=[1.5, 2.0, 2.5],
        maximize='Sharpe Ratio',
        constraint=lambda p: p.ema_fast < p.ema_mid1 < p.ema_slow
    )
    
    print_results("EMAリボン", stats3)
    
    # ===================================================================
    # 戦略4: トリプルトップブレイクアウト (TVScreenerベース)
    # ===================================================================
    print("\n" + "=" * 70)
    print("戦略4: トリプルトップブレイクアウト (TVScreenerベース)")
    print("=" * 70)
    
    bt4 = Backtest(
        df,
        TripleTopBreakout,
        cash=100,
        commission=0.00045,
        exclusive_orders=True,
        trade_on_close=False
    )
    
    print("\nパラメータ最適化中...")
    stats4 = bt4.optimize(
        pivot_length=range(5, 10, 2),
        price_tolerance_pct=[1.0, 1.5, 2.0],
        min_high_count=[2, 3],
        sl_atr_mult=[2.0, 2.5, 3.0],
        tp_atr_mult=[3.0, 4.0, 5.0],
        volume_mult=[2.0, 2.5, 3.0],
        maximize='Sharpe Ratio',
        constraint=lambda p: p.tp_atr_mult > p.sl_atr_mult
    )
    
    print_results("トリプルトップブレイクアウト", stats4)
    
    # ===================================================================
    # 比較サマリー
    # ===================================================================
    print("\n" + "=" * 70)
    print("戦略比較サマリー")
    print("=" * 70)
    
    comparison = pd.DataFrame({
        'マイクロブレイクアウト': extract_key_metrics(stats1),
        '平均回帰': extract_key_metrics(stats2),
        'EMAリボン': extract_key_metrics(stats3),
        'トリプルトップBK': extract_key_metrics(stats4)
    }).T
    
    print(comparison.to_string())
    
    all_sharpes = {
        'マイクロブレイクアウト': (stats1['Sharpe Ratio'], bt1),
        '平均回帰': (stats2['Sharpe Ratio'], bt2),
        'EMAリボン': (stats3['Sharpe Ratio'], bt3),
        'トリプルトップBK': (stats4['Sharpe Ratio'], bt4),
    }
    best_name = max(all_sharpes, key=lambda k: all_sharpes[k][0])
    best_sharpe = all_sharpes[best_name][0]
    best_bt = all_sharpes[best_name][1]
    
    safe_names = {
        'マイクロブレイクアウト': 'micro_breakout',
        '平均回帰': 'mean_reversion',
        'EMAリボン': 'ema_ribbon',
        'トリプルトップBK': 'triple_top_breakout',
    }
    best_bt.plot(
        filename=f'./backtest_results/{safe_names[best_name]}_best.html',
        open_browser=False
    )
    
    print(f"\n最良戦略: {best_name}（シャープレシオ {best_sharpe:.2f}）")
    print("結果HTMLは backtest_results/ フォルダで確認できます")
    
    return stats1, stats2, stats3, stats4


def print_results(strategy_name, stats):
    """結果表示"""
    print(f"\n{strategy_name} - バックテスト結果")
    print("-" * 70)
    print(f"総リターン:          {stats['Return [%]']:.2f}%")
    print(f"年間リターン:        {stats['Return (Ann.) [%]']:.2f}%")
    print(f"シャープレシオ:      {stats['Sharpe Ratio']:.2f}")
    print(f"最大ドローダウン:    {stats['Max. Drawdown [%]']:.2f}%")
    print(f"勝率:                {stats['Win Rate [%]']:.2f}%")
    print(f"総トレード数:        {stats['# Trades']}")
    print(f"平均トレード:        {stats['Avg. Trade [%]']:.2f}%")
    print(f"プロフィットファクター: {stats.get('Profit Factor', 'N/A')}")
    print(f"最大連勝:            {stats['Best Trade [%]']:.2f}%")
    print(f"最大連敗:            {stats['Worst Trade [%]']:.2f}%")
    print(f"平均保有時間:        {stats['Avg. Trade Duration']}")


def extract_key_metrics(stats):
    """主要指標抽出"""
    return {
        '総リターン': f"{stats['Return [%]']:.2f}%",
        '年間リターン': f"{stats['Return (Ann.) [%]']:.2f}%",
        'シャープレシオ': f"{stats['Sharpe Ratio']:.2f}",
        '最大DD': f"{stats['Max. Drawdown [%]']:.2f}%",
        '勝率': f"{stats['Win Rate [%]']:.2f}%",
        'トレード数': stats['# Trades']
    }


if __name__ == "__main__":
    results = run_comprehensive_backtest()
    
    if results[0] is not None:
        print("\nバックテスト完了！")
    else:
        print("\nバックテストに失敗しました")