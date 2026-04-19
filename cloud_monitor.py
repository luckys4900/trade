#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Cloud Run Bot Monitor Dashboard
Monitor bot execution logs and results from cloud in real-time
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

# Fix encoding
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    from google.cloud import logging as cloud_logging
    from google.cloud import run_v2
    GOOGLE_CLOUD_AVAILABLE = True
except ImportError:
    GOOGLE_CLOUD_AVAILABLE = False
    print("Warning: Google Cloud libraries not fully configured")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("CLOUD_MONITOR")


class CloudBotMonitor:
    """Google Cloud Run ボット監視クラス"""

    def __init__(self, project_id: Optional[str] = None):
        """
        初期化

        Args:
            project_id: Google Cloud プロジェクトID
                       未指定の場合は環境変数 GOOGLE_CLOUD_PROJECT から取得
        """
        self.project_id = project_id or os.environ.get('GOOGLE_CLOUD_PROJECT')

        if not self.project_id:
            logger.warning("Google Cloud Project ID not set")
            logger.warning("Set environment variable: GOOGLE_CLOUD_PROJECT=your-project-id")
            self.project_id = "your-project-id"

        self.service_name = "btc-trading-bot"
        self.region = "us-central1"

        try:
            if GOOGLE_CLOUD_AVAILABLE:
                self.logging_client = cloud_logging.Client(project=self.project_id)
            else:
                self.logging_client = None
        except Exception as e:
            logger.warning(f"Could not initialize Cloud Logging: {e}")
            self.logging_client = None

    def get_recent_logs(self, minutes: int = 60, limit: int = 50) -> List[Dict]:
        """
        最近のボット実行ログを取得

        Args:
            minutes: 過去何分のログを取得するか
            limit: 最大ログ数

        Returns:
            ログエントリのリスト
        """
        if not self.logging_client:
            logger.error("Cloud Logging not available")
            return self._get_mock_logs()

        try:
            # ログフィルタ設定
            filter_str = (
                f'resource.type="cloud_run_revision" AND '
                f'resource.labels.service_name="{self.service_name}" AND '
                f'timestamp>"{(datetime.utcnow() - timedelta(minutes=minutes)).isoformat()}Z"'
            )

            entries = self.logging_client.list_entries(
                filter_=filter_str,
                page_size=limit,
                order_by=cloud_logging.DESCENDING
            )

            logs = []
            for entry in entries:
                logs.append({
                    'timestamp': entry.timestamp,
                    'severity': entry.severity,
                    'message': entry.payload,
                    'labels': entry.labels
                })

            return logs

        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            return self._get_mock_logs()

    def parse_bot_execution(self, logs: List[Dict]) -> Dict:
        """
        ログから最新のボット実行結果を解析

        Args:
            logs: ログエントリのリスト

        Returns:
            解析されたボット実行情報
        """
        result = {
            'latest_execution': None,
            'status': 'UNKNOWN',
            'signal': None,
            'price': None,
            'rsi': None,
            'balance': None,
            'errors': [],
            'entries': [],
            'total_executions': 0
        }

        execution_count = 0

        for log in logs:
            message = str(log['message']) if isinstance(log['message'], str) else str(log['message'])

            # 実行情報を抽出
            if 'Bot cycle' in message or 'Bot initialized' in message:
                execution_count += 1
                result['latest_execution'] = log['timestamp']

            # ステータス確認
            if 'LIVE TRADING MODE' in message:
                result['status'] = 'LIVE'
            elif 'PAPER' in message:
                result['status'] = 'PAPER'

            # 価格・RSI情報
            if 'Price:' in message and 'RSI:' in message:
                try:
                    # 例: "Price: $74,405.00 | RSI: 54.4"
                    parts = message.split('|')
                    for part in parts:
                        if 'Price:' in part:
                            price_str = part.split('$')[1].strip().split()[0]
                            result['price'] = float(price_str.replace(',', ''))
                        if 'RSI:' in part:
                            rsi_str = part.split('RSI:')[1].strip().split()[0]
                            result['rsi'] = float(rsi_str)
                except:
                    pass

            # 残高情報
            if 'Balance:' in message:
                try:
                    balance_str = message.split('Balance:')[1].split('USDC')[0].strip()
                    result['balance'] = float(balance_str)
                except:
                    pass

            # エントリーシグナル
            if 'SHORT ENTRY SIGNAL' in message:
                result['signal'] = 'ENTRY'
                result['entries'].append({
                    'timestamp': log['timestamp'],
                    'type': 'SHORT_ENTRY'
                })

            # 利確
            if 'PROFIT TARGET HIT' in message:
                result['signal'] = 'PROFIT'
                result['entries'].append({
                    'timestamp': log['timestamp'],
                    'type': 'PROFIT_TARGET'
                })

            # 損切り
            if 'STOP LOSS HIT' in message:
                result['signal'] = 'LOSS'
                result['entries'].append({
                    'timestamp': log['timestamp'],
                    'type': 'STOP_LOSS'
                })

            # エラー
            if 'ERROR' in log['severity'] or 'WARNING' in log['severity']:
                result['errors'].append({
                    'timestamp': log['timestamp'],
                    'message': message,
                    'severity': log['severity']
                })

        result['total_executions'] = execution_count
        return result

    def display_dashboard(self, result: Dict):
        """Display monitoring dashboard"""
        print("\n" + "=" * 80)
        print("CLOUD BOT MONITOR DASHBOARD")
        print("=" * 80)

        # Status
        print(f"\n[STATUS]")
        status_icon = "[LIVE]" if result['status'] == 'LIVE' else "[PAPER]"
        print(f"  {status_icon} Mode: {result['status']}")

        if result['latest_execution']:
            print(f"  [LAST] Execution: {result['latest_execution']}")

        # Market Info
        print(f"\n[MARKET INFO]")
        if result['price']:
            print(f"  [PRICE] ${result['price']:,.2f}")
        if result['rsi']:
            rsi_status = "[OVERBOUGHT]" if result['rsi'] > 60 else "[NORMAL]"
            print(f"  [RSI] {result['rsi']:.1f} {rsi_status}")
        if result['balance']:
            print(f"  [BALANCE] {result['balance']:,.2f} USDC")

        # Signal
        print(f"\n[LATEST SIGNAL]")
        if result['signal']:
            signal_display = {
                'ENTRY': '[ENTRY] SHORT',
                'PROFIT': '[PROFIT] Target Hit',
                'LOSS': '[LOSS] Stop Hit'
            }
            print(f"  {signal_display.get(result['signal'], result['signal'])}")
        else:
            print(f"  [WAIT] No Signals (monitoring...)")

        # Entry History
        if result['entries']:
            print(f"\n[ENTRY HISTORY - Recent 5]")
            for entry in result['entries'][-5:]:
                action = entry['type'].replace('_', ' ')
                print(f"  - {entry['timestamp']} : {action}")

        # Errors
        if result['errors']:
            print(f"\n[ERRORS/WARNINGS - Recent 3]")
            for error in result['errors'][-3:]:
                icon = "[WARN]" if error['severity'] == 'WARNING' else "[ERROR]"
                print(f"  {icon} {error['timestamp']}")
                print(f"       {error['message'][:70]}")

        print(f"\n[STATISTICS]")
        print(f"  Total Executions: {result['total_executions']} times")
        print(f"  Entry Count: {len(result['entries'])} entries")
        print(f"  Error Count: {len(result['errors'])} errors")

        print("\n" + "=" * 80 + "\n")

    def get_statistics(self, logs: List[Dict]) -> Dict:
        """
        実行統計を計算

        Args:
            logs: ログエントリのリスト

        Returns:
            統計情報
        """
        stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'entries': 0,
            'profits': 0,
            'losses': 0,
            'errors': 0
        }

        for log in logs:
            message = str(log['message'])

            if 'Bot cycle' in message:
                stats['total_runs'] += 1

            if 'SHORT ENTRY SIGNAL' in message:
                stats['entries'] += 1
                stats['successful_runs'] += 1

            if 'PROFIT TARGET HIT' in message:
                stats['profits'] += 1

            if 'STOP LOSS HIT' in message:
                stats['losses'] += 1

            if 'ERROR' in log['severity']:
                stats['errors'] += 1

        return stats

    def _get_mock_logs(self) -> List[Dict]:
        """
        テスト用のモックログを返す
        （Google Cloud が設定されていない場合）
        """
        return [
            {
                'timestamp': datetime.now() - timedelta(minutes=5),
                'severity': 'INFO',
                'message': '=== Bot cycle 2026-03-18T05:07:12 ===',
                'labels': {}
            },
            {
                'timestamp': datetime.now() - timedelta(minutes=5),
                'severity': 'INFO',
                'message': '[MANUAL] Balance: 199.12 USDC | Available: 199.12 USDC',
                'labels': {}
            },
            {
                'timestamp': datetime.now() - timedelta(minutes=5),
                'severity': 'INFO',
                'message': 'Price: $74,425.00 | RSI: 54.6 | ATR: $588.56 | 24h change: -1.54%',
                'labels': {}
            }
        ]


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description='Cloud Bot Monitor')
    parser.add_argument('--project-id', help='Google Cloud Project ID')
    parser.add_argument('--minutes', type=int, default=120, help='ログ取得期間（分）')
    parser.add_argument('--limit', type=int, default=100, help='最大ログ数')
    parser.add_argument('--stats', action='store_true', help='統計情報を表示')

    args = parser.parse_args()

    # モニター初期化
    monitor = CloudBotMonitor(project_id=args.project_id)

    logger.info("Fetching Cloud Logging data...")

    # ログ取得
    logs = monitor.get_recent_logs(minutes=args.minutes, limit=args.limit)

    if not logs:
        logger.warning("No logs found. Make sure Cloud Logging is enabled.")
        logger.info("\nSetup instructions:")
        logger.info("1. Set environment variable: GOOGLE_CLOUD_PROJECT=your-project-id")
        logger.info("2. Authenticate: gcloud auth login")
        logger.info("3. Run again")
        return

    logger.info(f"Retrieved {len(logs)} log entries")

    # ボット実行情報を解析
    result = monitor.parse_bot_execution(logs)

    # ダッシュボード表示
    monitor.display_dashboard(result)

    # Statistics
    if args.stats:
        stats = monitor.get_statistics(logs)
        print("[DETAILED STATISTICS]")
        print(f"  Total Runs: {stats['total_runs']}")
        print(f"  Successful: {stats['successful_runs']}")
        print(f"  Entries: {stats['entries']}")
        print(f"  Profits: {stats['profits']}")
        print(f"  Losses: {stats['losses']}")
        print(f"  Errors: {stats['errors']}\n")


if __name__ == '__main__':
    main()
