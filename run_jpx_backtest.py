"""
Main Backtest Runner for Japanese Stocks (JPX)
"""

import logging
import argparse
from datetime import datetime
from backtesting import Backtest
from jquants_data_loader import JQuantsDataLoader
from jpx_strategy import JPXRSISwing
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_jpx_backtest(code: str, start: str, end: str, cash: float = 1_000_000):
    logging.info(f"Starting backtest for JPX stock code: {code}")
    
    # 1. データ取得
    loader = JQuantsDataLoader()
    df = loader.get_daily_quotes(code, start, end)
    
    if df.empty:
        logging.error("No data fetched. Check your J-Quants credentials and stock code.")
        return

    logging.info(f"Fetched {len(df)} bars for {code}")

    # 2. バックテスト実行
    bt = Backtest(
        df, 
        JPXRSISwing, 
        cash=cash, 
        commission=0.001,  # 日本株の平均的な手数料+スリッページ
        trade_on_close=True,
        exclusive_orders=True
    )
    
    stats = bt.run()
    
    # 3. 結果表示
    print(f"\n{'='*50}")
    print(f" JPX BACKTEST RESULTS: {code}")
    print(f"{'='*50}")
    print(stats)
    
    # 4. チャート保存
    try:
        filename = f"jpx_backtest_{code}.html"
        bt.plot(filename=filename, open_browser=False)
        logging.info(f"Chart saved to {filename}")
    except Exception as e:
        logging.warning(f"Could not save chart: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='JPX Stock Backtest Runner')
    parser.add_argument('--code', type=str, default='7203', help='Stock code (e.g. 7203 for Toyota)')
    parser.add_argument('--start', type=str, default='2023-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2024-12-31', help='End date (YYYY-MM-DD)')
    parser.add_argument('--cash', type=float, default=1000000, help='Initial cash')
    
    args = parser.parse_args()
    
    run_jpx_backtest(args.code, args.start, args.end, args.cash)
