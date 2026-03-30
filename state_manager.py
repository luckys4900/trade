#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Grid Trading Bot - State Manager
Handles data retrieval, processing, and technical indicator calculation
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import requests
from ui_config import (
    UPDATE_INTERVAL, RSI_PERIOD, ATR_PERIOD,
    READY_THRESHOLD, WARN_THRESHOLD, API_TIMEOUT, MAX_RETRIES
)

logger = logging.getLogger(__name__)


class StateManager:
    """GridBot の取引状態を取得・加工する"""

    def __init__(self, grid_bot_instance=None, api_base_url="https://api.hyperliquid.xyz"):
        """
        Args:
            grid_bot_instance: GridBot インスタンス（同じプロセス内）
            api_base_url: Hyperliquid API ベース URL
        """
        self.grid_bot = grid_bot_instance
        self.api_base_url = api_base_url
        self.last_update = None
        self.current_price = None
        self.ohlcv_data = None
        self.grid_state = {}
        self.indicators = {}
        self.session = requests.Session()

    def _fetch_ohlcv(self, symbol: str = "BTC", interval: int = 3600, limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Hyperliquid API から過去 100 本の 1h ローソク足データを取得

        Args:
            symbol: 取引シンボル（デフォルト: "BTC"）
            interval: ローソク足の間隔（秒、デフォルト: 3600 = 1h）
            limit: 取得本数（デフォルト: 100）

        Returns:
            OHLCV データの DataFrame、またはエラー時は None
        """
        try:
            url = f"{self.api_base_url}/info"
            params = {
                "type": "candleSnapshot",
                "coin": symbol,
                "interval": interval,
                "startTime": int((datetime.now().timestamp() - (limit * interval)) * 1000),
                "endTime": int(datetime.now().timestamp() * 1000)
            }

            for attempt in range(MAX_RETRIES):
                try:
                    response = self.session.get(url, params=params, timeout=API_TIMEOUT)
                    response.raise_for_status()
                    data = response.json()

                    if not data or "candles" not in data:
                        logger.warning(f"No candle data returned for {symbol}")
                        return None

                    candles = data["candles"]
                    if len(candles) == 0:
                        logger.warning(f"Empty candles list for {symbol}")
                        return None

                    df = pd.DataFrame([
                        {
                            "timestamp": pd.to_datetime(c.get("t", 0), unit="ms"),
                            "open": float(c.get("o", 0)),
                            "high": float(c.get("h", 0)),
                            "low": float(c.get("l", 0)),
                            "close": float(c.get("c", 0)),
                            "volume": float(c.get("v", 0))
                        }
                        for c in candles
                    ])

                    if len(df) < 2:
                        logger.warning(f"Not enough candle data: {len(df)} candles")
                        return None

                    return df.sort_values("timestamp").reset_index(drop=True)

                except requests.RequestException as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.debug(f"Retry {attempt + 1}/{MAX_RETRIES} for OHLCV fetch: {e}")
                        continue
                    raise

        except Exception as e:
            logger.error(f"Error fetching OHLCV data for {symbol}: {e}")
            return None

    def _calculate_rsi(self, prices: List[float], period: int = RSI_PERIOD) -> Optional[float]:
        """
        RSI（相対力指数）を計算

        Args:
            prices: 価格リスト
            period: RSI 計算期間（デフォルト: 14）

        Returns:
            RSI 値（0-100）、またはエラー時は None
        """
        try:
            if len(prices) < period + 1:
                logger.warning(f"Not enough data for RSI (need {period + 1}, got {len(prices)})")
                return None

            prices_series = pd.Series(prices)
            deltas = prices_series.diff()

            seed = deltas[:period + 1]
            up = seed[seed >= 0].sum() / period
            down = -seed[seed < 0].sum() / period

            rs = up / down if down != 0 else 0
            rsi = 100 - (100 / (1 + rs)) if down != 0 else 50

            # EMA 平滑化
            rsi_values = [rsi]
            for delta in deltas[period + 1:]:
                if delta >= 0:
                    up = (up * (period - 1) + delta) / period
                    down = down * (period - 1) / period
                else:
                    up = up * (period - 1) / period
                    down = (down * (period - 1) - delta) / period

                rs = up / down if down != 0 else 0
                rsi = 100 - (100 / (1 + rs)) if down != 0 else 50
                rsi_values.append(rsi)

            return float(rsi_values[-1]) if rsi_values else None

        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None

    def _calculate_atr(self, high: List[float], low: List[float], close: List[float], period: int = ATR_PERIOD) -> Optional[float]:
        """
        ATR（平均真の値幅）を計算

        Args:
            high: 高値リスト
            low: 安値リスト
            close: 終値リスト
            period: ATR 計算期間（デフォルト: 14）

        Returns:
            ATR 値、またはエラー時は None
        """
        try:
            if len(close) < period:
                logger.warning(f"Not enough data for ATR (need {period}, got {len(close)})")
                return None

            h = pd.Series(high)
            l = pd.Series(low)
            c = pd.Series(close)

            pc = c.shift(1)
            tr = pd.concat([
                h - l,
                (h - pc).abs(),
                (l - pc).abs(),
            ], axis=1).max(axis=1)

            atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
            return float(atr.iloc[-1]) if not atr.isna().all() else None

        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None

    def _get_grid_state(self) -> Dict:
        """
        GridBot インスタンスからグリッド状態を取得

        Returns:
            グリッド状態辞書
            {
                "grid_center": float,
                "grid_range": float,
                "buy_levels": List[float],
                "sell_levels": List[float],
                "open_orders": int,
                "filled_levels": List[int]
            }
        """
        try:
            if self.grid_bot is None or not hasattr(self.grid_bot, 'grid_manager'):
                logger.warning("GridBot instance not available")
                return {
                    "grid_center": None,
                    "grid_range": None,
                    "buy_levels": [],
                    "sell_levels": [],
                    "open_orders": 0,
                    "filled_levels": []
                }

            gm = self.grid_bot.grid_manager
            return {
                "grid_center": getattr(gm, 'grid_center', None),
                "grid_range": getattr(gm, 'grid_range', None),
                "buy_levels": getattr(gm, 'buy_levels', []),
                "sell_levels": getattr(gm, 'sell_levels', []),
                "open_orders": len(getattr(gm, 'open_orders', {})),
                "filled_levels": list(getattr(gm, 'filled_levels', set()))
            }

        except Exception as e:
            logger.error(f"Error getting grid state: {e}")
            return {
                "grid_center": None,
                "grid_range": None,
                "buy_levels": [],
                "sell_levels": [],
                "open_orders": 0,
                "filled_levels": []
            }

    def _fetch_current_price(self, symbol: str = "BTC") -> Optional[float]:
        """
        Hyperliquid API から現在価格を取得

        Args:
            symbol: 取引シンボル（デフォルト: "BTC"）

        Returns:
            現在価格、またはエラー時は None
        """
        try:
            url = f"{self.api_base_url}/info"
            params = {
                "type": "lastPrice",
                "coin": symbol
            }

            for attempt in range(MAX_RETRIES):
                try:
                    response = self.session.get(url, params=params, timeout=API_TIMEOUT)
                    response.raise_for_status()
                    data = response.json()

                    if "lastPrice" in data:
                        return float(data["lastPrice"])

                    logger.warning(f"No lastPrice in response for {symbol}")
                    return None

                except requests.RequestException as e:
                    if attempt < MAX_RETRIES - 1:
                        logger.debug(f"Retry {attempt + 1}/{MAX_RETRIES} for price fetch: {e}")
                        continue
                    raise

        except Exception as e:
            logger.error(f"Error fetching current price for {symbol}: {e}")
            return None

    def _calculate_entry_readiness(self, current_price: float, buy_levels: List[float],
                                   sell_levels: List[float]) -> Dict:
        """
        次のエントリーレベル（買い・売り）と準備度を計算

        Args:
            current_price: 現在価格
            buy_levels: 買いレベルのリスト
            sell_levels: 売りレベルのリスト

        Returns:
            dict: {
                'next_buy_level': float or None,
                'next_sell_level': float or None,
                'distance_buy_pct': float,  # 負数 = 下降が必要
                'distance_sell_pct': float,
                'buy_readiness': str,  # 'READY', 'WARN', 'FAR'
                'sell_readiness': str,
            }
        """
        try:
            # 次の買いレベル（現在価格より下）
            next_buy = [lv for lv in sorted(buy_levels, reverse=True) if lv < current_price]
            next_buy_level = next_buy[0] if next_buy else (min(buy_levels) if buy_levels else None)

            # 次の売りレベル（現在価格より上）
            next_sell = [lv for lv in sorted(sell_levels) if lv > current_price]
            next_sell_level = next_sell[0] if next_sell else (max(sell_levels) if sell_levels else None)

            # 距離をパーセンテージで計算
            distance_buy_pct = ((next_buy_level - current_price) / current_price * 100) if next_buy_level else 0
            distance_sell_pct = ((next_sell_level - current_price) / current_price * 100) if next_sell_level else 0

            # 状態判定
            def _get_readiness(distance_pct: float) -> str:
                abs_dist = abs(distance_pct)
                if abs_dist <= READY_THRESHOLD:
                    return "READY"
                elif abs_dist <= WARN_THRESHOLD:
                    return "WARN"
                else:
                    return "FAR"

            return {
                'next_buy_level': next_buy_level,
                'next_sell_level': next_sell_level,
                'distance_buy_pct': distance_buy_pct,
                'distance_sell_pct': distance_sell_pct,
                'buy_readiness': _get_readiness(distance_buy_pct),
                'sell_readiness': _get_readiness(distance_sell_pct),
            }

        except Exception as e:
            logger.error(f"Error calculating entry readiness: {e}")
            return {
                'next_buy_level': None,
                'next_sell_level': None,
                'distance_buy_pct': 0,
                'distance_sell_pct': 0,
                'buy_readiness': 'FAR',
                'sell_readiness': 'FAR',
            }

    def _calculate_tp_sl_profit(self, current_price: float, next_buy_level: Optional[float],
                                next_sell_level: Optional[float], atr: Optional[float]) -> Dict:
        """
        TP (売りレベル)・SL (買いレベル) と利益推定を計算

        Args:
            current_price: 現在価格
            next_buy_level: 次の買いレベル（SL）
            next_sell_level: 次の売りレベル（TP）
            atr: ATR（平均真の値幅）

        Returns:
            dict: {
                'tp_price': float,
                'sl_price': float,
                'tp_profit_usd': float,
                'tp_profit_pct': float,
                'sl_loss_usd': float,
                'sl_loss_pct': float,
                'rr_ratio': float,  # リスク・リワード比
                'estimated_hours_to_tp': float,
                'estimated_hours_to_sl': float,
            }
        """
        try:
            tp_price = next_sell_level if next_sell_level else current_price
            sl_price = next_buy_level if next_buy_level else current_price

            # 利益・損失計算（エントリーが現在価格と仮定）
            tp_profit_usd = tp_price - current_price
            tp_profit_pct = (tp_profit_usd / current_price) * 100 if current_price > 0 else 0

            sl_loss_usd = current_price - sl_price
            sl_loss_pct = (sl_loss_usd / current_price) * 100 if current_price > 0 else 0

            # リスク・リワード比
            rr_ratio = tp_profit_usd / sl_loss_usd if sl_loss_usd > 0 else 0

            # 時間推定（ATR ベース）
            # 推定時間 = 距離 / (ATR / 24 時間)
            atr_per_hour = atr / 24.0 if atr and atr > 0 else 1.0
            estimated_hours_to_tp = abs(tp_profit_usd) / atr_per_hour if atr_per_hour > 0 else 0
            estimated_hours_to_sl = sl_loss_usd / atr_per_hour if atr_per_hour > 0 else 0

            return {
                'tp_price': float(tp_price),
                'sl_price': float(sl_price),
                'tp_profit_usd': float(tp_profit_usd),
                'tp_profit_pct': float(tp_profit_pct),
                'sl_loss_usd': float(sl_loss_usd),
                'sl_loss_pct': float(sl_loss_pct),
                'rr_ratio': float(rr_ratio),
                'estimated_hours_to_tp': float(estimated_hours_to_tp),
                'estimated_hours_to_sl': float(estimated_hours_to_sl),
            }

        except Exception as e:
            logger.error(f"Error calculating TP/SL/Profit: {e}")
            return {
                'tp_price': 0.0,
                'sl_price': 0.0,
                'tp_profit_usd': 0.0,
                'tp_profit_pct': 0.0,
                'sl_loss_usd': 0.0,
                'sl_loss_pct': 0.0,
                'rr_ratio': 0.0,
                'estimated_hours_to_tp': 0.0,
                'estimated_hours_to_sl': 0.0,
            }

    def update(self, symbol: str = "BTC") -> Dict:
        """
        データを更新し、すべての状態を返す

        Args:
            symbol: 取引シンボル（デフォルト: "BTC"）

        Returns:
            {
                "timestamp": datetime,
                "current_price": float,
                "ohlcv": pd.DataFrame（optional）,
                "indicators": {
                    "rsi": float,
                    "atr": float,
                    "atr_pct": float
                },
                "grid_state": {
                    "grid_center": float,
                    "grid_range": float,
                    "buy_levels": List[float],
                    "sell_levels": List[float],
                    "open_orders": int,
                    "filled_levels": List[int]
                },
                "entry_readiness": {
                    "next_buy_level": float or None,
                    "next_sell_level": float or None,
                    "distance_buy_pct": float,
                    "distance_sell_pct": float,
                    "buy_readiness": str,  # "READY", "WARN", "FAR"
                    "sell_readiness": str
                },
                "tp_sl_profit": {
                    "tp_price": float,
                    "sl_price": float,
                    "tp_profit_usd": float,
                    "tp_profit_pct": float,
                    "sl_loss_usd": float,
                    "sl_loss_pct": float,
                    "rr_ratio": float,
                    "estimated_hours_to_tp": float,
                    "estimated_hours_to_sl": float
                }
            }
        """
        try:
            self.last_update = datetime.now()

            # 1. 現在価格を取得
            self.current_price = self._fetch_current_price(symbol)
            if self.current_price is None:
                logger.warning(f"Could not fetch current price for {symbol}")
                return self._empty_state()

            # 2. OHLCV データを取得
            self.ohlcv_data = self._fetch_ohlcv(symbol)
            if self.ohlcv_data is None or len(self.ohlcv_data) < 2:
                logger.warning(f"Could not fetch OHLCV data for {symbol}")
                return self._empty_state()

            # 3. テクニカル指標を計算
            close_prices = self.ohlcv_data["close"].tolist()
            high_prices = self.ohlcv_data["high"].tolist()
            low_prices = self.ohlcv_data["low"].tolist()

            rsi = self._calculate_rsi(close_prices)
            atr = self._calculate_atr(high_prices, low_prices, close_prices)
            atr_pct = (atr / self.current_price * 100) if atr and self.current_price > 0 else 0.0

            self.indicators = {
                "rsi": rsi,
                "atr": atr,
                "atr_pct": atr_pct
            }

            # 4. グリッド状態を取得
            self.grid_state = self._get_grid_state()

            # 5. エントリー準備度を計算
            buy_levels = self.grid_state.get("buy_levels", [])
            sell_levels = self.grid_state.get("sell_levels", [])
            entry_readiness = self._calculate_entry_readiness(
                self.current_price,
                buy_levels,
                sell_levels
            )

            # 6. TP/SL/利益推定を計算
            tp_sl_profit = self._calculate_tp_sl_profit(
                self.current_price,
                entry_readiness.get('next_buy_level'),
                entry_readiness.get('next_sell_level'),
                atr
            )

            # 7. すべてをまとめて返す
            state = {
                "timestamp": self.last_update,
                "current_price": self.current_price,
                "ohlcv": self.ohlcv_data,
                "indicators": self.indicators,
                "grid_state": self.grid_state,
                "entry_readiness": entry_readiness,
                "tp_sl_profit": tp_sl_profit
            }

            logger.debug(f"State updated: price={self.current_price}, rsi={rsi}, atr={atr}")
            return state

        except Exception as e:
            logger.error(f"Error in update: {e}")
            return self._empty_state()

    def _empty_state(self) -> Dict:
        """エラー時の空の状態を返す"""
        return {
            "timestamp": datetime.now(),
            "current_price": None,
            "ohlcv": None,
            "indicators": {
                "rsi": None,
                "atr": None,
                "atr_pct": None
            },
            "grid_state": {
                "grid_center": None,
                "grid_range": None,
                "buy_levels": [],
                "sell_levels": [],
                "open_orders": 0,
                "filled_levels": []
            },
            "entry_readiness": {
                "next_buy_level": None,
                "next_sell_level": None,
                "distance_buy_pct": 0.0,
                "distance_sell_pct": 0.0,
                "buy_readiness": "FAR",
                "sell_readiness": "FAR"
            },
            "tp_sl_profit": {
                "tp_price": 0.0,
                "sl_price": 0.0,
                "tp_profit_usd": 0.0,
                "tp_profit_pct": 0.0,
                "sl_loss_usd": 0.0,
                "sl_loss_pct": 0.0,
                "rr_ratio": 0.0,
                "estimated_hours_to_tp": 0.0,
                "estimated_hours_to_sl": 0.0
            }
        }
