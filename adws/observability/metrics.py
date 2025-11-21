"""Prometheus-compatible metrics export for ADWS v2.0.

This module provides production-grade metrics collection and export using
Prometheus client library, enabling:
- Workflow metrics (duration, count, state)
- Event metrics (throughput, errors, latency)
- Cost tracking (total, per-workflow, tokens)
- Performance metrics (query latency, throughput)
- StatsD compatibility

Usage:
    from adws.observability.metrics import (
        increment_counter,
        record_histogram,
        set_gauge,
        track_duration,
    )

    # Increment a counter
    increment_counter("workflows_total", labels={"state": "completed"})

    # Record histogram value
    record_histogram("workflow_duration_seconds", 1.23, labels={"workflow_id": "wf-123"})

    # Set gauge value
    set_gauge("workflows_active", 5)

    # Track duration with context manager
    with track_duration("event_publish_duration_seconds"):
        bus.publish(event)
"""

import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)


# Global registry for metrics
_registry = CollectorRegistry()

# Workflow Metrics
workflow_duration_seconds = Histogram(
    "adws_workflow_duration_seconds",
    "Duration of workflow execution in seconds",
    ["workflow_id", "state"],
    registry=_registry,
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float("inf")),
)

workflows_total = Counter(
    "adws_workflows_total",
    "Total number of workflows by state",
    ["state"],
    registry=_registry,
)

workflows_active = Gauge(
    "adws_workflows_active",
    "Number of currently active workflows",
    registry=_registry,
)

# Event Metrics
events_total = Counter(
    "adws_events_total",
    "Total number of events published by type",
    ["event_type"],
    registry=_registry,
)

event_publish_duration_seconds = Histogram(
    "adws_event_publish_duration_seconds",
    "Duration of event publication in seconds",
    ["event_type"],
    registry=_registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, float("inf")),
)

event_subscriber_errors_total = Counter(
    "adws_event_subscriber_errors_total",
    "Total number of subscriber errors by event type",
    ["event_type", "subscriber_id"],
    registry=_registry,
)

# Cost Metrics
cost_usd_total = Counter(
    "adws_cost_usd_total",
    "Total cost in USD",
    ["provider"],
    registry=_registry,
)

cost_per_workflow_usd = Gauge(
    "adws_cost_per_workflow_usd",
    "Cost per workflow in USD",
    ["workflow_id", "provider"],
    registry=_registry,
)

llm_tokens_total = Counter(
    "adws_llm_tokens_total",
    "Total number of LLM tokens used",
    ["provider", "token_type"],  # token_type: input, output
    registry=_registry,
)

# Performance Metrics
state_query_duration_seconds = Histogram(
    "adws_state_query_duration_seconds",
    "Duration of state queries in seconds",
    ["query_type"],
    registry=_registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, float("inf")),
)

event_throughput_per_second = Gauge(
    "adws_event_throughput_per_second",
    "Event throughput in events per second",
    registry=_registry,
)

# Health Metrics
health_status = Gauge(
    "adws_health_status",
    "Health status of components (1=healthy, 0=unhealthy)",
    ["component"],
    registry=_registry,
)


