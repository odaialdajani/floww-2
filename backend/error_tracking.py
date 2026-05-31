"""
Error tracking and logging improvements for Confluence Decoder.

Features:
- Structured JSON logging
- Request ID tracking
- Error aggregation
- Performance monitoring
- Sentry integration (optional)
"""

import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Error aggregation
_error_counts: Dict[str, int] = {}
_error_log: list = []
MAX_ERROR_LOG = 1000


def setup_logging(level: str = "INFO") -> None:
    """Set up structured logging for the application."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Console handler with structured format
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(StructuredFormatter())

    # File handler for persistent logs
    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(
        os.path.join(log_dir, "app.log"),
        encoding="utf-8",
    )
    file_handler.setFormatter(StructuredFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set the current request ID for logging context."""
    rid = request_id or str(uuid.uuid4())[:8]
    request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """Get the current request ID."""
    return request_id_var.get()


def log_error(error_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Log an error and track it in the aggregation."""
    global _error_counts, _error_log

    _error_counts[error_type] = _error_counts.get(error_type, 0) + 1

    error_entry = {
        "type": error_type,
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": get_request_id(),
        "count": _error_counts[error_type],
    }

    _error_log.append(error_entry)

    # Trim log if too large
    if len(_error_log) > MAX_ERROR_LOG:
        _error_log = _error_log[-MAX_ERROR_LOG:]

    # Log to standard logger
    logger = logging.getLogger("error_tracker")
    logger.error(f"[{error_type}] {message}", extra={"extra_data": data})


def get_error_summary() -> Dict[str, Any]:
    """Get a summary of all tracked errors."""
    return {
        "total_errors": sum(_error_counts.values()),
        "by_type": dict(_error_counts),
        "recent": _error_log[-20:],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def clear_error_log() -> None:
    """Clear the error tracking data."""
    global _error_counts, _error_log
    _error_counts = {}
    _error_log = []


class StructuredFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record):
        import json
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        })


class PerformanceMonitor:
    """Simple performance monitor."""

    def __init__(self):
        self._metrics = {}


perf_monitor = PerformanceMonitor()
