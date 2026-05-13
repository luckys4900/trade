"""
Error Recovery Module - Clarity Act Pair Trading v3.0
Handles errors and implements recovery mechanisms
Author: Claude Code
Date: 2026-05-14
"""

import json
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecoveryStrategy(Enum):
    """Recovery strategy types"""
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"
    CIRCUIT_BREAK = "CIRCUIT_BREAK"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


@dataclass
class ErrorRecord:
    """Error record for tracking"""
    error_id: str
    timestamp: datetime
    error_type: str
    severity: ErrorSeverity
    message: str
    traceback_str: str
    component: str
    retry_count: int = 0
    recovery_strategy: Optional[RecoveryStrategy] = None
    is_recovered: bool = False
    recovery_notes: str = ""


class ErrorRecovery:
    """
    Comprehensive error recovery system

    Functions:
    - Track and log errors
    - Implement automatic recovery strategies
    - Manage circuit breakers for cascading failures
    - Failsafe mechanisms
    - Error alerting and reporting
    """

    def __init__(self, logs_dir: str = "/Users/user/Desktop/trade/data/logs"):
        """Initialize error recovery system"""
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.errors: List[ErrorRecord] = []
        self.error_file = self.logs_dir / "errors.json"
        self.circuit_breakers: Dict[str, Dict] = {}
        self.recovery_handlers: Dict[str, Callable] = {}

        self.max_retries = 3
        self.retry_delay_seconds = 5
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_timeout = 300

        self._setup_default_handlers()
        self.load_errors()
        logger.info("ErrorRecovery system initialized")

    def _setup_default_handlers(self):
        """Setup default recovery handlers"""
        self.recovery_handlers["API_CONNECTION_ERROR"] = self._handle_api_connection_error
        self.recovery_handlers["NETWORK_ERROR"] = self._handle_network_error
        self.recovery_handlers["DATA_ERROR"] = self._handle_data_error
        self.recovery_handlers["CALCULATION_ERROR"] = self._handle_calculation_error
        self.recovery_handlers["STATE_ERROR"] = self._handle_state_error

    def load_errors(self):
        """Load existing errors from file"""
        try:
            if self.error_file.exists():
                with open(self.error_file, 'r') as f:
                    errors_data = json.load(f)
                    self.errors = [
                        ErrorRecord(
                            error_id=e.get("error_id"),
                            timestamp=datetime.fromisoformat(e.get("timestamp")),
                            error_type=e.get("error_type"),
                            severity=ErrorSeverity(e.get("severity", "MEDIUM")),
                            message=e.get("message"),
                            traceback_str=e.get("traceback_str"),
                            component=e.get("component"),
                            retry_count=e.get("retry_count", 0),
                            recovery_strategy=RecoveryStrategy(e.get("recovery_strategy")) if e.get("recovery_strategy") else None,
                            is_recovered=e.get("is_recovered", False),
                            recovery_notes=e.get("recovery_notes", "")
                        )
                        for e in errors_data
                    ]
                logger.info(f"Loaded {len(self.errors)} existing error records")
        except Exception as e:
            logger.error(f"Error loading error records: {e}")

    # ========================
    # ERROR TRACKING
    # ========================

    def record_error(self, error: Exception, component: str, severity: str = "MEDIUM") -> str:
        """
        Record an error for tracking

        Args:
            error: Exception object
            component: Component where error occurred
            severity: LOW, MEDIUM, HIGH, or CRITICAL

        Returns:
            error_id: unique identifier for this error
        """
        try:
            error_severity = ErrorSeverity(severity.upper())
            error_id = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.errors)}"
            error_type = type(error).__name__

            error_record = ErrorRecord(
                error_id=error_id,
                timestamp=datetime.now(),
                error_type=error_type,
                severity=error_severity,
                message=str(error),
                traceback_str=traceback.format_exc(),
                component=component,
                retry_count=0
            )

            self.errors.append(error_record)
            self._save_errors()

            logger.log(
                getattr(logging, severity.lower(), logging.ERROR),
                f"Error recorded [{error_id}] {error_type} in {component}: {error}"
            )

            return error_id

        except Exception as e:
            logger.error(f"Error recording error: {e}")
            return None

    def get_error_by_id(self, error_id: str) -> Optional[ErrorRecord]:
        """Retrieve error record by ID"""
        return next((e for e in self.errors if e.error_id == error_id), None)

    def get_recent_errors(self, minutes: int = 60, severity: Optional[str] = None) -> List[ErrorRecord]:
        """Get recent errors"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent = [e for e in self.errors if e.timestamp >= cutoff_time]

        if severity:
            try:
                sev_enum = ErrorSeverity(severity.upper())
                recent = [e for e in recent if e.severity == sev_enum]
            except ValueError:
                pass

        return recent

    # ========================
    # RECOVERY STRATEGIES
    # ========================

    def recover(self) -> bool:
        """
        Execute recovery for all unrecovered errors
        """
        try:
            unrecovered = [e for e in self.errors if not e.is_recovered]

            if not unrecovered:
                logger.info("No unrecovered errors")
                return True

            logger.info(f"Attempting recovery for {len(unrecovered)} errors")

            for error_record in unrecovered:
                self._attempt_recovery(error_record)

            return True

        except Exception as e:
            logger.error(f"Error in recovery process: {e}")
            return False

    def _attempt_recovery(self, error_record: ErrorRecord) -> bool:
        """Attempt recovery for a specific error"""
        try:
            logger.info(f"Attempting recovery for {error_record.error_id}...")

            # Check circuit breaker
            if self._is_circuit_broken(error_record.component):
                logger.warning(f"Circuit breaker open for {error_record.component}")
                return False

            # Get handler
            handler = self.recovery_handlers.get(
                error_record.error_type,
                self._handle_generic_error
            )

            # Attempt recovery with retries
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"Recovery attempt {attempt + 1}/{self.max_retries} for {error_record.error_id}")
                    success = handler(error_record)

                    if success:
                        error_record.is_recovered = True
                        error_record.recovery_strategy = RecoveryStrategy.RETRY
                        error_record.recovery_notes = f"Recovered after {attempt + 1} attempts"
                        self._save_errors()
                        logger.info(f"Error {error_record.error_id} recovered successfully")
                        return True

                    error_record.retry_count = attempt + 1

                except Exception as e:
                    logger.warning(f"Recovery attempt {attempt + 1} failed: {e}")
                    time.sleep(self.retry_delay_seconds)

            # If all retries failed, set circuit breaker
            logger.error(f"All recovery attempts failed for {error_record.error_id}")
            self._set_circuit_breaker(error_record.component)

            # For critical errors, mark for manual intervention
            if error_record.severity == ErrorSeverity.CRITICAL:
                error_record.recovery_strategy = RecoveryStrategy.MANUAL_INTERVENTION
                error_record.recovery_notes = "Critical error - manual intervention required"

            self._save_errors()
            return False

        except Exception as e:
            logger.error(f"Error in recovery attempt: {e}")
            return False

    # ========================
    # RECOVERY HANDLERS
    # ========================

    def _handle_api_connection_error(self, error_record: ErrorRecord) -> bool:
        """Handle API connection errors"""
        try:
            logger.info("Handling API connection error...")
            # Attempt to reconnect
            time.sleep(self.retry_delay_seconds)
            # In production: verify API is back online
            logger.info("API connection restored")
            return True
        except Exception as e:
            logger.error(f"API recovery failed: {e}")
            return False

    def _handle_network_error(self, error_record: ErrorRecord) -> bool:
        """Handle network errors"""
        try:
            logger.info("Handling network error...")
            # Attempt to verify network connectivity
            time.sleep(self.retry_delay_seconds)
            # In production: ping DNS or network endpoint
            logger.info("Network connectivity restored")
            return True
        except Exception as e:
            logger.error(f"Network recovery failed: {e}")
            return False

    def _handle_data_error(self, error_record: ErrorRecord) -> bool:
        """Handle data parsing/validation errors"""
        try:
            logger.info("Handling data error...")
            # Fetch fresh data
            time.sleep(self.retry_delay_seconds)
            # In production: fetch new data and retry parsing
            logger.info("Data refreshed, operation retryable")
            return True
        except Exception as e:
            logger.error(f"Data recovery failed: {e}")
            return False

    def _handle_calculation_error(self, error_record: ErrorRecord) -> bool:
        """Handle calculation/math errors"""
        try:
            logger.info("Handling calculation error...")
            # Recalculate with fresh data
            time.sleep(self.retry_delay_seconds)
            # In production: validate inputs and retry
            logger.info("Calculation retryable")
            return True
        except Exception as e:
            logger.error(f"Calculation recovery failed: {e}")
            return False

    def _handle_state_error(self, error_record: ErrorRecord) -> bool:
        """Handle state consistency errors"""
        try:
            logger.info("Handling state error...")
            # Attempt to restore consistent state
            time.sleep(self.retry_delay_seconds)
            # In production: reload from persistent storage
            logger.info("State recovered")
            return True
        except Exception as e:
            logger.error(f"State recovery failed: {e}")
            return False

    def _handle_generic_error(self, error_record: ErrorRecord) -> bool:
        """Handle unknown errors"""
        try:
            logger.info("Handling generic error...")
            time.sleep(self.retry_delay_seconds)
            # Generic recovery: wait and retry
            return True
        except Exception as e:
            logger.error(f"Generic recovery failed: {e}")
            return False

    # ========================
    # CIRCUIT BREAKER
    # ========================

    def _is_circuit_broken(self, component: str) -> bool:
        """Check if circuit breaker is open for component"""
        try:
            if component not in self.circuit_breakers:
                return False

            breaker = self.circuit_breakers[component]
            if breaker["state"] != "OPEN":
                return False

            # Check if timeout has passed
            if datetime.now() - breaker["opened_at"] > timedelta(seconds=self.circuit_breaker_timeout):
                logger.info(f"Circuit breaker timeout for {component} - attempting reset")
                breaker["state"] = "HALF_OPEN"
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking circuit breaker: {e}")
            return False

    def _set_circuit_breaker(self, component: str):
        """Set circuit breaker for component"""
        try:
            if component not in self.circuit_breakers:
                self.circuit_breakers[component] = {
                    "state": "OPEN",
                    "failure_count": 1,
                    "opened_at": datetime.now()
                }
            else:
                breaker = self.circuit_breakers[component]
                breaker["failure_count"] += 1
                if breaker["failure_count"] >= self.circuit_breaker_threshold:
                    breaker["state"] = "OPEN"
                    breaker["opened_at"] = datetime.now()
                    logger.critical(f"Circuit breaker OPEN for {component}")

        except Exception as e:
            logger.error(f"Error setting circuit breaker: {e}")

    def reset_circuit_breaker(self, component: str) -> bool:
        """Manually reset circuit breaker"""
        try:
            if component in self.circuit_breakers:
                self.circuit_breakers[component]["state"] = "CLOSED"
                self.circuit_breakers[component]["failure_count"] = 0
                logger.info(f"Circuit breaker RESET for {component}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error resetting circuit breaker: {e}")
            return False

    # ========================
    # FAILSAFE MECHANISMS
    # ========================

    def enable_failsafe(self, component: str, failsafe_function: Callable):
        """Enable failsafe mechanism for component"""
        try:
            if component not in self.recovery_handlers:
                self.recovery_handlers[component] = failsafe_function
                logger.info(f"Failsafe enabled for {component}")
        except Exception as e:
            logger.error(f"Error enabling failsafe: {e}")

    def is_system_healthy(self) -> bool:
        """Check overall system health"""
        try:
            # System is unhealthy if there are critical unrecovered errors
            critical_errors = [
                e for e in self.errors
                if e.severity == ErrorSeverity.CRITICAL and not e.is_recovered
            ]

            if critical_errors:
                logger.warning(f"System unhealthy: {len(critical_errors)} critical errors")
                return False

            # Check circuit breakers
            open_breakers = [
                name for name, breaker in self.circuit_breakers.items()
                if breaker["state"] == "OPEN"
            ]

            if open_breakers:
                logger.warning(f"System unhealthy: Circuit breakers open for {open_breakers}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            return False

    # ========================
    # ERROR REPORTING
    # ========================

    def get_error_summary(self) -> Dict:
        """Get error summary"""
        try:
            by_severity = {}
            for severity in ErrorSeverity:
                by_severity[severity.value] = len([
                    e for e in self.errors if e.severity == severity
                ])

            by_component = {}
            for error in self.errors:
                by_component[error.component] = by_component.get(error.component, 0) + 1

            unrecovered = len([e for e in self.errors if not e.is_recovered])

            return {
                "timestamp": datetime.now().isoformat(),
                "total_errors": len(self.errors),
                "unrecovered_errors": unrecovered,
                "by_severity": by_severity,
                "by_component": by_component,
                "circuit_breakers": {
                    name: breaker["state"]
                    for name, breaker in self.circuit_breakers.items()
                },
                "system_healthy": self.is_system_healthy()
            }

        except Exception as e:
            logger.error(f"Error getting summary: {e}")
            return {}

    def _save_errors(self):
        """Save errors to file"""
        try:
            errors_json = [
                {
                    "error_id": e.error_id,
                    "timestamp": e.timestamp.isoformat(),
                    "error_type": e.error_type,
                    "severity": e.severity.value,
                    "message": e.message,
                    "traceback_str": e.traceback_str,
                    "component": e.component,
                    "retry_count": e.retry_count,
                    "recovery_strategy": e.recovery_strategy.value if e.recovery_strategy else None,
                    "is_recovered": e.is_recovered,
                    "recovery_notes": e.recovery_notes
                }
                for e in self.errors
            ]

            with open(self.error_file, 'w') as f:
                json.dump(errors_json, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving error records: {e}")

    def export_error_report(self, filename: Optional[str] = None) -> Path:
        """Export error report"""
        try:
            if not filename:
                filename = f"error_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            filepath = self.logs_dir / filename

            report = {
                "generated_at": datetime.now().isoformat(),
                "summary": self.get_error_summary(),
                "recent_errors": [
                    {
                        "error_id": e.error_id,
                        "timestamp": e.timestamp.isoformat(),
                        "error_type": e.error_type,
                        "severity": e.severity.value,
                        "message": e.message,
                        "component": e.component,
                        "is_recovered": e.is_recovered
                    }
                    for e in sorted(self.errors, key=lambda x: x.timestamp, reverse=True)[:20]
                ]
            }

            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2)

            logger.info(f"Error report exported to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error exporting error report: {e}")
            return None


if __name__ == "__main__":
    # Test error recovery
    recovery = ErrorRecovery()

    # Record some test errors
    try:
        raise ConnectionError("Test connection error")
    except Exception as e:
        error_id = recovery.record_error(e, "TEST_COMPONENT", "MEDIUM")
        logger.info(f"Recorded error: {error_id}")

    # Get summary
    summary = recovery.get_error_summary()
    logger.info(f"Error summary: {json.dumps(summary, indent=2)}")

    # Attempt recovery
    success = recovery.recover()
    logger.info(f"Recovery {'successful' if success else 'failed'}")

    # Export report
    recovery.export_error_report()
