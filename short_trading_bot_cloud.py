#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Short Trading Bot - Cloud Version
Google Cloud Run 用（1回の実行で終了する形式）
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, Optional, Any

import pandas as pd
import numpy as np
import requests

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SHORT_BOT_CLOUD")


class BTCShortBotCloud:
    """クラウド実行用ショート取引ボット"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get('symbol', 'BTC')
        self.timeframe = config.get('timeframe', '1h')
        self.paper_mode = config.get('paper_mode', True)
        self.live_trading = config.get('live_trading', False)

        self.environment = config.get('environment', 'mainnet').lower()
        self.base_url = (
            "https://api.hyperliquid.xyz"
            if self.environment == "mainnet"
            else "https://api.hyperliquid-testnet.xyz"
        )
        self.session = requests.Session()

        # Strategy parameters
        self.rsi_overbought = config.get('rsi_overbought', 60)
        self.profit_target_pct = config.get('profit_target_pct', 0.003)
        self.stop_loss_pct = config.get('stop_loss_pct', 0.01)
        self.max_hold_bars = config.get('max_hold_bars', 10)

        logger.info(f"Bot initialized: {self.symbol} {self.timeframe} (Cloud Version)")
        logger.info(f"Mode: {'PAPER' if self.paper_mode else 'LIVE'}")

    def calculate_rsi(self, closes: list, period: int = 14) -> float:
        """RSI計算"""
        if len(closes) < period:
            return 50.0

        delta = pd.Series(closes).diff()
        gain = delta.clip(lower=0).ewm(alpha=1/period, min_periods=period).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/period, min_periods=period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = (100 - 100 / (1 + rs)).values

        return float(rsi[-1]) if len(rsi) > 0 else 50.0

    def calculate_atr(self, high: list, low: list, close: list, period: int = 14) -> float:
        """ATR計算"""
        if len(close) < period:
            return 0.0

        h = pd.Series(high)
        l = pd.Series(low)
        c = pd.Series(close)
        pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/period, min_periods=period).mean()

        return float(atr.iloc[-1]) if len(atr) > 0 else 0.0

    def get_account_balance(self) -> Optional[Dict]:
        """アカウント残高を取得"""
        try:
            if self.config.get('manual_balance_enabled', False):
                manual_balance = float(self.config.get('manual_balance', 0))
                if manual_balance > 0:
                    return {
                        'account_value': manual_balance,
                        'available': manual_balance,
                        'token': 'USDC'
                    }

            # API経由で取得
            account_address = self.config.get('account_address')
            data = {
                "type": "clearinghouseState",
                "user": account_address
            }

            resp = self.session.post(
                f"{self.base_url}/info",
                json=data,
                timeout=10
            )

            if resp.status_code == 200:
                result = resp.json()
                if isinstance(result, dict):
                    margin = result.get('marginSummary', {})
                    account_value = float(margin.get('accountValue', 0))

                    if account_value > 0:
                        return {
                            'account_value': account_value,
                            'available': account_value,
                            'token': 'USDC'
                        }

            return None
        except Exception as e:
            logger.warning(f"Failed to get balance: {e}")
            return None

    def get_candles(self, limit: int = 100) -> Optional[pd.DataFrame]:
        """Hyperliquid APIからOHLCVデータを取得"""
        try:
            interval_ms_map = {
                "1m": 60_000,
                "5m": 5 * 60_000,
                "15m": 15 * 60_000,
                "1h": 60 * 60_000,
                "4h": 4 * 60 * 60_000,
                "1d": 24 * 60 * 60_000,
            }
            interval_ms = interval_ms_map.get(self.timeframe, 60 * 60_000)
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - limit * interval_ms

            data = {
                "type": "candleSnapshot",
                "req": {
                    "coin": self.symbol,
                    "interval": self.timeframe,
                    "startTime": start_ms,
                    "endTime": now_ms,
                }
            }

            resp = self.session.post(
                f"{self.base_url}/info",
                json=data,
                timeout=10
            )

            if resp.status_code != 200:
                logger.error(f"API error {resp.status_code}: {resp.text}")
                return None

            result = resp.json()
            if not result or not isinstance(result, list):
                logger.warning(f"Unexpected API response: {result}")
                return None

            df = pd.DataFrame(result)
            if df.empty:
                return None

            df['datetime'] = pd.to_datetime(df['t'], unit='ms')
            df['open'] = df['o'].astype(float)
            df['high'] = df['h'].astype(float)
            df['low'] = df['l'].astype(float)
            df['close'] = df['c'].astype(float)
            df['volume'] = df['v'].astype(float)

            return df[['datetime', 'open', 'high', 'low', 'close', 'volume']].sort_values('datetime').reset_index(drop=True)

        except Exception as e:
            logger.error(f"Failed to get candles: {e}")
            return None

    def run_once(self) -> Dict:
        """1回分のボット実行"""
        try:
            current_time = datetime.now()
            logger.info(f"=== Bot cycle {current_time.isoformat()} ===")

            # アカウント残高取得
            balance_info = self.get_account_balance()
            if balance_info:
                logger.info(f"Balance: {balance_info['account_value']:.2f} {balance_info['token']}")

            # キャンドルデータ取得
            df = self.get_candles(limit=100)
            if df is None or df.empty:
                logger.warning("No candle data available")
                return {'status': 'error', 'message': 'No candle data'}

            closes = df['close'].values
            highs = df['high'].values
            lows = df['low'].values
            current_price = closes[-1]
            prev_price = closes[-2] if len(closes) > 1 else current_price
            high = highs[-1]
            low = lows[-1]

            # インジケータ計算
            rsi = self.calculate_rsi(closes)
            atr = self.calculate_atr(highs, lows, closes)
            price_change = (current_price - closes[-20]) / closes[-20] if len(closes) > 20 else 0

            logger.info(
                f"Price: ${current_price:,.2f} | "
                f"RSI: {rsi:.1f} | "
                f"ATR: ${atr:,.2f} | "
                f"24h change: {price_change:+.2%}"
            )

            # エントリーシグナル検出
            prev_rsi = self.calculate_rsi(closes[:-1])

            if prev_rsi <= self.rsi_overbought and rsi > self.rsi_overbought:
                logger.info(
                    f"SHORT ENTRY SIGNAL: RSI crossed above {self.rsi_overbought} "
                    f"(prev={prev_rsi:.1f}, current={rsi:.1f})"
                )

                if self.paper_mode:
                    logger.info(f"[PAPER] Would open SHORT at ${current_price:.2f}")
                else:
                    logger.info(f"[LIVE] Opening SHORT position at ${current_price:.2f}")

                return {
                    'status': 'signal',
                    'action': 'entry',
                    'price': current_price,
                    'rsi': rsi
                }

            return {'status': 'ok', 'message': 'No signals', 'rsi': rsi}

        except Exception as e:
            logger.error(f"Error in run_once: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}


def load_config() -> Dict:
    """設定ファイルを読み込み"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                raw_lines = f.readlines()
            cleaned_lines = [line.split('//')[0] for line in raw_lines]
            return json.loads('\n'.join(cleaned_lines))
        except Exception as e:
            logger.warning(f"Failed to load config.json: {e}, using defaults")

    return {
        'symbol': 'BTC',
        'timeframe': '1h',
        'paper_mode': True,
        'live_trading': False,
        'environment': 'mainnet',
        'rsi_overbought': 60,
        'profit_target_pct': 0.003,
        'stop_loss_pct': 0.01,
        'max_hold_bars': 10,
        'manual_balance_enabled': True,
        'manual_balance': 199.12
    }


def main():
    """メイン実行"""
    logger.info("=" * 80)
    logger.info("BTC SHORT TRADING BOT - CLOUD VERSION")
    logger.info("=" * 80)

    config = load_config()
    logger.info(f"Loaded config from config.json")

    bot = BTCShortBotCloud(config)

    # 1回実行して終了
    result = bot.run_once()

    logger.info("=" * 80)
    logger.info(f"Execution result: {result['status']}")
    logger.info("=" * 80)

    return result


if __name__ == '__main__':
    main()
