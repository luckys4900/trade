#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ログファイルの整理スクリプト
メインディレクトリのログファイルを logs/ フォルダに移動
"""

import os
import glob
import shutil
from pathlib import Path

def cleanup_logs():
    """ログファイルをlogsフォルダに移動"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(base_dir, 'logs')

    # logsフォルダを作成
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
        print(f"Created: {logs_dir}")

    # メインディレクトリのログファイルを検索
    log_patterns = [
        'short_bot_*.log',
        'rsi_swing_*.log',
        'trader_*.log',
        'v5_hl_*.log',
        'live_trade_*.log',
        'backtest_*.log'
    ]

    moved_count = 0
    for pattern in log_patterns:
        log_files = glob.glob(os.path.join(base_dir, pattern))

        for log_file in log_files:
            try:
                filename = os.path.basename(log_file)
                dest_path = os.path.join(logs_dir, filename)

                shutil.move(log_file, dest_path)
                print(f"Moved: {filename}")
                moved_count += 1
            except Exception as e:
                print(f"Error moving {log_file}: {e}")

    print()
    print("=" * 80)
    print(f"Cleanup complete: {moved_count} files moved to logs/")
    print("=" * 80)

    # ディレクトリ構造を表示
    print("\nDirectory structure:")
    print(f"{base_dir}/")
    print(f"  ├─ logs/")
    print(f"  │  └─ *.log files ({len(glob.glob(os.path.join(logs_dir, '*.log')))} files)")
    print(f"  ├─ short_trading_bot.py")
    print(f"  ├─ config.json")
    print(f"  └─ ...")

if __name__ == '__main__':
    cleanup_logs()
