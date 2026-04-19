#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC/USDT RSI SWING v6 - LIVE TRADER
Hyperliquid 用 RSI(14) + EMA(50) + ATR(14) ベースのスイング戦略

戦略根拠: rsi_swing_trader_v6.py バックテスト
  WR 60%, PF 2.09, Sharpe 5.13, MaxDD -5.20%

Layer 1 - RSI Crossover: RSIが30以下→30上抜け(LONG) / RSIが70以上→70下抜け(SHORT)
Layer 2 - EMA Trend Filter: Close > EMA(50)(LONG) / Close < EMA(50)(SHORT)
Layer 3 - ATR Risk Management: SL = sl_atr * ATR(14), TP = tp_atr * ATR(14), Time Stop = max_bars

起動時に既存ポジションを検知し、現在価格からSL/TPを設定（即損切回避）
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests
import pandas as pd
import numpy as np


def setup_logging() -> logging.Logger:
    log_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"rsi_swing_{timestamp}.log")

    logger = logging.getLogger("RSI_SWING_TRADER")
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
    logger.info(" BTC/USDT RSI SWING v6 - LIVE TRADER")
    logger.info("=" * 70)
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Script file: {__file__}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 70)

    return logger


logger = setup_logging()


def load_config() -> Optional[Dict[str, Any]]:
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        if not os.path.exists(config_path):
            config = {
                "symbol": "BTC",
                "timeframe": "4h",
                "rsi_period": 14,
                "rsi_overbought": 70,
                "rsi_oversold": 30,
                "sl_atr": 1.5,
                "tp_atr": 3.0,
                "equity_usd": 10000,
                "risk_pct": 0.02,
                "leverage": 5,
                "check_interval": 60,
                "environment": "mainnet",
                "live_trading": True,
            }
            logger.warning("config.json not found. Using defaults.")
            return config

        with open(config_path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        cleaned_lines: List[str] = []
        for line in raw_lines:
            if "//" in line:
                line = line.split("//", 1)[0]
            cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        return json.loads(cleaned_text)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None


def ema_ind(series: pd.Series, period: int) -> np.ndarray:
    s = pd.Series(series)
    return s.ewm(span=period, adjust=False).mean().values


def rsi_ind(series: pd.Series, period: int = 14) -> np.ndarray:
    s = pd.Series(series)
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).values


