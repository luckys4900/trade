#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Short Trading Bot - ダウントレンド対応
Hyperliquid ショート取引ボット
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

try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

logger = logging.getLogger(__name__)


def setup_logging() -> logging.Logger:
    """ログ設定"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base_dir, 'logs')

    # logsフォルダを作成
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        logger_temp = logging.getLogger("SETUP")
        logger_temp.info(f"Created logs directory: {log_dir}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"short_bot_{timestamp}.log")

    logger = logging.getLogger("SHORT_BOT")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info("=" * 70)
    logger.info(" BTC SHORT TRADING BOT - HYPERLIQUID")
    logger.info("=" * 70)
    logger.info(f"Start time: {datetime.now().isoformat()}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 70)

    return logger


logger = setup_logging()


class BTCShortBot:
    """BTC ショート取引ボット"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get('symbol', 'BTC')
        self.timeframe = config.get('timeframe', '1h')
        self.check_interval = config.get('check_interval', 60)
        self.paper_mode = config.get('paper_mode', True)
        self.live_trading = config.get('live_trading', False)

        # Exchange setup
        self.environment = config.get('environment', 'mainnet').lower()
        self.base_url = (
            "https://api.hyperliquid.xyz"
            if self.environment == "mainnet"
            else "https://api.hyperliquid-testnet.xyz"
        )
        self.session = requests.Session()

        # Strategy parameters (Optimized: RSI 60)
        self.rsi_overbought = config.get('rsi_overbought', 60)  # 70 → 60 (More entries)
        self.profit_target_pct = config.get('profit_target_pct', 0.003)  # 0.5% → 0.3%
        self.stop_loss_pct = config.get('stop_loss_pct', 0.01)  # 1%
        self.max_hold_bars = config.get('max_hold_bars', 10)  # 10時間

        # Trading state
        self.in_position = False
        self.position_entry_price: Optional[float] = None
        self.position_entry_time: Optional[datetime] = None
        self.position_entry_bar = None
        self.trades_today = 0
        self.daily_pnl = 0.0

        logger.info(
            f"ShortBot initialized: "
            f"symbol={self.symbol}, "
            f"timeframe={self.timeframe}, "
            f"paper_mode={self.paper_mode}, "
            f"rsi_overbought={self.rsi_overbought}"
        )

    def alert_sound(self, alert_type: str = "entry"):
        """トレードアラート音を鳴らす"""
        if not SOUND_AVAILABLE:
            return

        try:
            if alert_type == "entry":
                # エントリー: 高音 x 2回
                winsound.Beep(1000, 300)
                time.sleep(0.1)
                winsound.Beep(1000, 300)
            elif alert_type == "profit":
                # 利確: 高音 x 3回（成功の音）
                winsound.Beep(1200, 200)
                time.sleep(0.1)
                winsound.Beep(1200, 200)
                time.sleep(0.1)
                winsound.Beep(1200, 200)
            elif alert_type == "loss":
                # 損切: 低音（警告音）
                winsound.Beep(500, 400)
        except Exception as e:
            logger.debug(f"Audio alert failed: {e}")

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
        """アカウント残高を取得（API または 手動設定）"""
        try:
            # 手動残高設定が有効な場合はそれを使用
            if self.config.get('manual_balance_enabled', False):
                manual_balance = float(self.config.get('manual_balance', 0))
                if manual_balance > 0:
                    return {
                        'account_value': manual_balance,
                        'total_margin': 0,
                        'available': manual_balance,
                        'token': 'USDC',
                        'source': 'manual'
                    }

            # API経由で取得を試みる
            account_address = self.config.get('account_address')
            endpoint = "/info"

            data = {
                "type": "clearinghouseState",
                "user": account_address
            }

            resp = self.session.post(
                f"{self.base_url}{endpoint}",
                json=data,
                timeout=10
            )

            if resp.status_code == 200:
                result = resp.json()
                if isinstance(result, dict):
                    margin_summary = result.get('marginSummary', {})
                    account_value = float(margin_summary.get('accountValue', 0))
                    total_margin = float(margin_summary.get('totalMargin', 0))

                    if account_value > 0:
                        return {
                            'account_value': account_value,
                            'total_margin': total_margin,
                            'available': account_value - total_margin,
                            'token': 'USDC',
                            'source': 'api'
                        }

            return None
        except Exception as e:
            logger.debug(f"Failed to get balance: {e}")
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

            endpoint = "/info"
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
                f"{self.base_url}{endpoint}",
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

    def run_once(self):
        """1回分のボット実行"""
        try:
            current_time = datetime.now()
            logger.info(f"=== Bot cycle {current_time.isoformat()} ===")

            # アカウント残高を取得して表示
            balance_info = self.get_account_balance()
            if balance_info:
                account_value = balance_info['account_value']
                available = balance_info['available']
                token = balance_info.get('token', 'UNKNOWN')
                source = balance_info.get('source', 'unknown')

                logger.info(f"[{source.upper()}] Balance: {account_value:,.2f} {token} | Available: {available:,.2f} {token}")

                # 残高が不足している場合は警告
                required_per_trade = self.config.get('initial_capital', 100) * self.config.get('position_size_pct', 0.1)
                if available < required_per_trade:
                    logger.warning(f"INSUFFICIENT BALANCE! Need: {required_per_trade:.2f} {token}, Have: {available:.2f} {token}")
                elif available < required_per_trade * 2:
                    logger.warning(f"LOW BALANCE: {available:.2f} {token} (min recommended: {required_per_trade * 2:.2f})")
            else:
                logger.warning("Could not retrieve account balance - update manual_balance in config.json")

            # キャンドルデータ取得
            df = self.get_candles(limit=100)
            if df is None or df.empty:
                logger.warning("No candle data available")
                return

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

            # ポジション保有中の状態表示
            if self.in_position:
                logger.info(f"Position OPEN: Entry=${self.position_entry_price:.2f}")

                # 利益確定チェック: 価格が0.5%以上下がった
                profit_pct = (self.position_entry_price - low) / self.position_entry_price
                if profit_pct >= self.profit_target_pct:
                    logger.info(
                        f"PROFIT TARGET HIT: {profit_pct:.2%} "
                        f"(Entry: ${self.position_entry_price:.2f}, Low: ${low:.2f})"
                    )
                    self.alert_sound("profit")  # 利確アラート音
                    if self.paper_mode:
                        logger.info(f"[PAPER] Would close SHORT for +{profit_pct:.2%}")
                    else:
                        # 実際の決済処理
                        logger.info(f"[LIVE] Closing SHORT position")
                    self.in_position = False

                # 損切りチェック: 価格が1%以上上がった
                elif high >= self.position_entry_price * (1 + self.stop_loss_pct):
                    loss_pct = (high - self.position_entry_price) / self.position_entry_price
                    logger.warning(
                        f"STOP LOSS HIT: {loss_pct:.2%} "
                        f"(Entry: ${self.position_entry_price:.2f}, High: ${high:.2f})"
                    )
                    self.alert_sound("loss")  # 損切りアラート音
                    if self.paper_mode:
                        logger.info(f"[PAPER] Would close SHORT for -{loss_pct:.2%}")
                    else:
                        logger.info(f"[LIVE] Closing SHORT position (stop loss)")
                    self.in_position = False

                # タイムアウトチェック: 10時間以上保有
                current_bar = len(df) - 1
                if self.position_entry_bar and (current_bar - self.position_entry_bar) >= self.max_hold_bars:
                    hold_return = (self.position_entry_price - current_price) / self.position_entry_price
                    logger.info(
                        f"TIMEOUT: {self.max_hold_bars} bars held "
                        f"(Return: {hold_return:+.2%})"
                    )
                    if self.paper_mode:
                        logger.info(f"[PAPER] Would close SHORT for {hold_return:+.2%}")
                    else:
                        logger.info(f"[LIVE] Closing SHORT position (timeout)")
                    self.in_position = False

            # ショートエントリーチェック
            else:
                prev_rsi = self.calculate_rsi(closes[:-1])  # 前のRSI

                if prev_rsi <= self.rsi_overbought and rsi > self.rsi_overbought:
                    logger.info(
                        f"SHORT ENTRY SIGNAL: "
                        f"RSI crossed above {self.rsi_overbought} "
                        f"(prev={prev_rsi:.1f}, current={rsi:.1f})"
                    )

                    self.position_entry_price = current_price
                    self.position_entry_time = current_time
                    self.position_entry_bar = len(df) - 1
                    self.in_position = True
                    self.alert_sound("entry")  # エントリーアラート音

                    if self.paper_mode:
                        logger.info(f"[PAPER] Would open SHORT at ${current_price:.2f}")
                    else:
                        logger.info(f"[LIVE] Opening SHORT position at ${current_price:.2f}")

        except Exception as e:
            logger.error(f"Error in run_once: {e}", exc_info=True)

    def run_loop(self):
        """メイントレーディングループ"""
        logger.info("Starting short trading loop...")
        logger.info(f"Paper mode: {self.paper_mode}")
        logger.info(f"Check interval: {self.check_interval} seconds\n")

        try:
            while True:
                try:
                    self.run_once()
                except Exception as e:
                    logger.error(f"Cycle error: {e}", exc_info=True)

                logger.info(f"Sleeping {self.check_interval}s...\n")
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        finally:
            logger.info("Short trading bot stopped")


def main():
    """エントリーポイント"""
    # デフォルト設定
    config = {
        'symbol': 'BTC',
        'timeframe': '1h',
        'check_interval': 60,
        'paper_mode': True,
        'live_trading': False,
        'environment': 'mainnet',
        'rsi_overbought': 70,
        'profit_target_pct': 0.005,   # 0.5%
        'stop_loss_pct': 0.01,        # 1%
        'max_hold_bars': 10,          # 10時間
    }

    # config.json から設定を上書き（存在する場合）
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                raw_lines = f.readlines()
            cleaned_lines = [line.split('//')[0] for line in raw_lines]
            config.update(json.loads('\n'.join(cleaned_lines)))
            logger.info(f"Loaded config from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config.json: {e}, using defaults")

    # ボット起動
    bot = BTCShortBot(config)

    if bot.paper_mode:
        logger.info("Running in PAPER TRADING mode")
        logger.info("This is a simulation - no real trades will be placed")
    else:
        logger.warning("⚠️  LIVE TRADING MODE")
        logger.warning("Real money trades will be placed")

    bot.run_loop()


if __name__ == '__main__':
    main()
