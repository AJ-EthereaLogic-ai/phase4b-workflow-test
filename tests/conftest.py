"""
Global pytest configuration for Phase4B Test Project

This file provides shared fixtures and enforces Python version requirements.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add tests directory to sys.path to support imports from test fixtures
_tests_dir = Path(__file__).parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

_MIN_PY_VERSION = (3, 11)


def _verify_python_version() -> str:
    """Return the interpreter version string or exit if <3.11."""
    version_info = sys.version_info
    version_str = ".".join(map(str, version_info[:3]))
    if version_info < _MIN_PY_VERSION:
        pytest.exit(
            f"ERROR: pytest must run on Python 3.11+ (detected {version_str}).",
            returncode=1,
        )
    return version_str


def pytest_report_header(config: pytest.Config) -> str:
    version_str = _verify_python_version()
    return f"Python interpreter verified for pytest: {version_str}"


@pytest.fixture(scope="session", autouse=True)
def register_markers(pytestconfig: pytest.Config) -> None:
    """Register project markers to prevent unknown marker warnings."""
    markers = {
        "unit": "Unit tests that should execute quickly.",
        "integration": "Integration tests hitting multiple components.",
        "slow": "Slow or high-cost tests.",
    }
    for name, description in markers.items():
        pytestconfig.addinivalue_line("markers", f"{name}: {description}")