def atr_ind(high: pd.Series, low: pd.Series, close: pd.Series,
            period: int = 14) -> np.ndarray:
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    pc = c.shift(1)
    tr = pd.concat(
        [
            h - l,
            (h - pc).abs(),
            (l - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    return atr.values


class HyperliquidRSISwingTrader:
    """
    RSI Swing 戦略 (rsi_swing_trader_v6.py ベース)

    LONG:  RSI(14) が 30以下 → 30上抜けクロス AND Close > EMA(50)
    SHORT: RSI(14) が 70以上 → 70下抜けクロス AND Close < EMA(50)
    SL = sl_atr * ATR(14), TP = tp_atr * ATR(14)
    Time Stop = max_bars 本
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.symbol = config.get("symbol", "BTC")
        self.timeframe = config.get("timeframe", "4h")
        self.rsi_period = int(config.get("rsi_period", 14))
        self.rsi_overbought = float(config.get("rsi_overbought", 70))
        self.rsi_oversold = float(config.get("rsi_oversold", 30))
        self.equity = float(config.get("equity_usd", 10_000))
        self.risk_pct = float(config.get("risk_pct", 0.02))
        self.sl_atr = float(config.get("sl_atr", 1.5))
        self.tp_atr = float(config.get("tp_atr", 3.0))
        self.leverage = float(config.get("leverage", 5))
        self.check_interval = int(config.get("check_interval", 60))

        self.environment = str(config.get("environment", "mainnet")).lower()
        if self.environment == "mainnet":
            self.base_url = "https://api.hyperliquid.xyz"
        else:
            self.base_url = "https://api.hyperliquid-testnet.xyz"

        self.session = requests.Session()

        self.live_trading: bool = bool(config.get("live_trading", False))
        self.account_address: Optional[str] = None
        self.exchange = None
        self.info = None

        self.in_position: bool = False
        self.position_side: Optional[str] = None
        self.entry_price: Optional[float] = None
        self.sl_price: Optional[float] = None
        self.tp_price: Optional[float] = None
        self.entry_bar_time: Optional[int] = None
        self.max_bars: int = int(config.get("max_bars", 20))

        if self.live_trading:
            try:
                import eth_account
                from eth_account.signers.local import LocalAccount
                from hyperliquid.exchange import Exchange
                from hyperliquid.info import Info

                secret_key: Optional[str] = config.get("secret_key") or config.get("api_secret")
                account_address_cfg: Optional[str] = config.get("account_address") or config.get("api_key")

                if not secret_key:
                    logger.error("live_trading=True but secret_key missing. Falling back to paper mode.")
                    self.live_trading = False
                else:
                    account: LocalAccount = eth_account.Account.from_key(secret_key)
                    self.account_address = account_address_cfg or account.address
                    self.info = Info(self.base_url, skip_ws=True)
                    self.exchange = Exchange(account, self.base_url, account_address=self.account_address)
                    logger.info(
                        f"Live trading enabled: env={self.environment}, address={self.account_address}"
                    )
            except Exception as e:
                logger.error(f"Hyperliquid SDK init failed: {e} -> paper mode")
                self.live_trading = False

        self._detect_existing_position()

        logger.info(
            f"Initialized RSI SWING trader for {self.symbol} {self.timeframe} "
            f"(rsi_period={self.rsi_period}, OS={self.rsi_oversold}, OB={self.rsi_overbought}, "
            f"SL={self.sl_atr}xATR, TP={self.tp_atr}xATR)"
        )

    def _detect_existing_position(self) -> None:
        if not (self.live_trading and self.info is not None):
            return
        try:
            state = self.info.user_state(self.account_address)
            for ap in state.get("assetPositions", []):
                pos = ap.get("position", {})
                if pos.get("coin") == self.symbol:
                    sz = float(pos.get("szi", "0"))
                    if abs(sz) > 0:
                        self.in_position = True
                        self.position_side = "long" if sz > 0 else "short"
                        self.entry_price = float(pos.get("entryPx", "0"))
                        logger.info(
                            "Existing position detected: %s %.6f %s @ $%.2f (SL/TP will be set from current price)",
                            self.position_side.upper(), abs(sz), self.symbol, self.entry_price,
                        )
                        return
            logger.info("No existing open position on Hyperliquid.")
        except Exception as e:
            logger.warning("Could not check existing positions: %s (will retry on next cycle)", e)

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        try:
            url = f"{self.base_url}{endpoint}"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "HyperliquidRSISwing/1.0",
            }
            if method == "GET":
                resp = self.session.get(url, headers=headers)
            else:
                resp = self.session.post(url, headers=headers, json=data)
            if resp.status_code == 200:
                return resp.json()
            logger.error("API error %s: %s", resp.status_code, resp.text)
            return {"error": resp.text}
        except Exception as e:
            logger.error("Request error: %s", e)
            return {"error": str(e)}

    def get_candles(self, limit: int = 100) -> List[Dict]:
        try:
            interval_ms_map = {
                "1m": 60_000, "3m": 3 * 60_000, "5m": 5 * 60_000,
                "15m": 15 * 60_000, "30m": 30 * 60_000,
                "1h": 60 * 60_000, "2h": 2 * 60 * 60_000,
                "4h": 4 * 60 * 60_000, "8h": 8 * 60 * 60_000,
                "12h": 12 * 60 * 60_000, "1d": 24 * 60 * 60_000,
            }
            interval_ms = interval_ms_map.get(self.timeframe, 4 * 60 * 60_000)
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - limit * interval_ms

            data = {
                "type": "candleSnapshot",
                "req": {
                    "coin": self.symbol,
                    "interval": self.timeframe,
                    "startTime": start_ms,
                    "endTime": now_ms,
                },
            }
            resp = self._make_request("POST", "/info", data)
            if isinstance(resp, dict) and "error" in resp:
                logger.error("Error fetching candles: %s", resp["error"])
                return []

            candles: List[Dict[str, Any]] = []
            for c in resp:
                try:
                    candles.append(
                        {
                            "timestamp": int(c.get("t")),
                            "open": float(c.get("o", 0)),
                            "high": float(c.get("h", 0)),
                            "low": float(c.get("l", 0)),
                            "close": float(c.get("c", 0)),
                            "volume": float(c.get("v", 0)),
                        }
                    )
                except Exception as e:
                    logger.error("Error parsing candle: %s raw=%s", e, c)
            return candles
        except Exception as e:
            logger.error("Error processing candles: %s", e)
            return []

    def _calc_rsi_ema_atr(self, candles: List[Dict]) -> Optional[Dict[str, float]]:
        if len(candles) < max(self.rsi_period, 50, 14) + 2:
            return None
        df = pd.DataFrame(candles)
        close = df["close"]
        high = df["high"]
        low = df["low"]

        rsi_vals = rsi_ind(close, self.rsi_period)
        ema_vals = ema_ind(close, 50)
        atr_vals = atr_ind(high, low, close, 14)

        return {
            "rsi_now": float(rsi_vals[-1]),
            "rsi_prev": float(rsi_vals[-2]),
            "ema_now": float(ema_vals[-1]),
            "atr_now": float(atr_vals[-1]),
        }

    def _place_entry_order(self, side_long: bool, qty: float, price: float) -> bool:
        """
        エントリー注文を発注。IOC指値（実質成行）。
        成功したら True、失敗したら False を返す。
        """
        if not (self.live_trading and self.exchange is not None):
            return True  # paper mode は常に成功扱い
        try:
            # IOC指値 = 実質成行（best ask/bidに対してスリッページ付き）
            slippage = 0.05  # 5%
            if side_long:
                limit_px = round(price * (1 + slippage), 1)
            else:
                limit_px = round(price * (1 - slippage), 1)

            order_type = {"limit": {"tif": "Ioc"}}
            logger.info(
                "[LIVE] Entry order: %s coin=%s qty=%.6f limit_px=%.2f",
                "BUY" if side_long else "SELL",
                self.symbol, qty, limit_px,
            )
            resp = self.exchange.order(
                self.symbol, side_long, float(qty), float(limit_px),
                order_type, reduce_only=False,
            )
            logger.info("[LIVE] Entry order response: %s", resp)
            # レスポンスチェック: statuses[0].filled があれば成功
            statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
            if statuses and "filled" in statuses[0]:
                return True
            elif statuses and "error" in statuses[0]:
                logger.error("[LIVE] Entry order rejected: %s", statuses[0]["error"])
                return False
            return True  # レスポンス構造が不明な場合は楽観的に成功扱い
        except Exception as e:
            logger.error("[LIVE] Entry order failed: %s", e)
            return False

    def _place_tp_sl_orders(self, side_long: bool, qty: float,
                             tp_price: float, sl_price: float) -> None:
        """
        TP・SL のtrigger注文を取引所に発注。
        失敗時はソフトウェア監視にフォールバック（エラーログのみ）。
        """
        if not (self.live_trading and self.exchange is not None):
            return

        # TP注文: reduce_only=True, trigger注文
        try:
            tp_order_type = {
                "trigger": {
                    "triggerPx": float(tp_price),
                    "isMarket": True,
                    "tpsl": "tp",
                }
            }
            # TP: LONGならSELL(is_buy=False)、SHORTならBUY(is_buy=True)
            tp_is_buy = not side_long
            logger.info(
                "[LIVE] TP order: triggerPx=%.2f is_buy=%s qty=%.6f",
                tp_price, tp_is_buy, qty,
            )
            tp_resp = self.exchange.order(
                self.symbol, tp_is_buy, float(qty), float(tp_price),
                tp_order_type, reduce_only=True,
            )
            logger.info("[LIVE] TP order response: %s", tp_resp)
        except Exception as e:
            logger.error("[LIVE] TP order failed (fallback to software monitor): %s", e)

        # SL注文: reduce_only=True, trigger注文
        try:
            sl_order_type = {
                "trigger": {
                    "triggerPx": float(sl_price),
                    "isMarket": True,
                    "tpsl": "sl",
                }
            }
            sl_is_buy = not side_long
            logger.info(
                "[LIVE] SL order: triggerPx=%.2f is_buy=%s qty=%.6f",
                sl_price, sl_is_buy, qty,
            )
            sl_resp = self.exchange.order(
                self.symbol, sl_is_buy, float(qty), float(sl_price),
                sl_order_type, reduce_only=True,
            )
            logger.info("[LIVE] SL order response: %s", sl_resp)
        except Exception as e:
            logger.error("[LIVE] SL order failed (fallback to software monitor): %s", e)

    def _place_close_order(self, side_long: bool, qty: float, price: float) -> None:
        """ポジションクローズ注文（IOC指値 reduce_only=True）"""
        if not (self.live_trading and self.exchange is not None):
            return
        try:
            slippage = 0.05
            if side_long:
                limit_px = round(price * (1 + slippage), 1)
            else:
                limit_px = round(price * (1 - slippage), 1)
            order_type = {"limit": {"tif": "Ioc"}}
            logger.info(
                "[LIVE] Close order: %s coin=%s qty=%.6f limit_px=%.2f",
                "BUY" if side_long else "SELL",
                self.symbol, qty, limit_px,
            )
            resp = self.exchange.order(
                self.symbol, side_long, float(qty), float(limit_px),
                order_type, reduce_only=True,
            )
            logger.info("[LIVE] Close order response: %s", resp)
        except Exception as e:
            logger.error("[LIVE] Close order failed: %s", e)

    def _calc_qty(self, atr_now: float) -> float:
        sl_dist = atr_now * self.sl_atr
        if sl_dist <= 0:
            return 0.0
        return (self.equity * self.risk_pct) / sl_dist

    def run(self) -> None:
        mode = "live" if (self.live_trading and self.exchange is not None) else "paper"
        logger.info("Starting RSI SWING trading loop (%s mode)...", mode)

        while True:
            try:
                candles = self.get_candles(200)
                if not candles:
                    logger.error("No candle data. Sleeping %d seconds.", self.check_interval)
                    time.sleep(self.check_interval)
                    continue

                latest = candles[-1]
                bar_time = int(latest["timestamp"])
                price = float(latest["close"])

                ind = self._calc_rsi_ema_atr(candles)
                if not ind:
                    logger.info("Not enough history for indicators. Sleeping...")
                    time.sleep(self.check_interval)
                    continue

                rsi_now = ind["rsi_now"]
                rsi_prev = ind["rsi_prev"]
                ema_now = ind["ema_now"]
                atr_now = ind["atr_now"]

                logger.info(
                    "BAR %s | Price=%.2f RSI=%.2f (prev=%.2f) EMA50=%.2f ATR14=%.2f",
                    datetime.fromtimestamp(bar_time / 1000).isoformat(),
                    price,
                    rsi_now,
                    rsi_prev,
                    ema_now,
                    atr_now,
                )

                if self.in_position and self.entry_price is not None:
                    if self.sl_price is None and atr_now > 0:
                        sl_dist = atr_now * self.sl_atr
                        tp_dist = atr_now * self.tp_atr
                        if self.position_side == "long":
                            self.sl_price = price - sl_dist
                            self.tp_price = price + tp_dist
                        elif self.position_side == "short":
                            self.sl_price = price + sl_dist
                            self.tp_price = price - tp_dist
                        logger.info(
                            "SL/TP set from CURRENT price for inherited position: "
                            "entry=%.2f cur=%.2f SL=%.2f TP=%.2f",
                            self.entry_price, price, self.sl_price, self.tp_price,
                        )
                        self._print_position_summary(price, atr_now)

                        # 既存ポジション用のTP/SL注文を取引所に送信
                        qty = self._calc_qty(atr_now)
                        side_long = (self.position_side == "long")
                        self._place_tp_sl_orders(side_long, qty, self.tp_price, self.sl_price)

                    bars_held = 0
                    if self.entry_bar_time is not None:
                        bars_held = sum(1 for c in candles if c["timestamp"] >= self.entry_bar_time)

                    qty = self._calc_qty(atr_now)

                    if self.position_side == "long":
                        if self.sl_price is not None and price <= self.sl_price:
                            logger.info("LONG SL hit: price=%.2f <= SL=%.2f", price, self.sl_price)
                            self._place_close_order(False, qty, price)
                            self._close_position(price)
                        elif self.tp_price is not None and price >= self.tp_price:
                            logger.info("LONG TP hit: price=%.2f >= TP=%.2f", price, self.tp_price)
                            self._place_close_order(False, qty, price)
                            self._close_position(price)
                        elif bars_held >= self.max_bars:
                            logger.info("LONG time stop reached (%d bars).", bars_held)
                            self._place_close_order(False, qty, price)
                            self._close_position(price)

                    elif self.position_side == "short":
                        if self.sl_price is not None and price >= self.sl_price:
                            logger.info("SHORT SL hit: price=%.2f >= SL=%.2f", price, self.sl_price)
                            self._place_close_order(True, qty, price)
                            self._close_position(price, short=True)
                        elif self.tp_price is not None and price <= self.tp_price:
                            logger.info("SHORT TP hit: price=%.2f <= TP=%.2f", price, self.tp_price)
                            self._place_close_order(True, qty, price)
                            self._close_position(price, short=True)
                        elif bars_held >= self.max_bars:
                            logger.info("SHORT time stop reached (%d bars).", bars_held)
                            self._place_close_order(True, qty, price)
                            self._close_position(price, short=True)

                if self.in_position:
                    logger.info(
                        "In position (%s). SL=%.2f TP=%.2f | Entry=%.2f Cur=%.2f",
                        self.position_side,
                        self.sl_price or 0.0,
                        self.tp_price or 0.0,
                        self.entry_price or 0.0,
                        price,
                    )
                    time.sleep(self.check_interval)
                    continue

                long_signal = (
                    rsi_prev <= self.rsi_oversold
                    and rsi_now > self.rsi_oversold
                    and price > ema_now
                )
                short_signal = (
                    rsi_prev >= self.rsi_overbought
                    and rsi_now < self.rsi_overbought
                    and price < ema_now
                )

                if long_signal:
                    self._open_position("long", price, atr_now, bar_time)
                elif short_signal:
                    self._open_position("short", price, atr_now, bar_time)
                else:
                    logger.info("No entry signal.")

                logger.info("Sleeping for %d seconds...", self.check_interval)
                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                logger.info("RSI SWING trading loop stopped by user.")
                break
            except Exception as e:
                logger.error("Error in RSI SWING loop: %s", e)
                logger.info("Retrying in %d seconds...", self.check_interval)
                time.sleep(self.check_interval)

    def _open_position(self, side: str, price: float, atr_now: float, bar_time: int) -> None:
        sl_dist = atr_now * self.sl_atr
        tp_dist = atr_now * self.tp_atr
        qty = (self.equity * self.risk_pct) / sl_dist if sl_dist > 0 else 0.0
        side_long = (side == "long")

        if side_long:
            self.sl_price = price - sl_dist
            self.tp_price = price + tp_dist
        else:
            self.sl_price = price + sl_dist
            self.tp_price = price - tp_dist

        logger.info(
            "OPEN %s @ %.2f | SL=%.2f TP=%.2f qty_est=%.6f",
            side.upper(), price, self.sl_price, self.tp_price, qty,
        )

        # エントリー注文送信
        entry_ok = self._place_entry_order(side_long, qty, price)

        if entry_ok:
            # エントリー成功後にTP/SL注文を取引所に送信
            self._place_tp_sl_orders(side_long, qty, self.tp_price, self.sl_price)
        else:
            logger.error("Entry order failed. Position not opened.")
            self.sl_price = None
            self.tp_price = None
            return

        self.in_position = True
        self.position_side = side
        self.entry_price = price
        self.entry_bar_time = bar_time

    def _close_position(self, price: float, short: bool = False) -> None:
        if self.entry_price is None:
            self.in_position = False
            self.position_side = None
            self.sl_price = None
            self.tp_price = None
            self.entry_bar_time = None
            return

        direction = -1 if short else 1
        pnl_per_unit = (price - self.entry_price) * direction
        sl_dist = abs(self.entry_price - (self.sl_price or self.entry_price))
        qty = (self.equity * self.risk_pct) / (sl_dist if sl_dist > 0 else 1.0)
        pnl = pnl_per_unit * qty * self.leverage
        self.equity += pnl

        logger.info(
            "CLOSE %s @ %.2f (entry=%.2f) | qty_est=%.6f PnL=%.2f new_equity=%.2f",
            "SHORT" if short else "LONG",
            price,
            self.entry_price,
            qty,
            pnl,
            self.equity,
        )

        self.in_position = False
        self.position_side = None
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None
        self.entry_bar_time = None



    def _print_position_summary(self, price: float, atr_now: float) -> None:
        if self.entry_price is None:
            return
        sl_to_entry = abs(price - self.entry_price)
        tp_to_entry = abs((self.tp_price or self.entry_price)) if self.tp_price else 0.0
        rr_ratio = tp_to_entry / sl_to_entry if sl_to_entry > 0 else 0.0

        if self.position_side == "long":
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
        else:
            pnl_pct = (self.entry_price - price) / self.entry_price * 100

        sl_display = "$%.2f" % self.sl_price if self.sl_price else "N/A"
        tp_display = "$%.2f" % self.tp_price if self.tp_price else "N/A"

        logger.info("=" * 50)
        logger.info("  POSITION SUMMARY (%s)", self.position_side.upper())
        logger.info("  | %-14s | $%-14.2f", "Current", price)
        logger.info("  | %-14s | $%-14.2f", "Entry", self.entry_price)
        logger.info("  | %-14s | %s", "SL", sl_display)
        logger.info("  | %-14s | %s", "TP", tp_display)
        logger.info("  | %-14s | %.1fx ATR / %.1fx ATR", "SL/TP", self.sl_atr, self.tp_atr)
        logger.info("  | %-14s | $%.2f", "SL->Entry", sl_to_entry)
        logger.info("  | %-14s | $%.2f", "TP->Entry", tp_to_entry)
        logger.info("  | %-14s | %.1f", "R:R", rr_ratio)
        logger.info("  | %-14s | %+.2f%%", "Unrealized PnL", pnl_pct)
        logger.info("  | %-14s | %d bars", "Max Hold", self.max_bars)
        logger.info("=" * 50)


if __name__ == "__main__":
    try:
        cfg = load_config()
        if not cfg:
            print("Error: failed to load config.json")
            sys.exit(1)
        trader = HyperliquidRSISwingTrader(cfg)
        logger.info("RSI SWING trader initialized successfully")
        print("RSI SWING trading loop ready to start...")
        trader.run()
    except Exception as e:
        logger.error("Fatal error in RSI SWING trader: %s", e)
        print(f"Error: {e}")

