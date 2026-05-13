"""
Performance Analyzer Module - Clarity Act Pair Trading v3.0
Real-time performance tracking and statistical analysis
Author: Claude Code
Date: 2026-05-14
"""

import json
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from scipy import stats as scipy_stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Real-time performance metrics"""
    timestamp: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_pnl_percent: float
    average_pnl: float
    average_pnl_percent: float
    max_pnl: float
    min_pnl: float
    std_pnl: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_percent: float
    recovery_factor: float
    profit_factor: float


class PerformanceAnalyzer:
    """
    Real-time performance tracking and analysis

    Functions:
    - Track expected value (EV) in real-time
    - Calculate Sharpe and Sortino ratios
    - Monitor win rate and profit metrics
    - Perform statistical significance tests
    - Detect anomalies in performance
    """

    def __init__(self, window_size: int = 100, logs_dir: str = "/Users/user/Desktop/trade/data/logs"):
        """Initialize performance analyzer"""
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.window_size = window_size  # Consider last N trades
        self.trades_history: List[Dict] = []
        self.metrics_history: List[PerformanceMetrics] = []
        self.price_history: List[Dict] = []

        self.metrics_file = self.logs_dir / "performance_metrics.json"
        self.load_metrics()

        logger.info(f"PerformanceAnalyzer initialized with window_size={window_size}")

    def load_metrics(self):
        """Load existing metrics from file"""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r') as f:
                    metrics_data = json.load(f)
                    # We could deserialize metrics_history if needed
                logger.info("Loaded existing performance metrics")
        except Exception as e:
            logger.error(f"Error loading metrics: {e}")

    def update_metrics(self, btc_price: float, eth_price: float):
        """Update price data for continuous monitoring"""
        try:
            self.price_history.append({
                "timestamp": datetime.now(),
                "btc": btc_price,
                "eth": eth_price,
                "ratio": btc_price / eth_price if eth_price > 0 else 0
            })

            # Keep only last 1000 price points
            if len(self.price_history) > 1000:
                self.price_history = self.price_history[-1000:]

        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def record_trade(self, trade_data: Dict):
        """
        Record a completed trade for analysis

        Args:
            trade_data: {
                "entry_time": datetime,
                "entry_price": float,
                "exit_time": datetime,
                "exit_price": float,
                "position_size": float,
                "pnl": float,
                "pnl_percent": float
            }
        """
        try:
            self.trades_history.append(trade_data)

            # Recalculate metrics
            self._calculate_and_store_metrics()

        except Exception as e:
            logger.error(f"Error recording trade: {e}")

    def _calculate_and_store_metrics(self):
        """Calculate metrics and store in history"""
        try:
            metrics = self.get_current_metrics()
            if metrics:
                self.metrics_history.append(metrics)
                self._save_metrics()
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")

    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Get current performance metrics"""
        try:
            # Use recent trades (window_size)
            recent_trades = self.trades_history[-self.window_size:] if self.trades_history else []

            if not recent_trades:
                return None

            pnls = [t.get("pnl", 0) for t in recent_trades if t.get("pnl") is not None]
            pnl_percents = [t.get("pnl_percent", 0) for t in recent_trades if t.get("pnl_percent") is not None]

            winning_trades = [t for t in recent_trades if t.get("pnl", 0) > 0]
            losing_trades = [t for t in recent_trades if t.get("pnl", 0) <= 0]

            total_trades = len(recent_trades)
            win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0

            # Calculate statistics
            total_pnl = sum(pnls)
            total_pnl_percent = sum(pnl_percents)
            average_pnl = statistics.mean(pnls) if pnls else 0
            average_pnl_percent = statistics.mean(pnl_percents) if pnl_percents else 0
            max_pnl = max(pnls) if pnls else 0
            min_pnl = min(pnls) if pnls else 0
            std_pnl = statistics.stdev(pnls) if len(pnls) > 1 else 0

            # Calculate ratios
            sharpe_ratio = self._calculate_sharpe_ratio(pnl_percents)
            sortino_ratio = self._calculate_sortino_ratio(pnl_percents)
            max_drawdown, max_drawdown_percent = self._calculate_max_drawdown(pnls)
            recovery_factor = self._calculate_recovery_factor(total_pnl, max_drawdown)
            profit_factor = self._calculate_profit_factor(winning_trades, losing_trades)

            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                total_trades=total_trades,
                winning_trades=len(winning_trades),
                losing_trades=len(losing_trades),
                win_rate=win_rate,
                total_pnl=total_pnl,
                total_pnl_percent=total_pnl_percent,
                average_pnl=average_pnl,
                average_pnl_percent=average_pnl_percent,
                max_pnl=max_pnl,
                min_pnl=min_pnl,
                std_pnl=std_pnl,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                max_drawdown=max_drawdown,
                max_drawdown_percent=max_drawdown_percent,
                recovery_factor=recovery_factor,
                profit_factor=profit_factor
            )

            return metrics

        except Exception as e:
            logger.error(f"Error calculating current metrics: {e}")
            return None

    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sharpe ratio

        Sharpe Ratio = (mean_return - risk_free_rate) / std_return
        """
        try:
            if not returns or len(returns) < 2:
                return 0.0

            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)

            if std_return == 0:
                return 0.0

            # Annualize (252 trading days per year)
            annual_return = mean_return * 252
            annual_std = std_return * (252 ** 0.5)

            sharpe = (annual_return - risk_free_rate) / annual_std if annual_std > 0 else 0
            return sharpe

        except Exception as e:
            logger.error(f"Error calculating Sharpe ratio: {e}")
            return 0.0

    def _calculate_sortino_ratio(self, returns: List[float], risk_free_rate: float = 0.02, target_return: float = 0.0) -> float:
        """
        Calculate Sortino ratio (considers only downside volatility)

        Sortino Ratio = (mean_return - risk_free_rate) / downside_std
        """
        try:
            if not returns or len(returns) < 2:
                return 0.0

            mean_return = statistics.mean(returns)

            # Calculate downside deviation (only negative returns)
            downside_returns = [r for r in returns if r < target_return]
            if not downside_returns:
                downside_returns = [0]

            downside_std = statistics.stdev(downside_returns) if len(downside_returns) > 1 else 0

            if downside_std == 0:
                return 0.0

            # Annualize
            annual_return = mean_return * 252
            annual_downside_std = downside_std * (252 ** 0.5)

            sortino = (annual_return - risk_free_rate) / annual_downside_std if annual_downside_std > 0 else 0
            return sortino

        except Exception as e:
            logger.error(f"Error calculating Sortino ratio: {e}")
            return 0.0

    def _calculate_max_drawdown(self, pnls: List[float]) -> Tuple[float, float]:
        """
        Calculate maximum drawdown

        Returns:
            (max_drawdown_absolute, max_drawdown_percent)
        """
        try:
            if not pnls or len(pnls) < 2:
                return 0.0, 0.0

            cumulative_pnl = 0
            peak = 0
            max_dd_absolute = 0
            max_dd_percent = 0

            cumulative_pnls = []
            for pnl in pnls:
                cumulative_pnl += pnl
                cumulative_pnls.append(cumulative_pnl)

                if cumulative_pnl > peak:
                    peak = cumulative_pnl

                drawdown = peak - cumulative_pnl
                if drawdown > max_dd_absolute:
                    max_dd_absolute = drawdown
                    if peak != 0:
                        max_dd_percent = (drawdown / peak) * 100

            return max_dd_absolute, max_dd_percent

        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0, 0.0

    def _calculate_recovery_factor(self, total_pnl: float, max_drawdown: float) -> float:
        """
        Calculate recovery factor (total profit / max drawdown)

        Recovery Factor = Total Profit / Max Drawdown
        Higher is better - indicates how many times you can recover from worst loss
        """
        try:
            if max_drawdown == 0:
                return 0.0 if total_pnl <= 0 else float('inf')

            return total_pnl / abs(max_drawdown)

        except Exception as e:
            logger.error(f"Error calculating recovery factor: {e}")
            return 0.0

    def _calculate_profit_factor(self, winning_trades: List[Dict], losing_trades: List[Dict]) -> float:
        """
        Calculate profit factor (gross profit / gross loss)

        Profit Factor = Gross Profit / Gross Loss
        > 1.5 is considered good
        """
        try:
            gross_profit = sum(t.get("pnl", 0) for t in winning_trades if t.get("pnl", 0) > 0)
            gross_loss = abs(sum(t.get("pnl", 0) for t in losing_trades if t.get("pnl", 0) <= 0))

            if gross_loss == 0:
                return gross_profit / 0.01 if gross_profit > 0 else 0

            return gross_profit / gross_loss

        except Exception as e:
            logger.error(f"Error calculating profit factor: {e}")
            return 0.0

    # ========================
    # EXPECTED VALUE CALCULATION
    # ========================

    def calculate_expected_value(self) -> Optional[float]:
        """
        Calculate expected value (EV) of current strategy

        EV = (Win Rate × Avg Win) - ((1 - Win Rate) × Avg Loss)
        """
        try:
            recent_trades = self.trades_history[-self.window_size:] if self.trades_history else []

            if not recent_trades:
                return None

            winning_trades = [t for t in recent_trades if t.get("pnl_percent", 0) > 0]
            losing_trades = [t for t in recent_trades if t.get("pnl_percent", 0) <= 0]

            if not recent_trades:
                return None

            win_rate = len(winning_trades) / len(recent_trades)
            loss_rate = 1 - win_rate

            avg_win = statistics.mean([t.get("pnl_percent", 0) for t in winning_trades]) if winning_trades else 0
            avg_loss = abs(statistics.mean([t.get("pnl_percent", 0) for t in losing_trades])) if losing_trades else 0

            ev = (win_rate * avg_win) - (loss_rate * avg_loss)
            return ev

        except Exception as e:
            logger.error(f"Error calculating EV: {e}")
            return None

    # ========================
    # STATISTICAL TESTING
    # ========================

    def t_test_vs_benchmark(self, benchmark_returns: List[float], confidence: float = 0.95) -> Dict:
        """
        Perform t-test to determine if strategy returns are significantly different from benchmark

        Returns:
            {
                "t_statistic": float,
                "p_value": float,
                "is_significant": bool,
                "confidence_level": float
            }
        """
        try:
            recent_trades = self.trades_history[-self.window_size:]
            strategy_returns = [t.get("pnl_percent", 0) for t in recent_trades]

            if not strategy_returns or not benchmark_returns:
                return None

            t_stat, p_value = scipy_stats.ttest_ind(strategy_returns, benchmark_returns)
            alpha = 1 - confidence

            return {
                "t_statistic": t_stat,
                "p_value": p_value,
                "is_significant": p_value < alpha,
                "confidence_level": confidence,
                "degrees_of_freedom": len(strategy_returns) + len(benchmark_returns) - 2
            }

        except Exception as e:
            logger.error(f"Error performing t-test: {e}")
            return None

    # ========================
    # ANOMALY DETECTION
    # ========================

    def detect_anomalies(self, threshold_std: float = 3.0) -> List[Dict]:
        """
        Detect anomalous trades (outliers)

        Uses z-score method: |z| > threshold_std indicates anomaly
        """
        try:
            if not self.trades_history or len(self.trades_history) < 2:
                return []

            pnl_percents = [t.get("pnl_percent", 0) for t in self.trades_history]
            mean_pnl = statistics.mean(pnl_percents)
            std_pnl = statistics.stdev(pnl_percents)

            if std_pnl == 0:
                return []

            anomalies = []
            for i, trade in enumerate(self.trades_history):
                pnl_percent = trade.get("pnl_percent", 0)
                z_score = abs((pnl_percent - mean_pnl) / std_pnl)

                if z_score > threshold_std:
                    anomalies.append({
                        "trade_index": i,
                        "pnl_percent": pnl_percent,
                        "z_score": z_score,
                        "entry_time": trade.get("entry_time"),
                        "exit_reason": trade.get("exit_reason")
                    })

            return anomalies

        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            return []

    def _save_metrics(self):
        """Save metrics to file"""
        try:
            metrics_data = {
                "timestamp": datetime.now().isoformat(),
                "window_size": self.window_size,
                "total_trades_recorded": len(self.trades_history),
                "current_metrics": asdict(self.metrics_history[-1]) if self.metrics_history else None
            }

            with open(self.metrics_file, 'w') as f:
                json.dump(metrics_data, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Error saving metrics: {e}")

    def get_summary(self) -> Dict:
        """Get summary of current performance"""
        try:
            metrics = self.get_current_metrics()
            ev = self.calculate_expected_value()
            anomalies = self.detect_anomalies()

            if not metrics:
                return {}

            return {
                "timestamp": datetime.now().isoformat(),
                "metrics": asdict(metrics),
                "expected_value": ev,
                "anomalies_detected": len(anomalies),
                "recent_anomalies": anomalies[-5:] if anomalies else []
            }

        except Exception as e:
            logger.error(f"Error getting summary: {e}")
            return {}


if __name__ == "__main__":
    # Test performance analyzer
    analyzer = PerformanceAnalyzer(window_size=50)

    # Record some test trades
    for i in range(10):
        pnl_percent = 0.5 + (i % 3) * 0.3 - 0.2  # Mix of wins and losses
        trade_data = {
            "entry_time": datetime.now() - timedelta(hours=10-i),
            "entry_price": 45000.0,
            "exit_time": datetime.now() - timedelta(hours=10-i) + timedelta(hours=2),
            "exit_price": 45000.0 * (1 + pnl_percent / 100),
            "position_size": 500.0,
            "pnl": 225.0 * (pnl_percent / 100),
            "pnl_percent": pnl_percent
        }
        analyzer.record_trade(trade_data)

    # Get metrics
    metrics = analyzer.get_current_metrics()
    if metrics:
        logger.info(f"Current metrics: {asdict(metrics)}")

    # Calculate EV
    ev = analyzer.calculate_expected_value()
    logger.info(f"Expected Value: {ev:.4f}%")

    # Get summary
    summary = analyzer.get_summary()
    logger.info(f"Summary: {json.dumps(summary, indent=2, default=str)}")
