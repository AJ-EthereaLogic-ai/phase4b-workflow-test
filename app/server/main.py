"""
Entrypoint for the backend portion of Phase4B Test Project.

The module keeps runtime concerns separate from the ADWS automation
layer so teams can quickly replace this scaffolding with their preferred
framework. By default we only expose a `bootstrap()` helper that returns
the lightweight `ServerApplication` registry defined in
`app.server.__init__`.
"""

from __future__ import annotations

from app.server import ServerApplication, create_app


def bootstrap() -> ServerApplication:
    """
    Return a configured backend application instance.

    Downstream scripts (CLI runners, gunicorn, uvicorn, etc.) can call
    this function to obtain the app without importing framework-specific
    globals at module import time.
    """

    return create_app()


if __name__ == "__main__":
    application = bootstrap()
    print(
        f"Bootstrapped backend '{application.name}' "
        f"with {len(application.routes)} default route(s)."
    )
