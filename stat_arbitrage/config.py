import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration for statistical arbitrage system"""

    MIN_BTC = 100
    Z_SCORE_THRESHOLD = 2.0
    POSITION_SIZE = 0.02
    COINTEGRATION_P_VALUE = 0.05

    HURST_THRESHOLD = 0.5
    MIN_SHARPE = -1.0

    EXCHANGES = ['binance', 'kraken', 'coinbase', 'bybit', 'gate']
    RATE_LIMIT = True

    DB_PATH = 'stat_arb.db'
    LOG_DIR = 'logs'

    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
    BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')

    TESTNET = True

    MAX_POSITION_SIZE = 0.05
    MAX_LEVERAGE = 1.0

    ENTRY_THRESHOLD = 2.0
    EXIT_THRESHOLD = 0.5

    LOOKBACK_WINDOW = 20
    TRAIN_WINDOW = 200
    TEST_WINDOW = 100
    WALK_FORWARD_STEP = 50
