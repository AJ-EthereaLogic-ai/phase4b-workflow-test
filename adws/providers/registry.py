"""
Provider Registry

Central registry for LLM provider management, registration, and lookup.
"""

from typing import Dict, Optional, List
from adws.providers.interfaces import LLMProvider, ProviderConfig


class ProviderRegistry:
    """
    Central registry of available LLM providers.

    Manages provider lifecycle and lookup operations. Providers must
    be registered before use.

    Thread-safe: This implementation is not thread-safe. If used in
    multi-threaded contexts, external synchronization is required.

    Example:
        >>> registry = ProviderRegistry()
        >>> config = ProviderConfig(name="claude", enabled=True)
        >>> registry.register("claude", claude_provider, config)
        >>> provider = registry.get("claude")
        >>> if provider:
        ...     response = provider.execute(request)
    """

    def __init__(self):
        """Initialize an empty registry"""
        self._providers: Dict[str, LLMProvider] = {}
        self._configs: Dict[str, ProviderConfig] = {}

    def register(
        self,
        name: str,
        provider: LLMProvider,
        config: ProviderConfig
    ) -> None:
        """
        Register a provider.

        Args:
            name: Provider name (e.g., 'claude', 'openai', 'gemini')
            provider: Provider implementation
            config: Provider configuration

        Raises:
            ValueError: If provider name is invalid or already registered
            TypeError: If provider or config types are invalid

        Example:
            >>> registry = ProviderRegistry()
            >>> config = ProviderConfig(name="test", enabled=True)
            >>> registry.register("test", test_provider, config)
        """
        # Validate name
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Provider name must be a non-empty string")

        # Validate config type
        if not isinstance(config, ProviderConfig):
            raise TypeError(f"config must be an instance of ProviderConfig, got {type(config).__name__}")

        # Skip disabled providers
        if not config.enabled:
            return

        # Validate provider implements protocol
        required_attrs = ['name', 'execute', 'supports_model', 'max_context_length',
                          'cost_per_1k_tokens', 'estimate_tokens']
        if not all(hasattr(provider, attr) for attr in required_attrs):
            raise TypeError(f"provider must be an instance of LLMProvider")

        # Check for duplicate registration
        if name in self._providers:
            raise ValueError(f"Provider already registered: {name}")

        self._providers[name] = provider
        self._configs[name] = config

    def unregister(self, name: str) -> None:
        """
        Unregister a provider.

        Removes the provider from the registry. If the provider
        doesn't exist, this is a no-op (doesn't raise an error).

        Args:
            name: Provider name

        Example:
            >>> registry.unregister("test")
        """
        self._providers.pop(name, None)
        self._configs.pop(name, None)

    def get(self, name: str) -> Optional[LLMProvider]:
        """
        Get provider by name.

        Args:
            name: Provider name

        Returns:
            Provider instance or None if not registered

        Example:
            >>> provider = registry.get("claude")
            >>> if provider:
            ...     response = provider.execute(request)
        """
        return self._providers.get(name)

    def has_provider(self, name: str) -> bool:
        """
        Check if provider is registered.

        Args:
            name: Provider name

        Returns:
            True if provider is registered, False otherwise

        Example:
            >>> if registry.has_provider("claude"):
            ...     provider = registry.get("claude")
        """
        return name in self._providers

    def list_providers(self) -> List[str]:
        """
        Get sorted list of registered provider names.

        Returns:
            Sorted list of provider names

        Example:
            >>> for name in registry.list_providers():
            ...     print(f"Available: {name}")
        """
        return sorted(self._providers.keys())

    def get_for_model(self, model: str) -> Optional[LLMProvider]:
        """
        Find provider that supports model.

        Searches through registered providers to find the first
        one that supports the specified model.

        Args:
            model: Model identifier (e.g., 'claude-sonnet-4', 'gpt-4')

        Returns:
            First provider that supports model, or None if no provider found

        Example:
            >>> provider = registry.get_for_model("gpt-4")
            >>> if provider:
            ...     print(f"Found provider: {provider.name}")
        """
        for provider in self._providers.values():
            if provider.supports_model(model):
                return provider
        return None

    def has_provider_for_model(self, model: str) -> bool:
        """
        Check if any provider supports the given model.

        Args:
            model: Model identifier (e.g., 'claude-sonnet-4', 'gpt-4')

        Returns:
            True if at least one provider supports the model, False otherwise

        Example:
            >>> if registry.has_provider_for_model("gpt-4"):
            ...     print("GPT-4 is available")
        """
        return self.get_for_model(model) is not None

    def get_config(self, name: str) -> Optional[ProviderConfig]:
        """
        Get configuration for provider.

        Args:
            name: Provider name

        Returns:
            Provider configuration or None if not registered

        Example:
            >>> config = registry.get_config("claude")
            >>> if config:
            ...     print(f"Timeout: {config.timeout_seconds}s")
        """
        return self._configs.get(name)

    def get_retry_code(self, name: str):
        """
        Get retry code from provider if it has one.

        Args:
            name: Provider name

        Returns:
            Retry code if provider has one, None otherwise

        Example:
            >>> code = registry.get_retry_code("claude")
        """
        provider = self._providers.get(name)
        if provider is None:
            return None
        return getattr(provider, 'retry_code', None)


