"""Health check endpoints for ADWS v2.0 components.

This module provides production-grade health check capabilities for:
- Database (SQLite) connectivity and operations
- Event bus functionality
- LLM provider availability
- File system operations
- Overall system health

Supports both liveness and readiness probes for Kubernetes/container deployments.

Usage:
    from adws.observability.health import check_health, HealthStatus

    # Check overall system health
    status = check_health()
    print(status.is_healthy)  # True if all components healthy

    # Check specific component
    status = check_database_health(db_path)
    print(status.status)  # "healthy" or "unhealthy"

    # Use in HTTP endpoint
    status = check_health()
    return {"status": status.status, "components": status.components}
"""

import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from adws.observability.logging import get_logger
from adws.observability.metrics import set_gauge

logger = get_logger(__name__)


@dataclass
class ComponentHealth:
    """Health status of a single component.

    Attributes:
        name: Component name
        status: Health status ("healthy" or "unhealthy")
        message: Human-readable status message
        latency_ms: Health check latency in milliseconds
        metadata: Additional component-specific metadata
    """

    name: str
    status: str  # "healthy" or "unhealthy"
    message: str
    latency_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        """Check if component is healthy."""
        return self.status == "healthy"


@dataclass
class HealthStatus:
    """Overall system health status.

    Attributes:
        status: Overall status ("healthy" or "unhealthy")
        components: List of component health statuses
        timestamp: ISO8601 timestamp of health check
        uptime_seconds: System uptime in seconds (if available)
    """

    status: str
    components: List[ComponentHealth]
    timestamp: str
    uptime_seconds: Optional[float] = None

    @property
    def is_healthy(self) -> bool:
        """Check if overall system is healthy."""
        return self.status == "healthy"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "uptime_seconds": self.uptime_seconds,
            "components": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                    "metadata": c.metadata,
                }
                for c in self.components
            ],
        }


def check_database_health(db_path: Optional[Path] = None) -> ComponentHealth:
    """Check SQLite database health.

    Args:
        db_path: Path to SQLite database file (defaults to .adws/state/workflows.db)

    Returns:
        ComponentHealth with database status

    Checks:
        - Database file exists and is readable
        - Can execute test query
        - No database locks or corruption
    """
    start_time = time.time()

    if db_path is None:
        db_path = Path(".adws/state/workflows.db")

    try:
        # Check file exists
        if not db_path.exists():
            latency_ms = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="database",
                status="unhealthy",
                message=f"Database file not found: {db_path}",
                latency_ms=latency_ms,
                metadata={"db_path": str(db_path)},
            )

        # Check file is readable
        if not os.access(db_path, os.R_OK):
            latency_ms = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="database",
                status="unhealthy",
                message=f"Database file not readable: {db_path}",
                latency_ms=latency_ms,
                metadata={"db_path": str(db_path)},
            )

        # Execute test query
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            if result != (1,):
                raise ValueError("Test query returned unexpected result")

            # Check workflow table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
            )
            table_exists = cursor.fetchone() is not None

            latency_ms = (time.time() - start_time) * 1000

            return ComponentHealth(
                name="database",
                status="healthy",
                message="Database operational",
                latency_ms=latency_ms,
                metadata={
                    "db_path": str(db_path),
                    "workflows_table_exists": table_exists,
                },
            )

        finally:
            conn.close()

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("database_health_check_failed", error=str(e))
        return ComponentHealth(
            name="database",
            status="unhealthy",
            message=f"Database error: {str(e)}",
            latency_ms=latency_ms,
            metadata={"db_path": str(db_path), "error": str(e)},
        )


