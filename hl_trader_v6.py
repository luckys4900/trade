# -*- coding: utf-8 -*-
"""
BTC/USDT 4H ADAPTIVE RSI v5 - LIVE TRADER
Simplified version that works reliably with batch files
"""

import os
import sys
import json
import logging
import time
import datetime as dt
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
import requests
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from pathlib import Path

def setup_logging():
    """Setup logging to both console and file"""
    # Create log directory
    log_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create log filename with timestamp
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"trader_{timestamp}.log")

    # Write startup log
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "message": "Trader process started"
    }
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
        f.flush()

    # Setup logging
    logger = logging.getLogger("Trader")
    logger.setLevel(logging.DEBUG)
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger, log_file

logger, log_file = setup_logging()
logger.info("=" * 70)
logger.info(" BTC/USDT 4H ADAPTIVE RSI v5 - LIVE TRADER")
logger.info("=" * 70)
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"Script file: {__file__}")
logger.info(f"Log file: {log_file}")
logger.info("=" * 70)

# Load configuration
def load_config():
    """config.json を UTF-8 で読み込み、行末コメント // を許容してパースする。"""
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        if not os.path.exists(config_path):
            # Default configuration (paper / test mode)
            config = {
                "symbol": "BTC",
                "timeframe": "4h",
                "rsi_period": 14,
                "rsi_overbought": 70,
                "rsi_oversold": 30,
                "position_size_usd": 100,
                "max_positions": 1,
                "leverage": 10,
                "check_interval": 60,
                "environment": "testnet",
                "live_trading": False,
            }
            logger.warning("config.json が見つからないためデフォルト設定を使用します（paper/testnet）。")
            return config

        # UTF-8 で読み込み、日本語コメント付きでも動くように // 以降を削除
        with open(config_path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        cleaned_lines = []
        for line in raw_lines:
            # 非常にシンプルなコメント除去: // があればそこから右を切り捨て
            # （値の中に // が入るケースは今回想定しない）
            if "//" in line:
                line = line.split("//", 1)[0]
            cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        return json.loads(cleaned_text)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

class HyperliquidTrader:
    """Hyperliquid trading bot with adaptive RSI strategy"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("symbol", "BTC")
        self.timeframe = config.get("timeframe", "4h")
        self.rsi_period = config.get("rsi_period", 14)
        self.rsi_overbought = config.get("rsi_overbought", 70)
        self.rsi_oversold = config.get("rsi_oversold", 30)
        self.position_size_usd = config.get("position_size_usd", 100)
        self.max_positions = config.get("max_positions", 1)
        self.leverage = config.get("leverage", 10)
        self.check_interval = config.get("check_interval", 60)
        self.session = requests.Session()
        # network / environment
        self.environment: str = str(config.get("environment", "testnet")).lower()
        # base URL for REST requests (aligns with environment)
        if self.environment == "mainnet":
            self.base_url: str = "https://api.hyperliquid.xyz"
        else:
            self.base_url = "https://api.hyperliquid-testnet.xyz"

        # paper-trading state
        self.in_position: bool = False
        self.entry_price: Optional[float] = None

        # live trading (Hyperliquid SDK); initialized lazily
        self.live_trading: bool = bool(config.get("live_trading", False))
        self.account_address: Optional[str] = None
        self.info = None
        self.exchange = None

        if self.live_trading:
            try:
                import eth_account  # type: ignore[import]
                from eth_account.signers.local import LocalAccount  # type: ignore[import]
                from hyperliquid.exchange import Exchange  # type: ignore[import]
                from hyperliquid.info import Info  # type: ignore[import]

                # Try environment variable first, then config
                secret_key: Optional[str] = os.getenv("HYPERLIQUID_SECRET_KEY") or config.get("secret_key") or config.get("api_secret")  # type: ignore[assignment]
                account_address_cfg: Optional[str] = os.getenv("HYPERLIQUID_ADDRESS") or config.get("account_address") or config.get("api_key")  # type: ignore[assignment]

                if not secret_key:
                    logger.error("live_trading=True だが秘密鍵が見つかりません。paper モードにフォールバックします。")
                    logger.error("  環境変数 HYPERLIQUID_SECRET_KEY または config.json の secret_key を設定してください。")
                    self.live_trading = False
                else:
                    logger.info(f"[DEBUG] Secret key length: {len(secret_key)}")
                    logger.info(f"[DEBUG] Account address: {account_address_cfg}")

                    account: LocalAccount = eth_account.Account.from_key(secret_key)
                    self.account_address = account_address_cfg or account.address

                    logger.info(f"[DEBUG] Derived account address: {account.address}")
                    logger.info(f"[DEBUG] Using account address: {self.account_address}")

                    # SDK Info / Exchange は self.base_url をそのまま利用
                    self.info = Info(self.base_url, skip_ws=True)
                    self.exchange = Exchange(account, self.base_url, account_address=self.account_address)
                    logger.info(
                        f"Live trading 有効化: env={self.environment}, address={self.account_address}"
                    )
            except Exception as e:
                logger.error(f"Hyperliquid SDK 初期化に失敗: {e}. paper モードにフォールバックします。")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                self.live_trading = False
        
        logger.info(f"Initialized trader for {self.symbol} with {self.timeframe} timeframe")
        logger.info(f"RSI settings: period={self.rsi_period}, overbought={self.rsi_overbought}, oversold={self.rsi_oversold}")
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make API request to Hyperliquid"""
        try:
            base_url = getattr(self, "base_url", "https://api.hyperliquid.xyz")
            url = f"{base_url}{endpoint}"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "HyperliquidTrader/1.0"
            }
            
            if method == "GET":
                response = self.session.get(url, headers=headers)
            elif method == "POST":
                response = self.session.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                return {"error": response.text}
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {"error": str(e)}
    
    def get_candles(self, limit: int = 100) -> List[Dict]:
        """Get recent candlestick data from Hyperliquid /info candleSnapshot."""
        try:
            # map timeframe to milliseconds
            interval_ms_map = {
                "1m": 60_000,
                "3m": 3 * 60_000,
                "5m": 5 * 60_000,
                "15m": 15 * 60_000,
                "30m": 30 * 60_000,
                "1h": 60 * 60_000,
                "2h": 2 * 60 * 60_000,
                "4h": 4 * 60 * 60_000,
                "8h": 8 * 60 * 60_000,
                "12h": 12 * 60 * 60_000,
                "1d": 24 * 60 * 60_000,
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
            # official endpoint is /info for candleSnapshot
            response = self._make_request("POST", "/info", data)

            if isinstance(response, dict) and "error" in response:
                logger.error(f"Error fetching candles: {response['error']}")
                return []

            candles: List[Dict[str, Any]] = []
            for candle in response:
                try:
                    candles.append(
                        {
                            "timestamp": candle.get("t"),
                            "open": float(candle.get("o", 0)),
                            "high": float(candle.get("h", 0)),
                            "low": float(candle.get("l", 0)),
                            "close": float(candle.get("c", 0)),
                            "volume": float(candle.get("v", 0)),
                        }
                    )
                except Exception as inner_e:  # noqa: BLE001
                    logger.error(f"Error parsing candle: {inner_e} - raw: {candle}")

            return candles
        except Exception as e:
            logger.error(f"Error processing candles: {e}")
            return []
    
    def calculate_rsi(self, candles: List[Dict], period: int = None) -> float:
        """Calculate RSI (Relative Strength Index)"""
        if period is None:
            period = self.rsi_period
            
        if len(candles) < period + 1:
            return 50.0  # Neutral RSI if not enough data
        
        try:
            df = pd.DataFrame(candles)
            closes = df['close']
            
            # Calculate price differences
            delta = closes.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            # Calculate average gain and loss
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            # Calculate RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return float(rsi.iloc[-1])
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return 50.0
    
    def get_positions(self) -> List[Dict]:
        """Get current positions"""
        try:
            data = {"type": "clearinghouse"}
            response = self._make_request("POST", "/exchange", data)
            
            if "error" in response:
                logger.error(f"Error fetching positions: {response['error']}")
                return []
            
            positions = []
            for pos in response.get("assetPositions", []):
                if pos.get("position", {}).get("coin") == self.symbol:
                    positions.append(pos.get("position", {}))
            
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def place_order(self, side: str, size_usd: float, reduce_only: bool = False) -> Dict:
        """Place an order"""
        try:
            # Get current price to calculate quantity
            candles = self.get_candles(1)
            if not candles:
                logger.error("Cannot get current price")
                return {"error": "Cannot get current price"}
            
            current_price = candles[-1]["close"]
            quantity = size_usd / current_price
            
            data = {
                "coin": self.symbol,
                "side": side,
                "orderType": "market",
                "sz": str(quantity),
                "reduceOnly": reduce_only
            }
            
            logger.info(f"Placing {side} order: size=${size_usd:.2f} (qty={quantity:.6f})")
            
            # In a real implementation, you would sign the request with your API key/secret
            # This is a simplified version without authentication
            response = self._make_request("POST", "/exchange", data)
            
            if "error" in response:
                logger.error(f"Order error: {response['error']}")
                return {"error": response['error']}
            
            logger.info(f"Order placed successfully: {response}")
            return response
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {"error": str(e)}
    
    def get_account_info(self) -> Dict:
        """Get account information"""
        try:
            data = {"type": "user"}
            response = self._make_request("POST", "/info", data)
            
            if "error" in response:
                logger.error(f"Error fetching account info: {response['error']}")
                return {}
            
            return response
        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            return {}
    
    def run(self) -> None:
        """Main trading loop.

        - live_trading=True かつ Hyperliquid SDK 初期化済みなら、本番注文を送信
        - それ以外は紙トレード（ログのみ）として動作
        """
        mode = "live" if (self.live_trading and self.exchange is not None) else "paper"
        logger.info(f"Starting trading loop ({mode} mode)...")

        while True:
            try:
                # Get candle data
                candles = self.get_candles(100)
                if not candles:
                    logger.error("No candle data available")
                    time.sleep(self.check_interval)
                    continue

                # Calculate RSI
                current_rsi = self.calculate_rsi(candles)
                current_price = candles[-1]["close"]

                logger.info(f"Current RSI: {current_rsi:.2f}, Price: ${current_price:.2f}")

                is_live = self.live_trading and self.exchange is not None

                # Trading logic
                if not self.in_position:
                    if current_rsi <= self.rsi_oversold:
                        if is_live:
                            # --- LIVE BUY ---
                            try:
                                # Use Decimal for precise calculation
                                qty_decimal = Decimal(str(self.position_size_usd)) / Decimal(str(current_price))
                                # Quantize to 4 decimal places (BTC precision)
                                qty_decimal = qty_decimal.quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
                                qty = float(qty_decimal)
                                order_type = {"limit": {"tif": "Ioc"}}  # IOC (Immediate or Cancel) order
                                logger.info(
                                    f"[LIVE] Placing BUY: coin={self.symbol}, qty={qty:.4f}, "
                                    f"price=${float(current_price):.2f}, order_type={order_type}"
                                )
                                resp = self.exchange.order(
                                    self.symbol,
                                    True,
                                    qty,
                                    float(current_price),
                                    order_type,
                                    reduce_only=False,
                                )
                                logger.info(f"[LIVE] BUY order response: {resp}")
                                self.in_position = True
                                self.entry_price = current_price
                            except Exception as order_err:  # noqa: BLE001
                                logger.error(f"[LIVE] BUY order failed: {order_err}")
                                import traceback
                                logger.error(f"[LIVE] BUY traceback: {traceback.format_exc()}")
                        else:
                            # --- PAPER BUY ---
                            logger.info(
                                f"[PAPER] BUY signal: RSI {current_rsi:.2f} <= {self.rsi_oversold} "
                                "(paper position opened, no real order sent)"
                            )
                            self.in_position = True
                            self.entry_price = current_price
                    else:
                        logger.info("No signal (neutral/bearish, flat)")
                else:
                    if current_rsi >= self.rsi_overbought:
                        if is_live:
                            # --- LIVE SELL (reduce-only) ---
                            try:
                                # Use Decimal for precise calculation
                                qty_decimal = Decimal(str(self.position_size_usd)) / Decimal(str(current_price))
                                # Quantize to 4 decimal places (BTC precision)
                                qty_decimal = qty_decimal.quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
                                qty = float(qty_decimal)
                                order_type = {"limit": {}}
                                logger.info(
                                    f"[LIVE] Placing SELL (reduce-only): coin={self.symbol}, "
                                    f"qty={qty:.4f}, notional~${self.position_size_usd:.2f}"
                                )
                                resp = self.exchange.order(
                                    self.symbol,
                                    False,
                                    qty,
                                    float(current_price),
                                    order_type,
                                    reduce_only=True,
                                )
                                logger.info(f"[LIVE] SELL order response: {resp}")
                            except Exception as order_err:  # noqa: BLE001
                                logger.error(f"[LIVE] SELL order failed: {order_err}")
                                import traceback
                                logger.error(f"[LIVE] SELL traceback: {traceback.format_exc()}")

                        # ローカルのポジション状態は live/paper 共通でクローズ
                        pnl = 0.0
                        if self.entry_price:
                            pnl = (current_price - self.entry_price) * self.leverage
                        logger.info(
                            f"Position closed: est. PnL per 1x notional: {pnl:.2f} "
                            f"(entry={self.entry_price}, exit={current_price})"
                        )
                        self.in_position = False
                        self.entry_price = None
                    else:
                        logger.info("Holding position (no sell signal)")

                # Sleep until next check
                logger.info(f"Sleeping for {self.check_interval} seconds...")
                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                logger.info("Trading loop stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                logger.info(f"Retrying in {self.check_interval} seconds...")
                time.sleep(self.check_interval)

# Test debug logging
test_message = "Trader is running"
logger.info(f"Test message: {test_message}")
print(f"Trader started. Log file: {log_file}")

# Initialize and run trader
try:
    config = load_config()
    if config:
        trader = HyperliquidTrader(config)
        logger.info("Trader initialized successfully")
        print("Trading loop ready to start...")
        trader.run()
    else:
        logger.error("Failed to load configuration")
        print("Error: Failed to load configuration")
except Exception as e:
    logger.error(f"Error initializing trader: {e}")
    print(f"Error: {e}")

# Keep the script running
try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    logger.info("Trader stopped by user")
    print("Trader stopped.")

class HyperliquidBacktester:
    """Backtesting class for Hyperliquid trading strategy"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("symbol", "BTC")
        self.timeframe = config.get("timeframe", "4h")
        self.rsi_period = config.get("rsi_period", 14)
        self.rsi_overbought = config.get("rsi_overbought", 70)
        self.rsi_oversold = config.get("rsi_oversold", 30)
        self.position_size_usd = config.get("position_size_usd", 100)
        self.max_positions = config.get("max_positions", 1)
        self.leverage = config.get("leverage", 10)
        
        # Backtest specific parameters
        self.initial_balance = 10000.0  # Initial balance in USD
        self.slippage_percent = 0.05    # Slippage in percentage
        self.fee_percent = 0.02         # Fee in percentage
        
        # Trading state
        self.balance = self.initial_balance
        self.positions = []
        self.trades = []
        self.equity_curve = [self.initial_balance]
        
        logger.info(f"Initialized backtester for {self.symbol} with ${self.initial_balance:.2f}")
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make API request to Hyperliquid"""
        try:
            url = f"https://api.hyperliquid.xyz{endpoint}"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "HyperliquidBacktester/1.0"
            }
            
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                return {"error": response.text}
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {"error": str(e)}
    
    def get_historical_candles(self, days: int = 365) -> List[Dict]:
        """Get historical candlestick data for backtesting"""
        try:
            # Calculate the number of candles needed
            if self.timeframe == "4h":
                candles_per_day = 6
                limit = int(days * candles_per_day)
            elif self.timeframe == "1h":
                candles_per_day = 24
                limit = int(days * candles_per_day)
            elif self.timeframe == "1d":
                limit = days
            else:
                # Default to 4h
                candles_per_day = 6
                limit = int(days * candles_per_day)
            
            # Fetch candles
            data = {
                "coin": self.symbol,
                "interval": self.timeframe,
                "limit": limit
            }
            response = self._make_request("POST", "/info/candle", data)
            
            if "error" in response:
                logger.error(f"Error fetching candles: {response['error']}")
                return []
            
            # Process candle data
            candles = []
            for candle in response:
                candles.append({
                    "timestamp": candle.get("t"),
                    "open": float(candle.get("o", 0)),
                    "high": float(candle.get("h", 0)),
                    "low": float(candle.get("l", 0)),
                    "close": float(candle.get("c", 0)),
                    "volume": float(candle.get("v", 0))
                })
            
            # Sort by timestamp (ascending order)
            candles.sort(key=lambda x: x["timestamp"])
            
            logger.info(f"Fetched {len(candles)} historical candles")
            return candles
        except Exception as e:
            logger.error(f"Error fetching historical candles: {e}")
            return []
    
    def calculate_rsi(self, candles: List[Dict], period: int = None) -> float:
        """Calculate RSI (Relative Strength Index)"""
        if period is None:
            period = self.rsi_period
            
        if len(candles) < period + 1:
            return 50.0  # Neutral RSI if not enough data
        
        try:
            df = pd.DataFrame(candles)
            closes = df['close']
            
            # Calculate price differences
            delta = closes.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            # Calculate average gain and loss
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            # Calculate RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return float(rsi.iloc[-1])
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return 50.0
    
    def execute_trade(self, candle: Dict, side: str, rsi: float):
        """Execute a trade in backtesting"""
        try:
            price = candle["close"]
            
            # Apply slippage
            if side == "buy":
                price = price * (1 + self.slippage_percent / 100)
            else:
                price = price * (1 - self.slippage_percent / 100)
            
            # Calculate quantity
            quantity = self.position_size_usd / price
            
            # Calculate fees
            fee_amount = self.position_size_usd * (self.fee_percent / 100)
            
            # Create trade record
            trade = {
                "timestamp": candle["timestamp"],
                "datetime": datetime.fromtimestamp(candle["timestamp"]),
                "side": side,
                "price": price,
                "quantity": quantity,
                "size_usd": self.position_size_usd,
                "fee_usd": fee_amount,
                "rsi": rsi,
                "balance_before": self.balance
            }
            
            # Update balance
            if side == "buy":
                self.balance -= (self.position_size_usd + fee_amount)
                self.positions.append(trade)
                logger.info(f"BUY: Price=${price:.2f}, Size=${self.position_size_usd:.2f}, RSI={rsi:.2f}")
            else:  # sell
                # Calculate profit/loss
                if self.positions:
                    last_buy = self.positions[-1]
                    entry_price = last_buy["price"]
                    pnl = (price - entry_price) * quantity * self.leverage
                    self.balance += (self.position_size_usd + pnl - fee_amount)
                    
                    trade["entry_price"] = entry_price
                    trade["pnl"] = pnl
                    trade["profit_pct"] = (pnl / self.position_size_usd) * 100
                    
                    logger.info(f"SELL: Price=${price:.2f}, PNL=${pnl:.2f} ({trade['profit_pct']:.2f}%), RSI={rsi:.2f}")
                else:
                    # No position to sell
                    return
            
            trade["balance_after"] = self.balance
            self.trades.append(trade)
            self.equity_curve.append(self.balance)
            
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
    
    def run_backtest(self, days: int = 365) -> Dict[str, Any]:
        """Run backtest with historical data"""
        logger.info(f"Starting backtest for {days} days...")
        
        # Reset state
        self.balance = self.initial_balance
        self.positions = []
        self.trades = []
        self.equity_curve = [self.initial_balance]
        
        # Get historical data
        candles = self.get_historical_candles(days)
        if not candles:
            logger.error("No historical data available for backtesting")
            return {"error": "No historical data"}
        
        # Run backtest
        for i in range(self.rsi_period + 1, len(candles)):
            candle = candles[i]
            
            # Calculate RSI
            current_candles = candles[:i+1]
            current_rsi = self.calculate_rsi(current_candles)
            
            # Trading logic
            if len(self.positions) < self.max_positions and current_rsi <= self.rsi_oversold:
                # Buy signal
                self.execute_trade(candle, "buy", current_rsi)
            
            elif len(self.positions) >= self.max_positions and current_rsi >= self.rsi_overbought:
                # Sell signal
                self.execute_trade(candle, "sell", current_rsi)
        
        # Close any open positions at the end
        while self.positions:
            last_candle = candles[-1]
            current_candles = candles[:]
            current_rsi = self.calculate_rsi(current_candles)
            self.execute_trade(last_candle, "sell", current_rsi)
        
        # Calculate performance metrics
        metrics = self.calculate_metrics()
        
        logger.info("Backtest completed")
        return metrics
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate performance metrics"""
        if not self.trades:
            return {"error": "No trades executed"}
        
        # Separate buys and sells
        buy_trades = [t for t in self.trades if t["side"] == "buy"]
        sell_trades = [t for t in self.trades if t["side"] == "sell"]
        
        # Calculate metrics
        total_trades = len(sell_trades)
        if total_trades == 0:
            return {
                "error": "No completed trades",
                "total_trades": 0,
                "final_balance": self.balance,
                "profit_loss": self.balance - self.initial_balance
            }
        
        # Profit metrics
        profit_loss = self.balance - self.initial_balance
        profit_loss_pct = (profit_loss / self.initial_balance) * 100
        
        # Win rate
        winning_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        win_rate = (len(winning_trades) / total_trades) * 100
        
        # Average win/loss
        avg_win = np.mean([t["pnl"] for t in winning_trades]) if winning_trades else 0
        losing_trades = [t for t in sell_trades if t.get("pnl", 0) <= 0]
        avg_loss = np.mean([t["pnl"] for t in losing_trades]) if losing_trades else 0
        
        # Maximum drawdown
        max_balance = max(self.equity_curve)
        min_balance = min(self.equity_curve)
        max_drawdown = (max_balance - min_balance) / max_balance * 100
        
        # Sharpe ratio (simplified)
        equity_returns = pd.Series(self.equity_curve).pct_change().dropna()
        sharpe_ratio = equity_returns.mean() / equity_returns.std() * np.sqrt(252) if len(equity_returns) > 0 else 0
        
        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_loss": profit_loss,
            "profit_loss_pct": profit_loss_pct,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "final_balance": self.balance,
            "initial_balance": self.initial_balance
        }
    
    def save_report(self, metrics: Dict[str, Any], filename: str = None):
        """Save backtest report to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_report_{timestamp}.json"
        
        try:
            report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            with open(report_path, 'w') as f:
                json.dump({
                    "config": self.config,
                    "metrics": metrics,
                    "trades": self.trades,
                    "equity_curve": self.equity_curve
                }, f, indent=2, default=str)
            
            logger.info(f"Backtest report saved to: {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"Error saving report: {e}")
            return None
    
    def plot_equity_curve(self):
        """Plot equity curve"""
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(12, 6))
            plt.plot(self.equity_curve, label='Equity Curve')
            plt.axhline(y=self.initial_balance, color='r', linestyle='--', label='Initial Balance')
            plt.title(f"{self.symbol} {self.timeframe} RSI Strategy - Equity Curve")
            plt.xlabel('Trades')
            plt.ylabel('Balance ($)')
            plt.legend()
            plt.grid(True)

            # Save plot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            plot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"equity_curve_{timestamp}.png")
            plt.savefig(plot_path)
            logger.info(f"Equity curve saved to: {plot_path}")

            # Show plot
            plt.show()
        except ImportError:
            logger.warning("matplotlib not installed - skipping equity curve plot")
        except Exception as e:
            logger.error(f"Error plotting equity curve: {e}")

def run_backtest_mode():
    """Run backtesting mode"""
    logger.info("Starting backtest mode...")
    
    # Load configuration
    config = load_config()
    if not config:
        logger.error("Failed to load configuration")
        return
    
    # Create backtester
    backtester = HyperliquidBacktester(config)
    
    # Run backtest
    backtest_days = 180  # 6 months
    metrics = backtester.run_backtest(backtest_days)
    
    # Print results
    if "error" in metrics:
        logger.error(f"Backtest error: {metrics['error']}")
    else:
        logger.info("=" * 70)
        logger.info(" BACKTEST RESULTS")
        logger.info("=" * 70)
        logger.info(f"Total Trades: {metrics['total_trades']}")
        logger.info(f"Win Rate: {metrics['win_rate']:.2f}%")
        logger.info(f"Profit/Loss: ${metrics['profit_loss']:.2f} ({metrics['profit_loss_pct']:.2f}%)")
        logger.info(f"Max Drawdown: {metrics['max_drawdown']:.2f}%")
        logger.info(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        logger.info(f"Final Balance: ${metrics['final_balance']:.2f}")
        logger.info("=" * 70)
        
        # Save report
        report_path = backtester.save_report(metrics)
        if report_path:
            logger.info(f"Full report saved to: {report_path}")
        
        # Plot equity curve
        try:
            backtester.plot_equity_curve()
        except:
            logger.warning("Could not plot equity curve (matplotlib not available)")

# Test debug logging
test_message = "Trader is running"
logger.info(f"Test message: {test_message}")
print(f"Trader started. Log file: {log_file}")

# Initialize and run trader
try:
    config = load_config()
    if config:
        # Check if backtest mode
        if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
            print("DEBUG: Starting backtest mode...")
            logger.info("DEBUG: Starting backtest mode...")
            run_backtest_mode()
        else:
            print("DEBUG: Starting live trading mode...")
            logger.info("DEBUG: Starting live trading mode...")
            trader = HyperliquidTrader(config)
            logger.info("Trader initialized successfully")
            print("Trading loop ready to start...")
            trader.run()
    else:
        logger.error("Failed to load configuration")
        print("Error: Failed to load configuration")
except Exception as e:
    logger.error(f"Error initializing trader: {e}")
    print(f"Error: {e}")
