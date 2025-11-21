"""
Server scaffolding for Phase4B Test Project.

The cookiecutter template ships an opinionated-but-lightweight skeleton
that keeps the `app/` directory aligned with the ADWS design docs:

* `app/server/` - Backend entrypoint and API wiring lives here.
* `app/client/` - Frontend assets (HTML/CSS/JS) live alongside backend code.

Nothing in this module is framework-specific; feel free to replace the
helpers below with FastAPI, Django, Flask, or any stack that fits your
project. The defaults merely provide a discoverable starting point for
generated projects and keep static analysis tools happy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict


@dataclass
class RouteDefinition:
    """
    Simple representation of a backend route.

    Generated projects can replace this with their preferred framework,
    but storing route metadata in a structured format helps ADWS
    workflows reason about available endpoints when generating tests.
    """

    path: str
    method: str = "GET"
    handler: Callable[..., Dict[str, str]] | None = None
    description: str = ""


@dataclass
class ServerApplication:
    """
    Minimal registry for backend routes.

    The object exposes enough structure for workflow runners and the
    default tests to introspect which endpoints exist, while staying
    lightweight enough to discard if the user prefers another pattern.
    """

    name: str
    routes: Dict[str, RouteDefinition] = field(default_factory=dict)

    def add_route(self, route: RouteDefinition) -> None:
        """Register a new route."""
        key = f"{route.method.upper()} {route.path}"
        self.routes[key] = route

    def available_routes(self) -> Dict[str, RouteDefinition]:
        """Return a copy of the known routes for debugging or tests."""
        return dict(self.routes)


def create_app(name: str | None = None) -> ServerApplication:
    """
    Factory that returns a `ServerApplication` with a basic health route.

    Code generators and developers can import this function inside
    `main.py` to obtain a working instance before wiring up a web server.
    """

    app = ServerApplication(name=name or "phase4b_test")
    app.add_route(
        RouteDefinition(
            path="/healthz",
            method="GET",
            description="Default health-check endpoint used by ADWS smoke tests",
            handler=lambda: {"status": "ok"},
        )
    )
    return app


__all__ = ["ServerApplication", "RouteDefinition", "create_app"]
