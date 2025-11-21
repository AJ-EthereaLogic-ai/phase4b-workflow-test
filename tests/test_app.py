"""
Basic tests for Phase4B Test Project
"""
import pytest
from app import __version__


def test_version():
    """Test that version is defined."""
    assert __version__ == "0.1.0"


def test_import():
    """Test that app module can be imported."""
    import app
    assert app is not None


@pytest.mark.asyncio
async def test_async_example():
    """Example async test to verify pytest-asyncio is working."""
    result = await example_async_function()
    assert result is True


async def example_async_function():
    """Example async function for testing."""
    return True