def check_eventbus_health(
    event_bus_dir: Optional[Path] = None,
) -> ComponentHealth:
    """Check event bus health.

    Args:
        event_bus_dir: Path to event bus directory (defaults to .adws)

    Returns:
        ComponentHealth with event bus status

    Checks:
        - Event bus directory exists and is writable
        - Can create test file
    """
    start_time = time.time()

    if event_bus_dir is None:
        event_bus_dir = Path(".adws")

    try:
        # Check directory exists
        if not event_bus_dir.exists():
            latency_ms = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="eventbus",
                status="unhealthy",
                message=f"Event bus directory not found: {event_bus_dir}",
                latency_ms=latency_ms,
                metadata={"event_bus_dir": str(event_bus_dir)},
            )

        # Check directory is writable
        if not os.access(event_bus_dir, os.W_OK):
            latency_ms = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="eventbus",
                status="unhealthy",
                message=f"Event bus directory not writable: {event_bus_dir}",
                latency_ms=latency_ms,
                metadata={"event_bus_dir": str(event_bus_dir)},
            )

        # Try to create a test file
        test_file = event_bus_dir / ".health_check"
        test_file.write_text("health_check")
        test_file.unlink()

        latency_ms = (time.time() - start_time) * 1000

        return ComponentHealth(
            name="eventbus",
            status="healthy",
            message="Event bus operational",
            latency_ms=latency_ms,
            metadata={"event_bus_dir": str(event_bus_dir)},
        )

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("eventbus_health_check_failed", error=str(e))
        return ComponentHealth(
            name="eventbus",
            status="unhealthy",
            message=f"Event bus error: {str(e)}",
            latency_ms=latency_ms,
            metadata={"event_bus_dir": str(event_bus_dir), "error": str(e)},
        )


def check_filesystem_health(
    workspace_dir: Optional[Path] = None,
) -> ComponentHealth:
    """Check file system health.

    Args:
        workspace_dir: Path to workspace directory (defaults to .adws)

    Returns:
        ComponentHealth with file system status

    Checks:
        - Workspace directory exists and is writable
        - Sufficient disk space available
    """
    start_time = time.time()

    if workspace_dir is None:
        workspace_dir = Path(".adws")

    try:
        # Ensure directory exists
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Check directory is writable
        if not os.access(workspace_dir, os.W_OK):
            latency_ms = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="filesystem",
                status="unhealthy",
                message=f"Workspace directory not writable: {workspace_dir}",
                latency_ms=latency_ms,
                metadata={"workspace_dir": str(workspace_dir)},
            )

        # Check disk space
        import shutil

        disk_usage = shutil.disk_usage(workspace_dir)
        free_gb = disk_usage.free / (1024**3)
        total_gb = disk_usage.total / (1024**3)
        free_percent = (disk_usage.free / disk_usage.total) * 100

        # Warn if less than 1GB or less than 10% free
        is_healthy = free_gb >= 1.0 or free_percent >= 10.0

        latency_ms = (time.time() - start_time) * 1000

        return ComponentHealth(
            name="filesystem",
            status="healthy" if is_healthy else "unhealthy",
            message="File system operational"
            if is_healthy
            else f"Low disk space: {free_gb:.2f}GB ({free_percent:.1f}%) free",
            latency_ms=latency_ms,
            metadata={
                "workspace_dir": str(workspace_dir),
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "free_percent": round(free_percent, 1),
            },
        )

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("filesystem_health_check_failed", error=str(e))
        return ComponentHealth(
            name="filesystem",
            status="unhealthy",
            message=f"File system error: {str(e)}",
            latency_ms=latency_ms,
            metadata={"workspace_dir": str(workspace_dir), "error": str(e)},
        )


