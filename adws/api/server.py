"""FastAPI server for ADWS observability endpoints.

This module provides HTTP endpoints for:
- Health checks (/health, /health/liveness, /health/readiness)
- Prometheus metrics (/metrics)
- System information (/info)

The server is designed for production deployment and supports:
- Kubernetes liveness and readiness probes
- Prometheus metrics scraping
- Docker health checks
- Load balancer health checks

Usage:
    # Run with Uvicorn
    uvicorn adws.api.server:app --host 0.0.0.0 --port 8000

    # Run with Gunicorn + Uvicorn workers
    gunicorn adws.api.server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000

Example Health Check Response:
    {
        "status": "healthy",
        "timestamp": "2025-11-20T12:00:00Z",
        "uptime_seconds": 3600.0,
        "components": [
            {
                "name": "database",
                "status": "healthy",
                "message": "Database operational",
                "latency_ms": 5.2,
                "metadata": {"db_path": ".adws/state/workflows.db"}
            }
        ]
    }
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from adws.observability.health import (
    check_health,
    check_liveness,
    check_readiness,
)
from adws.observability.metrics import (
    get_metrics_content_type,
    get_metrics_output,
)
from adws.observability.logging import get_logger

logger = get_logger(__name__)

# FastAPI app instance
app = FastAPI(
    title="ADWS Observability API",
    description="Health checks and metrics for AI Developer Workflow System",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Startup time for uptime calculation
_startup_time = datetime.now(timezone.utc)


@app.on_event("startup")
async def startup_event():
    """Log startup event."""
    logger.info(
        "adws_api_server_started",
        port=os.getenv("ADWS_API_PORT", "8000"),
        host=os.getenv("ADWS_API_HOST", "0.0.0.0"),
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown event."""
    logger.info("adws_api_server_shutdown")


@app.get("/", response_class=JSONResponse)
async def root() -> Dict[str, Any]:
    """Root endpoint with API information.

    Returns:
        API metadata and available endpoints
    """
    return {
        "service": "ADWS Observability API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "liveness": "/health/liveness",
            "readiness": "/health/readiness",
            "metrics": "/metrics",
            "info": "/info",
            "docs": "/docs",
        },
    }


@app.get("/health", response_class=JSONResponse)
async def health() -> Dict[str, Any]:
    """Comprehensive health check endpoint.

    Checks all system components (database, event bus, filesystem, providers)
    and returns detailed status information.

    Returns:
        JSON response with overall status and component-level details

    Response Codes:
        200: All components healthy
        503: One or more components unhealthy
    """
    try:
        # Get default paths from environment or use defaults
        db_path = os.getenv("ADWS_DB_PATH")
        event_bus_dir = os.getenv("ADWS_EVENT_BUS_DIR")
        workspace_dir = os.getenv("ADWS_WORKSPACE_DIR")

        # Convert to Path if provided
        db_path = Path(db_path) if db_path else None
        event_bus_dir = Path(event_bus_dir) if event_bus_dir else None
        workspace_dir = Path(workspace_dir) if workspace_dir else None

        # Run health check
        health_status = check_health(
            db_path=db_path,
            event_bus_dir=event_bus_dir,
            workspace_dir=workspace_dir,
        )

        # Calculate uptime
        uptime = (datetime.now(timezone.utc) - _startup_time).total_seconds()

        # Add uptime to response
        response = health_status.to_dict()
        response["uptime_seconds"] = uptime

        # Return 503 if unhealthy
        status_code = 200 if health_status.is_healthy else 503

        return JSONResponse(
            content=response,
            status_code=status_code,
        )

    except Exception as e:
        logger.error("health_check_error", error=str(e), exc_info=True)
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": "An internal error has occurred.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status_code=503,
        )


