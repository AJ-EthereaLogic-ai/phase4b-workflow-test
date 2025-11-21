"""Enhanced Observability and Monitoring Infrastructure for ADWS v2.0.

This module provides production-grade observability capabilities including:
- Structured JSON logging with correlation IDs
- Prometheus-compatible metrics export
- Health check endpoints for system components
- Integration with monitoring and alerting systems

Components:
    - logging: Structured logging with structlog
    - metrics: Prometheus metrics export
    - health: Health check endpoints

Usage:
    from adws.observability import get_logger, track_metric, check_health

    logger = get_logger(__name__)
    logger.info("workflow_started", workflow_id="wf-123")

    track_metric("workflow_duration_seconds", 1.23)

    status = check_health()
"""

from adws.observability.logging import get_logger, configure_logging
from adws.observability.metrics import (
    track_metric,
    increment_counter,
    record_histogram,
    set_gauge,
    get_metrics_registry,
)
from adws.observability.health import check_health, HealthStatus

__all__ = [
    "get_logger",
    "configure_logging",
    "track_metric",
    "increment_counter",
    "record_histogram",
    "set_gauge",
    "get_metrics_registry",
    "check_health",
    "HealthStatus",
]
