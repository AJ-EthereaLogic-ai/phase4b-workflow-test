"""HTTP API for ADWS observability endpoints.

This module provides HTTP endpoints for health checks and metrics,
enabling production deployment with monitoring and orchestration support.
"""

from adws.api.server import app

__all__ = ["app"]