@app.get("/health/liveness", response_class=JSONResponse)
async def liveness() -> Dict[str, Any]:
    """Kubernetes liveness probe endpoint.

    Simple check to determine if the application should be restarted.
    Only checks basic filesystem operations.

    Returns:
        JSON response with liveness status

    Response Codes:
        200: Application is alive
        503: Application should be restarted
    """
    try:
        is_alive = check_liveness()

        status_code = 200 if is_alive else 503
        status = "alive" if is_alive else "dead"

        return JSONResponse(
            content={
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status_code=status_code,
        )

    except Exception as e:
        logger.error("liveness_check_error", error=str(e), exc_info=True)
        return JSONResponse(
            content={
                "status": "dead",
                "error": "An internal error occurred. The application is not alive.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status_code=503,
        )


@app.get("/health/readiness", response_class=JSONResponse)
async def readiness() -> Dict[str, Any]:
    """Kubernetes readiness probe endpoint.

    Checks if the application is ready to accept traffic.
    Validates critical components (database, event bus, providers).

    Returns:
        JSON response with readiness status

    Response Codes:
        200: Ready to accept traffic
        503: Not ready (initializing or unhealthy)
    """
    try:
        # Get default paths from environment or use defaults
        db_path = os.getenv("ADWS_DB_PATH")
        event_bus_dir = os.getenv("ADWS_EVENT_BUS_DIR")

        # Convert to Path if provided
        db_path = Path(db_path) if db_path else None
        event_bus_dir = Path(event_bus_dir) if event_bus_dir else None

        is_ready = check_readiness(
            db_path=db_path,
            event_bus_dir=event_bus_dir,
        )

        status_code = 200 if is_ready else 503
        status = "ready" if is_ready else "not_ready"

        return JSONResponse(
            content={
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status_code=status_code,
        )

    except Exception as e:
        logger.error("readiness_check_error", error=str(e), exc_info=True)
        return JSONResponse(
            content={
                "status": "not_ready",
                "error": "An internal error occurred. The application is not ready.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status_code=503,
        )


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format for scraping.

    Metrics include:
    - adws_workflow_duration_seconds: Workflow execution duration
    - adws_workflows_total: Total workflows by state
    - adws_workflows_active: Currently active workflows
    - adws_events_total: Total events published
    - adws_cost_usd_total: Total cost in USD
    - adws_llm_tokens_total: Total LLM tokens used
    - adws_health_status: Component health status (1=healthy, 0=unhealthy)

    Returns:
        Plain text response in Prometheus format
    """
    try:
        metrics_output = get_metrics_output()
        content_type = get_metrics_content_type()

        return Response(
            content=metrics_output,
            media_type=content_type,
        )

    except Exception as e:
        logger.error("metrics_export_error", error=str(e), exc_info=True)
        return Response(
            content=f"# Error exporting metrics: {e}\n",
            media_type="text/plain",
            status_code=500,
        )


@app.get("/info", response_class=JSONResponse)
async def info() -> Dict[str, Any]:
    """System information endpoint.

    Returns general system information and configuration details.

    Returns:
        JSON response with system information
    """
    uptime = (datetime.now(timezone.utc) - _startup_time).total_seconds()

    return {
        "service": "ADWS",
        "version": "2.0.0",
        "uptime_seconds": uptime,
        "startup_time": _startup_time.isoformat(),
        "python_version": os.sys.version,
        "environment": {
            "log_level": os.getenv("ADWS_LOG_LEVEL", "INFO"),
            "metrics_enabled": os.getenv("ADWS_METRICS_ENABLED", "true"),
            "health_checks_enabled": os.getenv("ADWS_HEALTH_CHECKS_ENABLED", "true"),
        },
        "paths": {
            "workspace": os.getenv("ADWS_WORKSPACE_DIR", ".adws"),
            "database": os.getenv("ADWS_DB_PATH", ".adws/state/workflows.db"),
            "event_bus": os.getenv("ADWS_EVENT_BUS_DIR", ".adws/events"),
        },
    }


# Health check for Docker HEALTHCHECK instruction
@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    """Simple health check for Docker HEALTHCHECK.

    Returns:
        "OK" if healthy, error message otherwise
    """
    try:
        is_alive = check_liveness()
        return "OK" if is_alive else "UNHEALTHY"
    except Exception as e:
        return f"ERROR: {e}"
