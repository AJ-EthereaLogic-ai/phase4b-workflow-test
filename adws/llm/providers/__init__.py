"""
Compatibility layer that re-exports provider implementations inside
``adws.providers`` so that the folder structure matches the design
documents referenced by the template.
"""

from adws.llm.providers.anthropic import AnthropicProvider
from adws.llm.providers.gemini import GeminiProvider
from adws.llm.providers.openai import OpenAIProvider
from adws.llm.providers.registry import (
    ProviderConfig,
    ProviderRegistry,
    get_provider_registry,
    register_default_providers,
)
from adws.llm.providers.base import BaseProvider

__all__ = [
    "AnthropicProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "ProviderConfig",
    "ProviderRegistry",
    "get_provider_registry",
    "register_default_providers",
    "BaseProvider",
]
