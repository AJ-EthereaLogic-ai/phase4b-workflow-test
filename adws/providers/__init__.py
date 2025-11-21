"""
Multi-LLM Provider Abstraction Layer

This module provides a flexible abstraction layer for integrating multiple
LLM providers (Claude, OpenAI, Gemini) with unified interfaces, configuration
management, and runtime provider selection.

Key Components:
    - LLMProvider: Protocol defining provider interface
    - PromptRequest/Response: Standardized request/response models
    - ProviderRegistry: Central registry for provider management
    - BaseProvider: Abstract base class with common functionality

Design Principles:
    - Protocol-based abstraction for flexibility
    - Async-first for parallel execution
    - Type-safe with full mypy compliance
    - Event-driven integration with existing EventBus
    - Cost tracking built into every operation

Example:
    >>> from adws.providers import get_provider_registry, PromptRequest
    >>> registry = get_provider_registry()
    >>> provider = registry.get("claude")
    >>> request = PromptRequest(
    ...     prompt="Explain quantum computing",
    ...     model="claude-sonnet-4",
    ...     adw_id="adw_123",
    ...     slash_command="/explain",
    ...     working_dir="/tmp"
    ... )
    >>> response = await provider.execute_async(request)
    >>> print(f"Cost: ${response.cost_usd:.4f}")
"""

from adws.providers.interfaces import (
    LLMProvider,
    PromptRequest,
    PromptResponse,
    RetryCode,
    ProviderConfig,
)
from adws.providers.registry import (
    ProviderRegistry,
    get_provider_registry,
    register_default_providers,
)
from adws.providers.base import BaseProvider

__all__ = [
    "LLMProvider",
    "PromptRequest",
    "PromptResponse",
    "RetryCode",
    "ProviderConfig",
    "ProviderRegistry",
    "get_provider_registry",
    "register_default_providers",
    "BaseProvider",
]
