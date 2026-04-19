#!/usr/bin/env python3
"""Pure backtest - no live trading initialization"""
import os
import sys
import json
import logging
from datetime import datetime
import pandas as pd
import numpy as np
import requests

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Backtest")

def load_config():
    """Load config"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()
        cleaned_lines = []
        for line in raw_lines:
            if "//" in line:
                line = line.split("//", 1)[0]
            cleaned_lines.append(line)
        cleaned_text = "\n".join(cleaned_lines)
        return json.loads(cleaned_text)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

class SimpleBacktester:
    """Simplified backtester"""
    
    def __init__(self, config):
        self.config = config
        self.symbol = config.get("symbol", "BTC")
        self.timeframe = config.get("timeframe", "1h")
        self.rsi_period = config.get("rsi_period", 14)
        self.rsi_overbought = config.get("rsi_overbought", 60)
        self.rsi_oversold = config.get("rsi_oversold", 30)
        self.position_size_usd = config.get("position_size_usd", 100)
        
        self.initial_balance = 10000.0
        self.balance = self.initial_balance
        self.in_position = False
        self.entry_price = None
        self.trades = []
        self.equity_curve = [self.initial_balance]
    
    def calculate_rsi(self, closes, period=14):
        """Calculate RSI"""
        if len(closes) < period + 1:
            return 50.0
        
        delta = closes.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi.iloc[-1]) if len(rsi) > 0 else 50.0
    
    def get_historical_data(self, days=180):
        """Get historical BTC data"""
        logger.info(f"Fetching {days} days of historical data...")
        try:
            # Using Hyperliquid API or fallback
            url = "https://api.hyperliquid.xyz/info"
            
            if self.timeframe == "1h":
                candles_per_day = 24
            else:
                candles_per_day = 6
            
            limit = days * candles_per_day
            
            data = {
                "type": "candleSnapshot",
                "req": {
                    "coin": self.symbol,
                    "interval": self.timeframe,
                    "startTime": 0,
                    "endTime": int(datetime.now().timestamp() * 1000),
                }
            }
            
            response = requests.post(url, json=data, timeout=10)
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code}")
                return None
            
            candles = []
            for candle in response.json()[:limit]:
                candles.append({
                    "close": float(candle.get("c", 0)),
                    "high": float(candle.get("h", 0)),
                    "low": float(candle.get("l", 0)),
                })
            
            candles.reverse()  # oldest first
            logger.info(f"Fetched {len(candles)} candles")
            return candles
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return None
    
    def run_backtest(self, days=180):
        """Run backtest"""
        logger.info(f"Starting backtest ({days} days)...")
        
        candles = self.get_historical_data(days)
        if not candles or len(candles) < self.rsi_period + 1:
            logger.error("Not enough data for backtest")
            return {"error": "Not enough data"}
        
        closes = pd.Series([c["close"] for c in candles])
        
        for i in range(self.rsi_period + 1, len(candles)):
            close = candles[i]["close"]
            current_closes = closes.iloc[:i+1]
            current_rsi = self.calculate_rsi(current_closes, self.rsi_period)
            
            # Trading logic
            if not self.in_position:
                if current_rsi <= self.rsi_oversold:
                    self.in_position = True
                    self.entry_price = close
                    logger.info(f"BUY at ${close:.2f}, RSI={current_rsi:.2f}")
            else:
                if current_rsi >= self.rsi_overbought:
                    pnl = (close - self.entry_price) * (self.position_size_usd / self.entry_price)
                    self.balance += pnl
                    self.trades.append({
                        "entry": self.entry_price,
                        "exit": close,
                        "pnl": pnl
                    })
                    logger.info(f"SELL at ${close:.2f}, RSI={current_rsi:.2f}, PnL=${pnl:.2f}")
                    self.in_position = False
                    self.entry_price = None
            
            self.equity_curve.append(self.balance)
        
        # Close any open position
        if self.in_position and candles:
            close = candles[-1]["close"]
            pnl = (close - self.entry_price) * (self.position_size_usd / self.entry_price)
            self.balance += pnl
            self.trades.append({"entry": self.entry_price, "exit": close, "pnl": pnl})
        
        # Calculate metrics
        profit_loss = self.balance - self.initial_balance
        profit_loss_pct = (profit_loss / self.initial_balance) * 100
        
        winning = [t for t in self.trades if t["pnl"] > 0]
        win_rate = (len(winning) / len(self.trades) * 100) if self.trades else 0
        
        return {
            "total_trades": len(self.trades),
            "winning_trades": len(winning),
            "win_rate": win_rate,
            "profit_loss": profit_loss,
            "profit_loss_pct": profit_loss_pct,
            "final_balance": self.balance,
            "initial_balance": self.initial_balance
        }

# Run backtest
config = load_config()
if config:
    backtester = SimpleBacktester(config)
    metrics = backtester.run_backtest(days=180)
    
    print("\n" + "="*70)
    print(" BACKTEST RESULTS (180 days)")
    print("="*70)
    if "error" in metrics:
        print(f"Error: {metrics['error']}")
    else:
        print(f"Total Trades: {metrics['total_trades']}")
        print(f"Winning Trades: {metrics['winning_trades']}")
        print(f"Win Rate: {metrics['win_rate']:.2f}%")
        print(f"Profit/Loss: ${metrics['profit_loss']:.2f} ({metrics['profit_loss_pct']:.2f}%)")
        print(f"Final Balance: ${metrics['final_balance']:.2f}")
    print("="*70)
else:
    logger.error("Failed to load config")