# Global registry singleton
_global_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """
    Get the global provider registry.

    Returns the singleton instance of the provider registry.
    Creates it on first access.

    Returns:
        Global ProviderRegistry instance

    Example:
        >>> registry = get_provider_registry()
        >>> provider = registry.get("claude")
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ProviderRegistry()
    return _global_registry


def register_default_providers() -> None:
    """
    Register default providers.

    Registers Claude, OpenAI, and Gemini providers if their
    API keys are available in the environment.

    This function is safe to call multiple times (idempotent).
    If a provider is already registered, it will be skipped.

    Example:
        >>> register_default_providers()
        >>> registry = get_provider_registry()
        >>> if registry.has_provider("claude"):
        ...     print("Claude provider available")

    Note:
        This function requires the provider implementations to be
        available. If implementations haven't been created yet,
        this will do nothing.
    """
    import os
    from importlib import import_module

    registry = get_provider_registry()

    # Try to register Claude provider
    try:
        if not registry.has_provider("claude"):
            # Import will be available once we implement ClaudeCodeProvider
            from adws.providers.implementations.claude import ClaudeCodeProvider
            config = ProviderConfig(
                name="claude",
                enabled=True,
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout_seconds=120.0,
                max_retries=3,
            )
            provider = ClaudeCodeProvider(config)
            registry.register("claude", provider, config)
    except (ImportError, Exception):
        # Provider implementation not available yet, or initialization failed
        pass

    # Try to register OpenAI provider
    try:
        if not registry.has_provider("openai") and os.getenv("OPENAI_API_KEY"):
            from adws.providers.implementations.openai import OpenAIProvider
            config = ProviderConfig(
                name="openai",
                enabled=True,
                api_key=os.getenv("OPENAI_API_KEY"),
                timeout_seconds=120.0,
                max_retries=3,
            )
            provider = OpenAIProvider(config)
            registry.register("openai", provider, config)
    except (ImportError, Exception):
        pass

    # Try to register Gemini provider
    try:
        if not registry.has_provider("gemini") and os.getenv("GOOGLE_API_KEY"):
            from adws.providers.implementations.gemini import GeminiProvider
            config = ProviderConfig(
                name="gemini",
                enabled=True,
                api_key=os.getenv("GOOGLE_API_KEY"),
                timeout_seconds=120.0,
                max_retries=3,
            )
            provider = GeminiProvider(config)
            registry.register("gemini", provider, config)
    except (ImportError, Exception):
        pass