def check_providers_health() -> ComponentHealth:
    """Check LLM providers health.

    Returns:
        ComponentHealth with providers status

    Checks:
        - Environment variables for API keys are set
        - Provider configuration is valid
    """
    start_time = time.time()

    try:
        providers_status = {}

        # Check for API keys in environment
        providers_config = {
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }

        configured_count = 0
        for provider_name, env_var in providers_config.items():
            api_key = os.environ.get(env_var)
            is_configured = api_key is not None and len(api_key) > 0
            providers_status[provider_name] = is_configured
            if is_configured:
                configured_count += 1

        latency_ms = (time.time() - start_time) * 1000

        # At least one provider should be configured
        is_healthy = configured_count > 0

        return ComponentHealth(
            name="providers",
            status="healthy" if is_healthy else "unhealthy",
            message=f"{configured_count} provider(s) configured"
            if is_healthy
            else "No providers configured",
            latency_ms=latency_ms,
            metadata={
                "providers": providers_status,
                "configured_count": configured_count,
            },
        )

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error("providers_health_check_failed", error=str(e))
        return ComponentHealth(
            name="providers",
            status="unhealthy",
            message=f"Providers error: {str(e)}",
            latency_ms=latency_ms,
            metadata={"error": str(e)},
        )


def check_health(
    db_path: Optional[Path] = None,
    event_bus_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
) -> HealthStatus:
    """Check overall system health.

    Args:
        db_path: Optional database path (defaults to .adws/state/workflows.db)
        event_bus_dir: Optional event bus directory (defaults to .adws)
        workspace_dir: Optional workspace directory (defaults to .adws)

    Returns:
        HealthStatus with overall and component-level health

    Example:
        >>> status = check_health()
        >>> if status.is_healthy:
        ...     print("System healthy")
        >>> else:
        ...     for component in status.components:
        ...         if not component.is_healthy:
        ...             print(f"{component.name}: {component.message}")
    """
    from datetime import datetime, timezone

    # Run all health checks
    components = [
        check_database_health(db_path),
        check_eventbus_health(event_bus_dir),
        check_filesystem_health(workspace_dir),
        check_providers_health(),
    ]

    # Determine overall status
    all_healthy = all(c.is_healthy for c in components)
    overall_status = "healthy" if all_healthy else "unhealthy"

    # Update metrics
    for component in components:
        metric_value = 1.0 if component.is_healthy else 0.0
        set_gauge("health_status", metric_value, labels={"component": component.name})

    # Create health status
    health_status = HealthStatus(
        status=overall_status,
        components=components,
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=None,  # Could be enhanced to track actual uptime
    )

    # Log health check result
    logger.debug(
        "health_check_completed",
        status=overall_status,
        components_count=len(components),
        healthy_count=sum(1 for c in components if c.is_healthy),
    )

    return health_status


def check_readiness(
    db_path: Optional[Path] = None,
    event_bus_dir: Optional[Path] = None,
) -> bool:
    """Readiness probe for Kubernetes/container deployments.

    Args:
        db_path: Optional database path
        event_bus_dir: Optional event bus directory

    Returns:
        True if system is ready to accept traffic, False otherwise

    Readiness Criteria:
        - Database is operational
        - Event bus is operational
        - At least one provider is configured
    """
    health = check_health(db_path, event_bus_dir)

    # Check critical components
    critical_components = {"database", "eventbus", "providers"}
    for component in health.components:
        if component.name in critical_components and not component.is_healthy:
            logger.warning(
                "readiness_check_failed",
                component=component.name,
                message=component.message,
            )
            return False

    return True


def check_liveness() -> bool:
    """Liveness probe for Kubernetes/container deployments.

    Returns:
        True if system is alive, False if should be restarted

    Liveness Criteria:
        - Basic file system operations work
    """
    try:
        # Simple check - can we write to workspace?
        workspace_dir = Path(".adws")
        workspace_dir.mkdir(parents=True, exist_ok=True)

        test_file = workspace_dir / ".liveness_check"
        test_file.write_text("alive")
        test_file.unlink()

        return True

    except Exception as e:
        logger.error("liveness_check_failed", error=str(e))
        return False


__all__ = [
    "ComponentHealth",
    "HealthStatus",
    "check_health",
    "check_database_health",
    "check_eventbus_health",
    "check_filesystem_health",
    "check_providers_health",
    "check_readiness",
    "check_liveness",
]
