"""
Trade Logger Module - Clarity Act Pair Trading v3.0
Logs and tracks all trades with detailed performance metrics
Author: Claude Code
Date: 2026-05-14
"""

import json
import csv
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict, field
import statistics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TradeEntry:
    """Single trade entry"""
    entry_id: str
    entry_time: datetime
    entry_price: float
    position_size: float
    btc_price: float
    eth_price: float
    order_id: str
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    status: str = "OPEN"
    notes: str = ""


class TradeLogger:
    """
    Comprehensive trade logging and reporting system

    Functions:
    - Log all entry and exit trades
    - Track performance metrics in real-time
    - Generate daily/weekly/monthly reports
    - Export to JSON and CSV formats
    """

    def __init__(self, logs_dir: str = "/Users/user/Desktop/trade/data/logs"):
        """Initialize trade logger"""
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.trades: List[TradeEntry] = []
        self.trade_file = self.logs_dir / "trades.json"
        self.csv_file = self.logs_dir / "trades.csv"

        self.load_trades()
        logger.info("TradeLogger initialized")

    def load_trades(self):
        """Load existing trades from file"""
        try:
            if self.trade_file.exists():
                with open(self.trade_file, 'r') as f:
                    trades_data = json.load(f)
                    self.trades = [
                        TradeEntry(
                            entry_id=t.get("entry_id"),
                            entry_time=datetime.fromisoformat(t.get("entry_time")),
                            entry_price=t.get("entry_price"),
                            position_size=t.get("position_size"),
                            btc_price=t.get("btc_price"),
                            eth_price=t.get("eth_price"),
                            order_id=t.get("order_id"),
                            exit_time=datetime.fromisoformat(t.get("exit_time")) if t.get("exit_time") else None,
                            exit_price=t.get("exit_price"),
                            exit_reason=t.get("exit_reason"),
                            pnl=t.get("pnl"),
                            pnl_percent=t.get("pnl_percent"),
                            status=t.get("status", "OPEN"),
                            notes=t.get("notes", "")
                        )
                        for t in trades_data
                    ]
                logger.info(f"Loaded {len(self.trades)} existing trades")
        except Exception as e:
            logger.error(f"Error loading trades: {e}")

    def log_entry(self, entry_data: Dict) -> str:
        """
        Log a new trade entry

        Args:
            entry_data: {
                "entry_time": datetime,
                "entry_price": float,
                "position_size": float,
                "btc_price": float,
                "eth_price": float,
                "order_id": str
            }

        Returns:
            entry_id: unique identifier for this trade entry
        """
        try:
            entry_time = entry_data.get("entry_time")
            if isinstance(entry_time, str):
                entry_time = datetime.fromisoformat(entry_time)

            entry_price = entry_data.get("entry_price", 0)
            entry_id = f"entry_{entry_time.strftime('%Y%m%d_%H%M%S')}_{len(self.trades)}"

            trade = TradeEntry(
                entry_id=entry_id,
                entry_time=entry_time,
                entry_price=entry_price,
                position_size=entry_data.get("position_size"),
                btc_price=entry_data.get("btc_price"),
                eth_price=entry_data.get("eth_price"),
                order_id=entry_data.get("order_id"),
                status="OPEN",
                notes=f"Entry logged at {entry_time}"
            )

            self.trades.append(trade)
            self._save_trades()

            logger.info(f"Trade entry logged: {entry_id} at {entry_price:.2f}")
            return entry_id

        except Exception as e:
            logger.error(f"Error logging entry: {e}")
            return None

    def log_exit(self, exit_data: Dict) -> Optional[str]:
        """
        Log trade exit for an existing entry

        Args:
            exit_data: {
                "entry_id": str (optional, uses last open trade if not provided),
                "exit_time": datetime,
                "exit_price": float,
                "exit_reason": str,
                "pnl": float,
                "pnl_percent": float
            }

        Returns:
            entry_id: identifier of the closed trade
        """
        try:
            # Find the trade to close
            entry_id = exit_data.get("entry_id")
            if not entry_id:
                # Find last open trade
                open_trades = [t for t in self.trades if t.status == "OPEN"]
                if not open_trades:
                    logger.warning("No open trades to close")
                    return None
                trade = open_trades[-1]
                entry_id = trade.entry_id
            else:
                trade = next((t for t in self.trades if t.entry_id == entry_id), None)
                if not trade:
                    logger.warning(f"Trade not found: {entry_id}")
                    return None

            exit_time = exit_data.get("exit_time")
            if isinstance(exit_time, str):
                exit_time = datetime.fromisoformat(exit_time)

            # Update trade
            trade.exit_time = exit_time
            trade.exit_price = exit_data.get("exit_price")
            trade.exit_reason = exit_data.get("exit_reason")
            trade.pnl = exit_data.get("pnl")
            trade.pnl_percent = exit_data.get("pnl_percent")
            trade.status = "CLOSED"
            trade.notes = f"Closed: {trade.notes} | Exit reason: {trade.exit_reason}"

            self._save_trades()

            logger.info(
                f"Trade exit logged: {entry_id} | "
                f"Exit price: {trade.exit_price:.2f} | "
                f"P&L: {trade.pnl_percent:.2f}%"
            )
            return entry_id

        except Exception as e:
            logger.error(f"Error logging exit: {e}")
            return None

    def _save_trades(self):
        """Save trades to JSON file"""
        try:
            trades_json = [
                {
                    "entry_id": t.entry_id,
                    "entry_time": t.entry_time.isoformat(),
                    "entry_price": t.entry_price,
                    "position_size": t.position_size,
                    "btc_price": t.btc_price,
                    "eth_price": t.eth_price,
                    "order_id": t.order_id,
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "exit_price": t.exit_price,
                    "exit_reason": t.exit_reason,
                    "pnl": t.pnl,
                    "pnl_percent": t.pnl_percent,
                    "status": t.status,
                    "notes": t.notes
                }
                for t in self.trades
            ]

            with open(self.trade_file, 'w') as f:
                json.dump(trades_json, f, indent=2)

            # Also save to CSV
            self._save_to_csv()

        except Exception as e:
            logger.error(f"Error saving trades: {e}")

    def _save_to_csv(self):
        """Save trades to CSV file"""
        try:
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "entry_id", "entry_time", "entry_price", "position_size",
                        "btc_price", "eth_price", "exit_time", "exit_price",
                        "pnl", "pnl_percent", "status"
                    ]
                )
                writer.writeheader()

                for t in self.trades:
                    writer.writerow({
                        "entry_id": t.entry_id,
                        "entry_time": t.entry_time.isoformat(),
                        "entry_price": t.entry_price,
                        "position_size": t.position_size,
                        "btc_price": t.btc_price,
                        "eth_price": t.eth_price,
                        "exit_time": t.exit_time.isoformat() if t.exit_time else "",
                        "exit_price": t.exit_price or "",
                        "pnl": t.pnl or "",
                        "pnl_percent": t.pnl_percent or "",
                        "status": t.status
                    })
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")

    def get_closed_trades(self) -> List[TradeEntry]:
        """Get all closed trades"""
        return [t for t in self.trades if t.status == "CLOSED"]

    def get_open_trades(self) -> List[TradeEntry]:
        """Get all open trades"""
        return [t for t in self.trades if t.status == "OPEN"]

    # ========================
    # REPORTING FUNCTIONS
    # ========================

    def generate_daily_report(self, date: Optional[datetime] = None) -> Dict:
        """Generate daily report for specific date (default: today)"""
        if date is None:
            date = datetime.now()

        start_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=1)

        daily_trades = [
            t for t in self.get_closed_trades()
            if start_time <= t.exit_time < end_time
        ]

        report = self._calculate_metrics(daily_trades, f"Daily Report - {date.date()}")
        return report

    def generate_weekly_report(self, date: Optional[datetime] = None) -> Dict:
        """Generate weekly report (week ending on date)"""
        if date is None:
            date = datetime.now()

        # Find Monday of the week
        days_since_monday = date.weekday()
        start_time = (date - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_time = start_time + timedelta(days=7)

        weekly_trades = [
            t for t in self.get_closed_trades()
            if start_time <= t.exit_time < end_time
        ]

        report = self._calculate_metrics(
            weekly_trades,
            f"Weekly Report - Week of {start_time.date()}"
        )
        return report

    def generate_monthly_report(self, date: Optional[datetime] = None) -> Dict:
        """Generate monthly report"""
        if date is None:
            date = datetime.now()

        start_time = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get next month
        if date.month == 12:
            end_time = start_time.replace(year=date.year + 1, month=1)
        else:
            end_time = start_time.replace(month=date.month + 1)

        monthly_trades = [
            t for t in self.get_closed_trades()
            if start_time <= t.exit_time < end_time
        ]

        report = self._calculate_metrics(
            monthly_trades,
            f"Monthly Report - {start_time.strftime('%Y-%m')}"
        )
        return report

    def _calculate_metrics(self, trades: List[TradeEntry], title: str) -> Dict:
        """Calculate performance metrics for a set of trades"""
        try:
            if not trades:
                return {
                    "title": title,
                    "timestamp": datetime.now().isoformat(),
                    "total_trades": 0,
                    "metrics": {}
                }

            pnls = [t.pnl for t in trades if t.pnl is not None]
            pnl_percents = [t.pnl_percent for t in trades if t.pnl_percent is not None]

            winning_trades = [t for t in trades if t.pnl is not None and t.pnl > 0]
            losing_trades = [t for t in trades if t.pnl is not None and t.pnl <= 0]

            return {
                "title": title,
                "timestamp": datetime.now().isoformat(),
                "total_trades": len(trades),
                "metrics": {
                    "winning_trades": len(winning_trades),
                    "losing_trades": len(losing_trades),
                    "win_rate": len(winning_trades) / len(trades) if trades else 0,
                    "total_pnl": sum(pnls),
                    "total_pnl_percent": sum(pnl_percents),
                    "average_pnl": statistics.mean(pnls) if pnls else 0,
                    "average_pnl_percent": statistics.mean(pnl_percents) if pnl_percents else 0,
                    "max_pnl": max(pnls) if pnls else 0,
                    "min_pnl": min(pnls) if pnls else 0,
                    "median_pnl": statistics.median(pnls) if pnls else 0,
                    "stdev_pnl": statistics.stdev(pnls) if len(pnls) > 1 else 0,
                    "sharpe_ratio": self._calculate_sharpe_ratio(pnl_percents),
                    "profit_factor": self._calculate_profit_factor(winning_trades, losing_trades)
                },
                "trade_details": [
                    {
                        "entry_id": t.entry_id,
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "pnl": t.pnl,
                        "pnl_percent": t.pnl_percent,
                        "exit_reason": t.exit_reason
                    }
                    for t in trades
                ]
            }

        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return {}

    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio for returns"""
        try:
            if not returns or len(returns) < 2:
                return 0.0

            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)

            if std_return == 0:
                return 0.0

            # Annualize (assuming 252 trading days per year)
            annual_return = mean_return * 252
            annual_std = std_return * (252 ** 0.5)

            sharpe = (annual_return - risk_free_rate) / annual_std if annual_std > 0 else 0
            return sharpe

        except Exception as e:
            logger.error(f"Error calculating Sharpe ratio: {e}")
            return 0.0

    def _calculate_profit_factor(self, winning_trades: List[TradeEntry], losing_trades: List[TradeEntry]) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        try:
            gross_profit = sum(t.pnl for t in winning_trades if t.pnl)
            gross_loss = abs(sum(t.pnl for t in losing_trades if t.pnl))

            if gross_loss == 0:
                return gross_profit / 0.01 if gross_profit > 0 else 0

            return gross_profit / gross_loss
        except Exception as e:
            logger.error(f"Error calculating profit factor: {e}")
            return 0.0

    def save_report(self, report: Dict, report_type: str = "daily") -> Path:
        """Save report to file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{report_type}_{timestamp}.json"
            filepath = self.logs_dir / filename

            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2)

            logger.info(f"Report saved: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error saving report: {e}")
            return None


if __name__ == "__main__":
    # Test trade logger
    logger_inst = TradeLogger()

    # Log a test entry
    entry_data = {
        "entry_time": datetime.now(),
        "entry_price": 45000.0,
        "position_size": 500.0,
        "btc_price": 45000.0,
        "eth_price": 2500.0,
        "order_id": "test_order_001"
    }
    entry_id = logger_inst.log_entry(entry_data)
    logger.info(f"Test entry logged: {entry_id}")

    # Log a test exit
    exit_data = {
        "entry_id": entry_id,
        "exit_time": datetime.now() + timedelta(hours=2),
        "exit_price": 45500.0,
        "exit_reason": "Target reached",
        "pnl": 250.0,
        "pnl_percent": 1.11
    }
    logger_inst.log_exit(exit_data)

    # Generate reports
    daily_report = logger_inst.generate_daily_report()
    logger.info(f"Daily report: {json.dumps(daily_report, indent=2)}")

    # Save report
    logger_inst.save_report(daily_report, "daily")