def increment_counter(
    metric_name: str,
    value: float = 1.0,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Increment a counter metric.

    Args:
        metric_name: Name of the counter (without adws_ prefix)
        value: Amount to increment by (default: 1.0)
        labels: Optional labels as key-value pairs

    Example:
        >>> increment_counter("workflows_total", labels={"state": "completed"})
        >>> increment_counter("events_total", labels={"event_type": "workflow_started"})
    """
    labels = labels or {}
    metric = _get_metric(metric_name)
    if metric and isinstance(metric, Counter):
        if labels:
            metric.labels(**labels).inc(value)
        else:
            metric.inc(value)


def record_histogram(
    metric_name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Record a histogram observation.

    Args:
        metric_name: Name of the histogram (without adws_ prefix)
        value: Value to observe
        labels: Optional labels as key-value pairs

    Example:
        >>> record_histogram("workflow_duration_seconds", 1.23, labels={"workflow_id": "wf-123", "state": "completed"})
        >>> record_histogram("event_publish_duration_seconds", 0.005, labels={"event_type": "task_completed"})
    """
    labels = labels or {}
    metric = _get_metric(metric_name)
    if metric and isinstance(metric, Histogram):
        if labels:
            metric.labels(**labels).observe(value)
        else:
            metric.observe(value)


def set_gauge(
    metric_name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Set a gauge metric value.

    Args:
        metric_name: Name of the gauge (without adws_ prefix)
        value: Value to set
        labels: Optional labels as key-value pairs

    Example:
        >>> set_gauge("workflows_active", 5)
        >>> set_gauge("cost_per_workflow_usd", 0.25, labels={"workflow_id": "wf-123", "provider": "claude"})
    """
    labels = labels or {}
    metric = _get_metric(metric_name)
    if metric and isinstance(metric, Gauge):
        if labels:
            metric.labels(**labels).set(value)
        else:
            metric.set(value)


def increment_gauge(
    metric_name: str,
    value: float = 1.0,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Increment a gauge metric.

    Args:
        metric_name: Name of the gauge (without adws_ prefix)
        value: Amount to increment by (default: 1.0)
        labels: Optional labels as key-value pairs

    Example:
        >>> increment_gauge("workflows_active", 1)
    """
    labels = labels or {}
    metric = _get_metric(metric_name)
    if metric and isinstance(metric, Gauge):
        if labels:
            metric.labels(**labels).inc(value)
        else:
            metric.inc(value)


def decrement_gauge(
    metric_name: str,
    value: float = 1.0,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Decrement a gauge metric.

    Args:
        metric_name: Name of the gauge (without adws_ prefix)
        value: Amount to decrement by (default: 1.0)
        labels: Optional labels as key-value pairs

    Example:
        >>> decrement_gauge("workflows_active", 1)
    """
    labels = labels or {}
    metric = _get_metric(metric_name)
    if metric and isinstance(metric, Gauge):
        if labels:
            metric.labels(**labels).dec(value)
        else:
            metric.dec(value)


@contextmanager
def track_duration(
    metric_name: str,
    labels: Optional[Dict[str, str]] = None,
) -> Iterator[None]:
    """Context manager to track duration of an operation.

    Args:
        metric_name: Name of the histogram metric (without adws_ prefix)
        labels: Optional labels as key-value pairs

    Yields:
        None

    Example:
        >>> with track_duration("event_publish_duration_seconds", labels={"event_type": "workflow_started"}):
        ...     bus.publish(event)
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        record_histogram(metric_name, duration, labels)


def track_metric(
    metric_name: str,
    value: Optional[float] = None,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Generic metric tracking function.

    Automatically determines the metric type and calls the appropriate function.

    Args:
        metric_name: Name of the metric (without adws_ prefix)
        value: Value to record (if None, assumes counter with value 1.0)
        labels: Optional labels as key-value pairs

    Example:
        >>> track_metric("workflows_total", labels={"state": "completed"})
        >>> track_metric("workflow_duration_seconds", 1.23, labels={"workflow_id": "wf-123"})
    """
    metric = _get_metric(metric_name)
    if not metric:
        return

    if isinstance(metric, Counter):
        increment_counter(metric_name, value or 1.0, labels)
    elif isinstance(metric, Histogram):
        if value is not None:
            record_histogram(metric_name, value, labels)
    elif isinstance(metric, Gauge):
        if value is not None:
            set_gauge(metric_name, value, labels)


def get_metrics_registry() -> CollectorRegistry:
    """Get the global metrics registry.

    Returns:
        Prometheus CollectorRegistry instance

    Example:
        >>> registry = get_metrics_registry()
        >>> metrics_output = generate_latest(registry)
    """
    return _registry


def get_metrics_output() -> bytes:
    """Get Prometheus-formatted metrics output.

    Returns:
        Bytes containing Prometheus-formatted metrics

    Example:
        >>> output = get_metrics_output()
        >>> print(output.decode('utf-8'))
    """
    return generate_latest(_registry)


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics.

    Returns:
        Content type string

    Example:
        >>> content_type = get_metrics_content_type()
        >>> # Use in HTTP response: {"Content-Type": content_type}
    """
    return CONTENT_TYPE_LATEST


def _get_metric(metric_name: str) -> Any:
    """Get metric by name.

    Args:
        metric_name: Name of the metric (with or without adws_ prefix)

    Returns:
        Metric instance or None
    """
    # Remove prefix if present (variable names don't have adws_ prefix)
    if metric_name.startswith("adws_"):
        metric_name = metric_name[5:]  # Remove "adws_"

    # Get from globals
    return globals().get(metric_name)


# Export key metrics objects for direct access
__all__ = [
    "increment_counter",
    "record_histogram",
    "set_gauge",
    "increment_gauge",
    "decrement_gauge",
    "track_duration",
    "track_metric",
    "get_metrics_registry",
    "get_metrics_output",
    "get_metrics_content_type",
    # Metric objects
    "workflow_duration_seconds",
    "workflows_total",
    "workflows_active",
    "events_total",
    "event_publish_duration_seconds",
    "event_subscriber_errors_total",
    "cost_usd_total",
    "cost_per_workflow_usd",
    "llm_tokens_total",
    "state_query_duration_seconds",
    "event_throughput_per_second",
    "health_status",
]
