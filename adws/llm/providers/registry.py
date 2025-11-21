"""
Registry utilities mirroring :mod:`adws.providers.registry`.
"""

from adws.providers.interfaces import ProviderConfig
from adws.providers.registry import (
    ProviderRegistry,
    get_provider_registry,
    register_default_providers,
)

__all__ = [
    "ProviderRegistry",
    "ProviderConfig",
    "get_provider_registry",
    "register_default_providers",
]
