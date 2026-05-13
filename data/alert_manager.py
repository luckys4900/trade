"""
Alert Manager Module - Clarity Act Pair Trading v3.0
Manages alerts for trading events and risk warnings
Author: Claude Code
Date: 2026-05-14
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    """Alert message"""
    alert_id: str
    timestamp: datetime
    level: AlertLevel
    message: str
    component: str = "WORKFLOW"
    is_processed: bool = False
    processed_at: Optional[datetime] = None


class AlertManager:
    """
    Comprehensive alert management system

    Functions:
    - Generate alerts for trading signals
    - Send risk warnings
    - Manage position alerts
    - Emergency alerts
    - Alert queue and processing
    """

    def __init__(self, logs_dir: str = "/Users/user/Desktop/trade/data/logs"):
        """Initialize alert manager"""
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.alerts: List[Alert] = []
        self.alert_file = self.logs_dir / "alerts.json"
        self.alert_queue: List[Alert] = []

        # Configuration
        self.max_alerts_in_memory = 1000
        self.alert_retention_days = 30

        self.load_alerts()
        logger.info("AlertManager initialized")

    def load_alerts(self):
        """Load existing alerts from file"""
        try:
            if self.alert_file.exists():
                with open(self.alert_file, 'r') as f:
                    alerts_data = json.load(f)
                    self.alerts = [
                        Alert(
                            alert_id=a.get("alert_id"),
                            timestamp=datetime.fromisoformat(a.get("timestamp")),
                            level=AlertLevel(a.get("level", "INFO")),
                            message=a.get("message"),
                            component=a.get("component", "WORKFLOW"),
                            is_processed=a.get("is_processed", False),
                            processed_at=datetime.fromisoformat(a.get("processed_at")) if a.get("processed_at") else None
                        )
                        for a in alerts_data
                    ]
                logger.info(f"Loaded {len(self.alerts)} existing alerts")
        except Exception as e:
            logger.error(f"Error loading alerts: {e}")

    # ========================
    # ALERT GENERATION
    # ========================

    def send_alert(self, message: str, level: str = "INFO", component: str = "WORKFLOW") -> str:
        """
        Send an alert

        Args:
            message: Alert message
            level: INFO, WARNING, ERROR, or CRITICAL
            component: Source component

        Returns:
            alert_id: unique identifier for this alert
        """
        try:
            alert_level = AlertLevel(level.upper())
            alert_id = f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.alerts)}"

            alert = Alert(
                alert_id=alert_id,
                timestamp=datetime.now(),
                level=alert_level,
                message=message,
                component=component,
                is_processed=False
            )

            self.alerts.append(alert)
            self.alert_queue.append(alert)

            # Log to logger
            logger_func = getattr(logger, level.lower(), logger.info)
            logger_func(f"[{component}] {message}")

            # Cleanup if needed
            if len(self.alerts) > self.max_alerts_in_memory:
                self._cleanup_old_alerts()

            self._save_alerts()
            return alert_id

        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            return None

    def send_signal_alert(self, signal_type: str, signal_data: Dict) -> str:
        """Send alert for trading signal"""
        message = f"{signal_type} signal generated - {signal_data.get('reason', 'No reason')}"
        return self.send_alert(message, "INFO", "SIGNAL_GENERATOR")

    def send_risk_alert(self, risk_type: str, risk_data: Dict) -> str:
        """Send alert for risk condition"""
        message = f"Risk alert: {risk_type} - {risk_data.get('description', '')}"
        return self.send_alert(message, "WARNING", "RISK_MANAGER")

    def send_position_alert(self, position_status: str, position_data: Dict) -> str:
        """Send alert for position change"""
        message = f"Position {position_status}: Size={position_data.get('size', 0)}, Price={position_data.get('price', 0)}"
        return self.send_alert(message, "INFO", "POSITION_MANAGER")

    def send_emergency_alert(self, emergency_type: str, details: Dict) -> str:
        """Send critical emergency alert"""
        message = f"EMERGENCY - {emergency_type}: {details.get('details', '')}"
        return self.send_alert(message, "CRITICAL", "SYSTEM")

    # ========================
    # ALERT MANAGEMENT
    # ========================

    def get_pending_alerts(self) -> List[Alert]:
        """Get unprocessed alerts"""
        return [a for a in self.alerts if not a.is_processed]

    def get_recent_alerts(self, minutes: int = 60) -> List[Alert]:
        """Get alerts from last N minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [a for a in self.alerts if a.timestamp >= cutoff_time]

    def get_alerts_by_level(self, level: str) -> List[Alert]:
        """Get alerts by severity level"""
        try:
            alert_level = AlertLevel(level.upper())
            return [a for a in self.alerts if a.level == alert_level]
        except Exception as e:
            logger.error(f"Error getting alerts by level: {e}")
            return []

    def get_alerts_by_component(self, component: str) -> List[Alert]:
        """Get alerts from specific component"""
        return [a for a in self.alerts if a.component == component]

    def mark_as_processed(self, alert_id: str) -> bool:
        """Mark alert as processed"""
        try:
            alert = next((a for a in self.alerts if a.alert_id == alert_id), None)
            if alert:
                alert.is_processed = True
                alert.processed_at = datetime.now()
                self._save_alerts()
                return True
            return False
        except Exception as e:
            logger.error(f"Error marking alert as processed: {e}")
            return False

    def process_alerts(self) -> int:
        """
        Process queued alerts

        Returns:
            Number of alerts processed
        """
        try:
            processed_count = 0

            for alert in self.alert_queue:
                # Take appropriate action based on alert level
                if alert.level == AlertLevel.CRITICAL:
                    self._handle_critical_alert(alert)
                elif alert.level == AlertLevel.ERROR:
                    self._handle_error_alert(alert)
                elif alert.level == AlertLevel.WARNING:
                    self._handle_warning_alert(alert)
                else:
                    self._handle_info_alert(alert)

                self.mark_as_processed(alert.alert_id)
                processed_count += 1

            self.alert_queue.clear()
            return processed_count

        except Exception as e:
            logger.error(f"Error processing alerts: {e}")
            return 0

    def _handle_critical_alert(self, alert: Alert):
        """Handle critical alert"""
        logger.critical(f"CRITICAL ALERT: {alert.message}")
        # In production: Send SMS, email, webhook

    def _handle_error_alert(self, alert: Alert):
        """Handle error alert"""
        logger.error(f"ERROR ALERT: {alert.message}")
        # In production: Log to error tracking system

    def _handle_warning_alert(self, alert: Alert):
        """Handle warning alert"""
        logger.warning(f"WARNING ALERT: {alert.message}")
        # In production: Log to monitoring system

    def _handle_info_alert(self, alert: Alert):
        """Handle info alert"""
        logger.info(f"INFO ALERT: {alert.message}")
        # In production: Log to analytics

    # ========================
    # SPECIFIC ALERT TYPES
    # ========================

    def alert_insufficient_balance(self, required: float, available: float) -> str:
        """Alert for insufficient balance"""
        message = f"Insufficient balance: Required ${required:.2f}, Available ${available:.2f}"
        return self.send_alert(message, "ERROR", "ENTRY_MANAGER")

    def alert_position_limit_exceeded(self, current_size: float, limit: float) -> str:
        """Alert for position size limit exceeded"""
        message = f"Position limit exceeded: Current ${current_size:.2f}, Limit ${limit:.2f}"
        return self.send_alert(message, "WARNING", "POSITION_MANAGER")

    def alert_drawdown_threshold(self, current_dd: float, threshold: float) -> str:
        """Alert for drawdown threshold exceeded"""
        message = f"Drawdown threshold exceeded: Current {current_dd:.2f}%, Threshold {threshold:.2f}%"
        return self.send_alert(message, "WARNING", "RISK_MANAGER")

    def alert_stop_loss_hit(self, entry_price: float, current_price: float, loss_percent: float) -> str:
        """Alert for stop-loss condition"""
        message = f"Stop loss hit: Entry ${entry_price:.2f}, Current ${current_price:.2f}, Loss {loss_percent:.2f}%"
        return self.send_alert(message, "INFO", "RISK_MANAGER")

    def alert_api_connection_error(self, component: str, error: str) -> str:
        """Alert for API connection error"""
        message = f"API connection error in {component}: {error}"
        return self.send_alert(message, "ERROR", "SYSTEM")

    def alert_price_feed_stale(self, component: str, minutes_stale: int) -> str:
        """Alert for stale price feed"""
        message = f"Price feed stale in {component}: {minutes_stale} minutes old"
        return self.send_alert(message, "WARNING", "DATA_FEED")

    def alert_unusual_volatility(self, volatility_percent: float, normal_range: Tuple) -> str:
        """Alert for unusual market volatility"""
        message = f"Unusual volatility detected: {volatility_percent:.2f}% (Normal: {normal_range[0]:.2f}%-{normal_range[1]:.2f}%)"
        return self.send_alert(message, "WARNING", "MARKET_MONITOR")

    # ========================
    # ALERT REPORTING
    # ========================

    def get_alert_summary(self) -> Dict:
        """Get summary of all alerts"""
        try:
            total = len(self.alerts)
            processed = len([a for a in self.alerts if a.is_processed])
            pending = total - processed

            by_level = {}
            for level in AlertLevel:
                by_level[level.value] = len([a for a in self.alerts if a.level == level])

            by_component = {}
            for alert in self.alerts:
                by_component[alert.component] = by_component.get(alert.component, 0) + 1

            return {
                "timestamp": datetime.now().isoformat(),
                "total_alerts": total,
                "processed": processed,
                "pending": pending,
                "by_level": by_level,
                "by_component": by_component,
                "recent_5": [
                    {
                        "alert_id": a.alert_id,
                        "timestamp": a.timestamp.isoformat(),
                        "level": a.level.value,
                        "message": a.message,
                        "component": a.component
                    }
                    for a in sorted(self.alerts, key=lambda x: x.timestamp, reverse=True)[:5]
                ]
            }

        except Exception as e:
            logger.error(f"Error getting alert summary: {e}")
            return {}

    def _cleanup_old_alerts(self):
        """Remove old alerts (older than retention period)"""
        try:
            cutoff_time = datetime.now() - timedelta(days=self.alert_retention_days)
            original_count = len(self.alerts)

            self.alerts = [a for a in self.alerts if a.timestamp >= cutoff_time]

            removed = original_count - len(self.alerts)
            if removed > 0:
                logger.info(f"Cleaned up {removed} old alerts")

            self._save_alerts()

        except Exception as e:
            logger.error(f"Error cleaning up old alerts: {e}")

    def _save_alerts(self):
        """Save alerts to file"""
        try:
            alerts_json = [
                {
                    "alert_id": a.alert_id,
                    "timestamp": a.timestamp.isoformat(),
                    "level": a.level.value,
                    "message": a.message,
                    "component": a.component,
                    "is_processed": a.is_processed,
                    "processed_at": a.processed_at.isoformat() if a.processed_at else None
                }
                for a in self.alerts
            ]

            with open(self.alert_file, 'w') as f:
                json.dump(alerts_json, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving alerts: {e}")

    def export_alerts_report(self, filename: Optional[str] = None) -> Path:
        """Export alerts to a report file"""
        try:
            if not filename:
                filename = f"alert_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            filepath = self.logs_dir / filename

            report = {
                "generated_at": datetime.now().isoformat(),
                "summary": self.get_alert_summary(),
                "all_alerts": [
                    {
                        "alert_id": a.alert_id,
                        "timestamp": a.timestamp.isoformat(),
                        "level": a.level.value,
                        "message": a.message,
                        "component": a.component,
                        "is_processed": a.is_processed,
                        "processed_at": a.processed_at.isoformat() if a.processed_at else None
                    }
                    for a in self.alerts
                ]
            }

            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2)

            logger.info(f"Alerts report exported to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error exporting alerts report: {e}")
            return None


if __name__ == "__main__":
    # Test alert manager
    manager = AlertManager()

    # Send various alerts
    manager.send_alert("System started", "INFO", "SYSTEM")
    manager.send_signal_alert("ENTRY", {"reason": "BTC/ETH ratio above MA"})
    manager.send_risk_alert("DRAWDOWN", {"description": "Approaching drawdown limit"})
    manager.send_position_alert("OPENED", {"size": 1000.0, "price": 45000.0})

    # Get summary
    summary = manager.get_alert_summary()
    logger.info(f"Alert summary: {json.dumps(summary, indent=2)}")

    # Process alerts
    processed = manager.process_alerts()
    logger.info(f"Processed {processed} alerts")

    # Export report
    manager.export_alerts_report()
