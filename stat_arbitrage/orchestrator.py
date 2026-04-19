import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd

from stat_arbitrage.data_collector import DataCollector
from stat_arbitrage.cointegration_analyzer import CointegrationAnalyzer
from stat_arbitrage.pair_selector import PairSelector
from stat_arbitrage.backtest_engine import BacktestEngine
from stat_arbitrage.paper_trading import PaperTradingEngine
from stat_arbitrage.live_trading import LiveTradingClient
from stat_arbitrage.database import TradeDatabase
from stat_arbitrage.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StatArbitrageOrchestrator:
    """Master orchestrator for statistical arbitrage trading system"""

    def __init__(self, config: Config, db_path: str = 'stat_arb.db',
                 mode: str = 'backtest'):
        """
        Initialize orchestrator.

        Args:
            config: Configuration object
            db_path: Path to SQLite database
            mode: 'backtest', 'paper', or 'live'
        """
        self.config = config
        self.mode = mode
        self.db = TradeDatabase(db_path)

        self.data_collector = DataCollector(
            exchanges=['binance', 'kraken', 'coinbase'],
            rate_limit=True
        )
        self.analyzer = CointegrationAnalyzer()
        self.selector = PairSelector(
            min_p_value=config.COINTEGRATION_P_VALUE,
            max_hurst=0.5
        )
        self.backtest_engine = BacktestEngine(
            z_score_threshold=config.Z_SCORE_THRESHOLD,
            position_size=config.POSITION_SIZE
        )

        if mode == 'paper':
            self.paper_trader = PaperTradingEngine(
                initial_capital=100000,
                maker_fee=0.001,
                taker_fee=0.002
            )
        elif mode == 'live':
            self.live_trader = LiveTradingClient(
                api_key=config.BINANCE_API_KEY,
                api_secret=config.BINANCE_API_SECRET,
                testnet=True
            )

    def discover_pairs(self, symbols: List[str], days: int = 30) -> Dict:
        """
        Discover cointegrated trading pairs.

        Args:
            symbols: List of cryptocurrency symbols to analyze
            days: Historical lookback period in days

        Returns:
            Dictionary of viable trading pairs
        """
        logger.info(f"Discovering pairs from {len(symbols)} symbols")

        # Fetch price data
        data = {}
        for symbol in symbols:
            try:
                df = self.data_collector.fetch_2year_history(
                    [symbol], timeframe='1d'
                )
                data[symbol] = df[symbol]
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")
                continue

        # Analyze all pairs
        analysis_results = {}
        pairs_analyzed = 0

        for i, sym1 in enumerate(symbols):
            if sym1 not in data:
                continue
            for sym2 in symbols[i+1:]:
                if sym2 not in data:
                    continue

                pairs_analyzed += 1
                pair_name = f"{sym1}_{sym2}"

                try:
                    analysis = self.analyzer.analyze_pair(
                        data[sym1], data[sym2]
                    )
                    analysis['pair'] = (sym1, sym2)
                    analysis_results[pair_name] = analysis
                except Exception as e:
                    logger.debug(f"Analysis failed for {pair_name}: {e}")
                    continue

        logger.info(f"Analyzed {pairs_analyzed} pairs, "
                   f"found {len(analysis_results)} cointegrated")

        # Select best pairs
        viable_pairs = self.selector.get_top_pairs(analysis_results, n=15)
        return {'pairs': viable_pairs, 'total_analyzed': pairs_analyzed}

    def backtest_pair(self, df1: pd.DataFrame, df2: pd.DataFrame,
                     pair_name: str) -> Dict:
        """
        Run backtest on a trading pair.

        Args:
            df1: First asset price data
            df2: Second asset price data
            pair_name: Name of pair

        Returns:
            Backtest results
        """
        logger.info(f"Running backtest for {pair_name}")

        result = self.backtest_engine.run(df1, df2, pair_name)

        # Save to database
        results_dict = {
            'pair': pair_name,
            'total_trades': result.total_trades,
            'win_rate': result.win_rate,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'total_return_pct': result.total_return_pct
        }
        self.db.save_backtest_results(pair_name, results_dict)

        return results_dict

    def paper_trade(self, pairs: List[str], duration_hours: int = 24) -> Dict:
        """
        Run paper trading simulation.

        Args:
            pairs: List of trading pairs
            duration_hours: Simulation duration

        Returns:
            Trading performance metrics
        """
        if self.mode != 'paper':
            raise RuntimeError("Orchestrator not in paper trading mode")

        logger.info(f"Starting paper trading for {len(pairs)} pairs")

        # Simulate trading
        for pair in pairs:
            self.paper_trader.open_position(
                pair=pair,
                side='BUY',
                entry_price=100.0,
                quantity=1.0,
                timestamp=datetime.now()
            )

        # Get performance
        performance = self.paper_trader.get_performance_metrics()

        # Log to database
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'event': 'PAPER_TRADING_COMPLETE',
            'message': f'Completed paper trading for {len(pairs)} pairs',
            'details': performance
        }
        self.db.save_session_log(log_data)

        return performance

    def get_status(self) -> Dict:
        """Get system status and statistics"""
        stats = self.db.get_statistics()

        status = {
            'mode': self.mode,
            'database': self.db.db_path,
            'statistics': stats,
            'timestamp': datetime.now().isoformat()
        }

        if self.mode == 'paper':
            status['paper_trader'] = self.paper_trader.get_performance_metrics()

        if self.mode == 'live':
            status['live_account'] = self.live_trader.get_account_info()

        return status

    def close(self):
        """Close all connections"""
        self.db.close()
        logger.info("Orchestrator closed")
