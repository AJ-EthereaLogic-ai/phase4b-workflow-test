"""Structured JSON logging with correlation IDs for ADWS v2.0.

This module provides production-grade structured logging using structlog,
enabling:
- JSON-formatted log output for log aggregation systems
- Correlation IDs for request tracing
- Configurable log levels
- Log rotation support
- Context injection for workflow tracking

Usage:
    from adws.observability import get_logger, configure_logging

    # Configure logging (typically done once at application startup)
    configure_logging(level="INFO", format="json")

    # Get a logger
    logger = get_logger(__name__)

    # Log with context
    logger.info("workflow_started", workflow_id="wf-123", correlation_id="req-456")

    # Use bound logger for persistent context
    logger = logger.bind(workflow_id="wf-123")
    logger.info("event_processed", event_type="task_completed")
"""

import logging
import logging.handlers
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from structlog.types import EventDict, Processor


# Context variable for correlation ID tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


def add_correlation_id(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add correlation ID to log entries.

    Args:
        logger: Logger instance
        method_name: Name of the logging method
        event_dict: Event dictionary to modify

    Returns:
        Modified event dictionary with correlation_id
    """
    correlation_id = correlation_id_var.get()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def add_timestamp(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add ISO8601 timestamp to log entries.

    Args:
        logger: Logger instance
        method_name: Name of the logging method
        event_dict: Event dictionary to modify

    Returns:
        Modified event dictionary with timestamp
    """
    event_dict["timestamp"] = structlog.processors.TimeStamper(fmt="iso", utc=True)(
        logger, method_name, event_dict
    )["timestamp"]
    return event_dict


def add_log_level(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add log level to event dictionary.

    Args:
        logger: Logger instance
        method_name: Name of the logging method
        event_dict: Event dictionary to modify

    Returns:
        Modified event dictionary with level
    """
    if method_name == "warn":
        # structlog uses "warn" but we want "warning" for consistency
        method_name = "warning"
    event_dict["level"] = method_name
    return event_dict


def configure_logging(
    level: str = "INFO",
    format: str = "json",
    log_file: Optional[Path] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """Configure structured logging for ADWS.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format ("json" or "console")
        log_file: Optional path for file logging with rotation
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup files to keep

    Example:
        >>> configure_logging(level="DEBUG", format="console")
        >>> configure_logging(level="INFO", format="json", log_file=Path(".adws/logs/adws.log"))
    """
    # Configure standard library logging
    logging_level = getattr(logging, level.upper(), logging.INFO)

    # Create handlers
    handlers = []

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging_level)
    handlers.append(console_handler)

    # File handler with rotation (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging_level)
        handlers.append(file_handler)

    # Configure root logger
    # Clear existing handlers to allow reconfiguration
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging_level)
    for handler in handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(handler)

    # Configure structlog processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        add_correlation_id,
        add_log_level,
        add_timestamp,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if format == "json":
        # JSON output for production
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        # Console output for development
        structlog.configure(
            processors=shared_processors
            + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog BoundLogger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("event_processed", event_type="workflow_started")
    """
    return structlog.get_logger(name)


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID for request tracing.

    Args:
        correlation_id: Correlation ID (auto-generated if None)

    Returns:
        The correlation ID that was set

    Example:
        >>> correlation_id = set_correlation_id()
        >>> logger.info("request_received", user_id="user-123")
        # Log will include correlation_id automatically
    """
    if correlation_id is None:
        correlation_id = f"req-{uuid.uuid4().hex[:12]}"
    correlation_id_var.set(correlation_id)
    return correlation_id


def clear_correlation_id() -> None:
    """Clear correlation ID from context.

    Example:
        >>> clear_correlation_id()
    """
    correlation_id_var.set(None)


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID.

    Returns:
        Current correlation ID or None

    Example:
        >>> correlation_id = get_correlation_id()
    """
    return correlation_id_var.get()


# Initialize with default configuration
# This ensures backward compatibility with standard logging
try:
    configure_logging(level="INFO", format="console")
except Exception:
    # If configuration fails, fall back to basic logging
    logging.basicConfig(level=logging.INFO)


__all__ = [
    "configure_logging",
    "get_logger",
    "set_correlation_id",
    "clear_correlation_id",
    "get_correlation_id",
]
