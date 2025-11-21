"""
API package for Phase4B Test Project.

Developers can drop framework-specific routers (FastAPI APIRouter,
Flask Blueprints, etc.) inside this package. The placeholder ensures
the directory exists so the template structure matches the project
scope specification.
"""

from __future__ import annotations

API_VERSION = "0.1.0"


def describe() -> str:
    """Return a short string describing the API surface."""
    return f"{API_VERSION} (placeholder)"


__all__ = ["API_VERSION", "describe"]
