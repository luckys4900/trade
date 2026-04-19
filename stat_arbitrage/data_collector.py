import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class DataCollector:
    def __init__(self, exchanges: List[str], rate_limit: bool = True):
        """Initialize CCXT exchange clients
        
        Args:
            exchanges: List of exchange names (e.g., ['binance', 'kraken'])
            rate_limit: Enable rate limiting to respect API limits
        """
        self.exchange_clients = {}
        self.rate_limit = rate_limit
        
        for exchange_name in exchanges:
            try:
                exchange_class = getattr(ccxt, exchange_name)
                self.exchange_clients[exchange_name] = exchange_class({
                    'enableRateLimit': rate_limit
                })
                logger.info(f"Initialized {exchange_name}")
            except AttributeError:
                logger.error(f"Exchange {exchange_name} not found in CCXT")
                raise ValueError(f"Unknown exchange: {exchange_name}")
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100, 
                    exchange: str = None) -> List[List]:
        """Fetch OHLCV data from CCXT
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Timeframe (e.g., '1m', '5m', '1h', '1d')
            limit: Number of candles to fetch
            exchange: Exchange name (uses first if not specified)
            
        Returns:
            List of OHLCV candles [timestamp, open, high, low, close, volume]
        """
        if exchange is None:
            exchange = list(self.exchange_clients.keys())[0]
        
        if exchange not in self.exchange_clients:
            logger.error(f"Exchange {exchange} not initialized")
            return []
        
        try:
            client = self.exchange_clients[exchange]
            ohlcv = client.fetch_ohlcv(symbol, timeframe, limit=limit)
            logger.info(f"Fetched {len(ohlcv)} candles for {symbol} from {exchange}")
            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching {symbol} from {exchange}: {e}")
            return []
    
    def fetch_multiple(self, symbols: List[str], timeframe: str, limit: int = 100,
                      exchange: str = None) -> Dict[str, List]:
        """Fetch data for multiple symbols
        
        Args:
            symbols: List of trading pair symbols
            timeframe: Timeframe for all symbols
            limit: Number of candles per symbol
            exchange: Exchange name
            
        Returns:
            Dictionary mapping symbol to OHLCV data
        """
        if exchange is None:
            exchange = list(self.exchange_clients.keys())[0]
        
        prices = {}
        for symbol in symbols:
            prices[symbol] = self.fetch_ohlcv(symbol, timeframe, limit, exchange)
            if self.rate_limit:
                time.sleep(0.5)
        
        return prices
    
    def save_csv(self, filepath: str, ohlcv: List[List], symbol: str):
        """Save OHLCV data to CSV
        
        Args:
            filepath: Path to save CSV file
            ohlcv: OHLCV data from fetch_ohlcv
            symbol: Trading pair symbol
        """
        df = pd.DataFrame(
            ohlcv,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df['symbol'] = symbol
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.to_csv(filepath, index=False)
        logger.info(f"Saved {len(df)} rows to {filepath}")
    
    def fetch_2year_history(self, symbols: List[str], timeframe: str = "1d",
                           exchange: str = None) -> Dict[str, pd.DataFrame]:
        """Fetch 2 years of historical data
        
        Args:
            symbols: List of trading pair symbols
            timeframe: Timeframe (default '1d')
            exchange: Exchange name
            
        Returns:
            Dictionary mapping symbol to pandas DataFrame with historical data
        """
        if exchange is None:
            exchange = list(self.exchange_clients.keys())[0]
        
        all_data = {}
        for symbol in symbols:
            logger.info(f"Fetching 2-year history for {symbol}...")
            ohlcv_list = []
            
            # 730 days = 2 years
            days_remaining = 730
            while days_remaining > 0:
                limit = min(100, days_remaining)
                ohlcv = self.fetch_ohlcv(symbol, timeframe, limit, exchange)
                
                if not ohlcv:
                    break
                
                ohlcv_list.extend(ohlcv)
                days_remaining -= limit
                
                if self.rate_limit:
                    time.sleep(0.5)
            
            df = pd.DataFrame(
                ohlcv_list,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            all_data[symbol] = df
            logger.info(f"Fetched {len(df)} rows for {symbol}")
        
        return all_data
