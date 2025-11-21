"""
Routing Engine for Provider Selection

Implements intelligent routing strategies to select the optimal LLM provider
for each request based on configurable rules and strategies.
"""

import asyncio
import os
import threading
import yaml
from pathlib import Path
from typing import List, Optional, Any, Dict, Set
from enum import Enum
from pydantic import BaseModel, Field

from adws.providers.interfaces import PromptRequest
from adws.providers.registry import ProviderRegistry


class RoutingConfig(BaseModel):
    """
    Configuration for routing heuristics.

    Allows customization of cost/quality/latency ordering preferences
    without code changes. Can be loaded from YAML config or environment
    variables.

    Attributes:
        cost_order: Provider preference for cost optimization (cheapest first)
        quality_order: Provider preference for quality optimization (best first)
        latency_order: Provider preference for latency optimization (fastest first)
        enable_capability_cache: Whether to cache capability checks (default: True)

    Example:
        >>> config = RoutingConfig(
        ...     cost_order=["gemini", "openai", "claude"],
        ...     quality_order=["claude", "openai", "gemini"]
        ... )
    """
    cost_order: List[str] = Field(
        default_factory=lambda: ["gemini", "openai", "claude"],
        description="Provider preference for cost optimization"
    )
    quality_order: List[str] = Field(
        default_factory=lambda: ["claude", "openai", "gemini"],
        description="Provider preference for quality optimization"
    )
    latency_order: List[str] = Field(
        default_factory=list,
        description="Provider preference for latency optimization (empty = use metrics)"
    )
    enable_capability_cache: bool = Field(
        default=True,
        description="Whether to cache capability checks"
    )

    @classmethod
    def from_yaml(cls, path: Path) -> "RoutingConfig":
        """
        Load configuration from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            RoutingConfig instance

        Example:
            >>> config = RoutingConfig.from_yaml(Path("config/routing.yml"))
        """
        if not path.exists():
            return cls()

        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}

        return cls(**data.get('routing', {}))

    @classmethod
    def from_env(cls) -> "RoutingConfig":
        """
        Load configuration from environment variables.

        Environment variables:
            ADWS_ROUTING_COST_ORDER: Comma-separated provider order for cost
            ADWS_ROUTING_QUALITY_ORDER: Comma-separated provider order for quality
            ADWS_ROUTING_LATENCY_ORDER: Comma-separated provider order for latency
            ADWS_ROUTING_ENABLE_CAPABILITY_CACHE: "true" or "false"

        Returns:
            RoutingConfig instance

        Example:
            >>> os.environ["ADWS_ROUTING_COST_ORDER"] = "gemini,openai,claude"
            >>> config = RoutingConfig.from_env()
        """
        kwargs = {}

        if cost_order := os.getenv("ADWS_ROUTING_COST_ORDER"):
            kwargs["cost_order"] = [p.strip() for p in cost_order.split(",")]

        if quality_order := os.getenv("ADWS_ROUTING_QUALITY_ORDER"):
            kwargs["quality_order"] = [p.strip() for p in quality_order.split(",")]

        if latency_order := os.getenv("ADWS_ROUTING_LATENCY_ORDER"):
            kwargs["latency_order"] = [p.strip() for p in latency_order.split(",")]

        if cache_str := os.getenv("ADWS_ROUTING_ENABLE_CAPABILITY_CACHE"):
            kwargs["enable_capability_cache"] = cache_str.lower() in ("true", "1", "yes")

        return cls(**kwargs) if kwargs else cls()


class RoutingStrategy(str, Enum):
    """
    Available routing strategies.

    Strategies:
        COST_OPTIMIZED: Prefer providers with lowest cost
        QUALITY_OPTIMIZED: Prefer providers with highest quality (default)
        LATENCY_OPTIMIZED: Prefer providers with lowest latency
        CAPABILITY_BASED: Route based on model capabilities
        ROUND_ROBIN: Distribute load evenly across providers
        CUSTOM: Use custom rule-based routing
    """
    COST_OPTIMIZED = "cost-optimized"
    QUALITY_OPTIMIZED = "quality-optimized"
    LATENCY_OPTIMIZED = "latency-optimized"
    CAPABILITY_BASED = "capability-based"
    ROUND_ROBIN = "round-robin"
    CUSTOM = "custom"


class RoutingCondition(BaseModel):
    """
    Condition for rule-based routing.

    Attributes:
        field: Field to evaluate (model, capability, cost, latency, custom)
        operator: Comparison operator (equals, contains, lt, gt, lte, gte)
        value: Value to compare against

    Example:
        >>> condition = RoutingCondition(
        ...     field="model",
        ...     operator="contains",
        ...     value="gpt"
        ... )
    """
    field: str = Field(
        ...,
        description="Field to evaluate",
        pattern="^(model|capability|cost|latency|custom)$"
    )
    operator: str = Field(
        ...,
        description="Comparison operator",
        pattern="^(equals|contains|lt|gt|lte|gte)$"
    )
    value: Any = Field(..., description="Value to compare against")


class RoutingRule(BaseModel):
    """
    Rule for provider routing.

    Rules are evaluated in priority order (higher priority first).
    First matching rule determines the provider selection.

    Attributes:
        id: Unique rule identifier
        name: Human-readable rule name
        priority: Rule priority (higher = evaluated first)
        conditions: List of conditions (all must match)
        target_provider: Provider to select when rule matches
        fallback_providers: Ordered list of fallback providers

    Example:
        >>> rule = RoutingRule(
        ...     id="gpt4-to-openai",
        ...     name="Route GPT-4 to OpenAI",
        ...     priority=100,
        ...     conditions=[
        ...         RoutingCondition(field="model", operator="equals", value="gpt-4")
        ...     ],
        ...     target_provider="openai",
        ...     fallback_providers=["claude", "gemini"]
        ... )
    """
    id: str = Field(..., description="Unique rule identifier", min_length=1)
    name: str = Field(..., description="Human-readable name", min_length=1)
    priority: int = Field(..., description="Priority (higher = first)", ge=0)
    conditions: List[RoutingCondition] = Field(
        ...,
        description="Conditions (all must match)",
        min_length=1
    )
    target_provider: str = Field(..., description="Target provider", min_length=1)
    fallback_providers: List[str] = Field(
        default_factory=list,
        description="Fallback providers in order"
    )


class RoutingDecision(BaseModel):
    """
    Result of routing decision.

    Contains the selected provider and metadata about why it was chosen.

    Attributes:
        provider_id: Selected provider identifier
        reason: Human-readable explanation for selection
        fallback_providers: Ordered list of fallback providers
        estimated_cost: Estimated cost in USD (if available)
        estimated_latency: Estimated latency in seconds (if available)
        strategy_used: Strategy that made this decision
        matched_rule_id: Rule ID that matched (if rule-based)

    Example:
        >>> decision = RoutingDecision(
        ...     provider_id="claude",
        ...     reason="Quality-optimized routing (default provider)",
        ...     fallback_providers=["openai", "gemini"],
        ...     strategy_used=RoutingStrategy.QUALITY_OPTIMIZED
        ... )
    """
    provider_id: str = Field(..., description="Selected provider", min_length=1)
    reason: str = Field(..., description="Selection reason", min_length=1)
    fallback_providers: List[str] = Field(
        default_factory=list,
        description="Fallback providers"
    )
    estimated_cost: Optional[float] = Field(None, description="Estimated cost USD", ge=0)
    estimated_latency: Optional[float] = Field(None, description="Estimated latency sec", ge=0)
    strategy_used: RoutingStrategy = Field(..., description="Strategy used")
    matched_rule_id: Optional[str] = Field(None, description="Matched rule ID")


class RoutingEngine:
    """
    Intelligent routing engine for provider selection.

    Routes requests to optimal providers based on configurable rules
    and strategies. Supports multiple routing strategies including
    cost optimization, quality optimization, latency optimization,
    and custom rule-based routing.

    Thread-safety: All operations are protected by a re-entrant lock so the
    engine can be safely shared across threads.

    Example:
        >>> from adws.providers.registry import get_provider_registry
        >>> registry = get_provider_registry()
        >>> engine = RoutingEngine(registry)
        >>>
        >>> # Add custom rule
        >>> rule = RoutingRule(
        ...     id="gpt4-rule",
        ...     name="Route GPT-4 to OpenAI",
        ...     priority=100,
        ...     conditions=[RoutingCondition(
        ...         field="model",
        ...         operator="contains",
        ...         value="gpt"
        ...     )],
        ...     target_provider="openai"
        ... )
        >>> engine.add_rule(rule)
        >>>
        >>> # Route request
        >>> request = PromptRequest(
        ...     prompt="Test",
        ...     model="gpt-4",
        ...     adw_id="test",
        ...     slash_command="/test",
        ...     working_dir="/tmp"
        ... )
        >>> decision = engine.route(request)
        >>> print(f"Selected: {decision.provider_id}")
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        config: Optional[RoutingConfig] = None
    ):
        """
        Initialize routing engine.

        Args:
            registry: Provider registry for provider lookup
            config: Optional routing configuration (defaults to RoutingConfig())

        Example:
            >>> registry = get_provider_registry()
            >>> config = RoutingConfig.from_yaml(Path("config/routing.yml"))
            >>> engine = RoutingEngine(registry, config)
        """
        self._registry = registry
        self._config = config or RoutingConfig()
        self._rules: List[RoutingRule] = []
        self._round_robin_index = 0
        self._lock = threading.RLock()
        self._capability_cache: Dict[tuple, bool] = {}

    def add_rule(self, rule: RoutingRule) -> None:
        """
        Add routing rule.

        Rules are automatically sorted by priority (highest first).
        Thread-safe operation.

        Args:
            rule: Routing rule to add

        Example:
            >>> rule = RoutingRule(
            ...     id="test",
            ...     name="Test Rule",
            ...     priority=50,
            ...     conditions=[RoutingCondition(
            ...         field="model",
            ...         operator="equals",
            ...         value="test-model"
            ...     )],
            ...     target_provider="test-provider"
            ... )
            >>> engine.add_rule(rule)
        """
        with self._lock:
            self._rules.append(rule)
            # Sort by priority (highest first)
            self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove routing rule by ID.

        Thread-safe operation.

        Args:
            rule_id: Rule identifier to remove

        Returns:
            True if rule was removed, False if not found

        Example:
            >>> engine.remove_rule("test-rule")
            True
        """
        with self._lock:
            initial_length = len(self._rules)
            self._rules = [r for r in self._rules if r.id != rule_id]
            return len(self._rules) < initial_length

    def get_rules(self) -> List[RoutingRule]:
        """
        Get all routing rules.

        Thread-safe operation returns a copy of the rules.

        Returns:
            List of routing rules sorted by priority

        Example:
            >>> rules = engine.get_rules()
            >>> for rule in rules:
            ...     print(f"{rule.name}: priority={rule.priority}")
        """
        with self._lock:
            return self._rules.copy()

    def update_config(self, config: RoutingConfig) -> None:
        """
        Update routing configuration at runtime.

        Thread-safe operation that updates heuristics without redeploying.

        Args:
            config: New routing configuration

        Example:
            >>> new_config = RoutingConfig(
            ...     cost_order=["openai", "gemini", "claude"]
            ... )
            >>> engine.update_config(new_config)
        """
        with self._lock:
            self._config = config
            # Clear capability cache when config changes
            self._capability_cache.clear()

    def get_config(self) -> RoutingConfig:
        """
        Get current routing configuration.

        Returns:
            Current routing configuration

        Example:
            >>> config = engine.get_config()
            >>> print(config.cost_order)
        """
        with self._lock:
            return self._config.model_copy()

    def route(
        self,
        request: PromptRequest,
        strategy: RoutingStrategy = RoutingStrategy.QUALITY_OPTIMIZED
    ) -> RoutingDecision:
        """
        Route request to optimal provider.

        First tries rule-based routing (if any rules are configured).
        Falls back to strategy-based routing if no rules match.

        Args:
            request: Prompt request to route
            strategy: Routing strategy to use (default: QUALITY_OPTIMIZED)

        Returns:
            Routing decision with selected provider and metadata

        Raises:
            ValueError: If no providers are available

        Example:
            >>> decision = engine.route(request, RoutingStrategy.COST_OPTIMIZED)
            >>> print(f"Provider: {decision.provider_id}")
            >>> print(f"Reason: {decision.reason}")
        """
        with self._lock:
            rules_snapshot = self._rules.copy()

        # Try rule-based routing first
        for rule in rules_snapshot:
            if self._matches_rule(request, rule):
                return RoutingDecision(
                    provider_id=rule.target_provider,
                    reason=f"Matched rule: {rule.name}",
                    fallback_providers=rule.fallback_providers,
                    strategy_used=RoutingStrategy.CUSTOM,
                    matched_rule_id=rule.id
                )

        # Fall back to strategy-based routing
        return self._route_by_strategy(request, strategy)

    async def route_async(
        self,
        request: PromptRequest,
        strategy: RoutingStrategy = RoutingStrategy.QUALITY_OPTIMIZED
    ) -> RoutingDecision:
        """
        Route request to optimal provider asynchronously.

        This async version allows for non-blocking routing when fetching
        provider metrics or performing other async operations. Currently
        delegates to synchronous route() in a thread pool, but can be
        extended for true async metric fetching.

        Args:
            request: Prompt request to route
            strategy: Routing strategy to use (default: QUALITY_OPTIMIZED)

        Returns:
            Routing decision with selected provider and metadata

        Raises:
            ValueError: If no providers are available

        Example:
            >>> decision = await engine.route_async(request, RoutingStrategy.COST_OPTIMIZED)
            >>> print(f"Provider: {decision.provider_id}")
        """
        # For now, offload synchronous route to thread pool
        # Future enhancement: add async metric fetching
        return await asyncio.to_thread(self.route, request, strategy)

    def _matches_rule(self, request: PromptRequest, rule: RoutingRule) -> bool:
        """Check if request matches all rule conditions."""
        return all(
            self._matches_condition(request, condition, rule.target_provider)
            for condition in rule.conditions
        )

    def _check_provider_capability(self, provider_id: str, capability: str) -> bool:
        """
        Check if a provider supports a capability with optional caching.

        Args:
            provider_id: Provider identifier
            capability: Capability name to check

        Returns:
            True if provider supports capability, False otherwise
        """
        cache_key = (provider_id, capability)

        # Optimistic cache read (no lock for read)
        if self._config.enable_capability_cache:
            cached = self._capability_cache.get(cache_key)
            if cached is not None:
                return cached

        # Get provider and check capability
        provider = self._registry.get(provider_id)
        if not provider:
            result = False
        elif hasattr(provider, "supports_capability"):
            result = provider.supports_capability(capability)
        else:
            # No valid way to check capability; return False
            result = False

        # Cache result if enabled
        if self._config.enable_capability_cache:
            with self._lock:
                self._capability_cache[cache_key] = result

        return result

    def _get_request_capabilities(self, request: PromptRequest) -> Set[str]:
        """
        Extract normalized capability requirements from request metadata.

        Supports either a list or comma-separated string stored under
        'capabilities' or 'required_capabilities'.
        """
        metadata = getattr(request, "metadata", {}) or {}

        capabilities = metadata.get("capabilities")
        if capabilities is None:
            capabilities = metadata.get("required_capabilities")

        if capabilities is None:
            return set()

        if isinstance(capabilities, str):
            raw_values = [capabilities]
        elif isinstance(capabilities, (list, tuple, set)):
            raw_values = list(capabilities)
        else:
            return set()

        normalized = {
            str(capability).strip()
            for capability in raw_values
            if str(capability).strip()
        }
        return normalized

    def _matches_condition(
        self,
        request: PromptRequest,
        condition: RoutingCondition,
        target_provider: Optional[str] = None
    ) -> bool:
        """
        Check if request matches a single condition.

        Args:
            request: Prompt request to evaluate
            condition: Condition to check
            target_provider: Optional target provider for capability checks

        Returns:
            True if condition matches, False otherwise
        """
        # Get field value
        field_value: Any = None

        if condition.field == "model":
            field_value = request.model
        elif condition.field == "capability":
            capability_value = str(condition.value)
            requested_capabilities = self._get_request_capabilities(request)

            # If the request declares capabilities, ensure this condition is requested
            if requested_capabilities and capability_value not in requested_capabilities:
                return False

            # Check that the target provider supports the capability
            if target_provider:
                return self._check_provider_capability(target_provider, capability_value)
            else:
                return False
        elif condition.field in ["cost", "latency"]:
            # These would need to be in request metadata
            field_value = request.metadata.get(condition.field)
        elif condition.field == "custom":
            # Custom field from metadata
            # For custom fields, condition.value is the metadata key name
            field_value = request.metadata.get(str(condition.value))

        if field_value is None:
            return False

        # Apply operator
        if condition.operator == "equals":
            # For custom fields, "equals" checks if the key exists and is truthy
            if condition.field == "custom":
                return bool(field_value)
            return field_value == condition.value
        elif condition.operator == "contains":
            return str(condition.value) in str(field_value)
        elif condition.operator == "lt":
            return float(field_value) < float(condition.value)
        elif condition.operator == "gt":
            return float(field_value) > float(condition.value)
        elif condition.operator == "lte":
            return float(field_value) <= float(condition.value)
        elif condition.operator == "gte":
            return float(field_value) >= float(condition.value)

        return False

    def _route_by_strategy(
        self,
        request: PromptRequest,
        strategy: RoutingStrategy
    ) -> RoutingDecision:
        """Route using specified strategy."""
        providers = self._registry.list_providers()

        if not providers:
            raise ValueError("No providers available for routing")

        if strategy == RoutingStrategy.COST_OPTIMIZED:
            return self._route_by_cost(providers)
        elif strategy == RoutingStrategy.LATENCY_OPTIMIZED:
            return self._route_by_latency(providers, request)
        elif strategy == RoutingStrategy.ROUND_ROBIN:
            return self._route_round_robin(providers)
        elif strategy == RoutingStrategy.CAPABILITY_BASED:
            return self._route_by_capability(providers, request)
        else:  # QUALITY_OPTIMIZED (default)
            return self._route_by_quality(providers)

    def _route_by_cost(self, providers: List[str]) -> RoutingDecision:
        """
        Route by cost optimization.

        Uses configurable cost ordering preferences (default: gemini > openai > claude).
        Configuration can be updated via RoutingConfig.
        """
        with self._lock:
            cost_order = self._config.cost_order

        # Sort providers by cost preference
        def cost_rank(provider: str) -> int:
            try:
                return cost_order.index(provider)
            except ValueError:
                return 999  # Unknown providers go last

        sorted_providers = sorted(providers, key=cost_rank)

        return RoutingDecision(
            provider_id=sorted_providers[0],
            reason="Cost-optimized routing (prefer cheaper providers)",
            fallback_providers=sorted_providers[1:],
            strategy_used=RoutingStrategy.COST_OPTIMIZED
        )

    def _route_by_quality(self, providers: List[str]) -> RoutingDecision:
        """
        Route by quality optimization.

        Uses configurable quality ordering preferences (default: claude > openai > gemini).
        Configuration can be updated via RoutingConfig.
        """
        with self._lock:
            quality_order = self._config.quality_order

        # Sort providers by quality preference
        def quality_rank(provider: str) -> int:
            try:
                return quality_order.index(provider)
            except ValueError:
                return 999  # Unknown providers go last

        sorted_providers = sorted(providers, key=quality_rank)

        return RoutingDecision(
            provider_id=sorted_providers[0],
            reason="Quality-optimized routing (prefer higher quality)",
            fallback_providers=sorted_providers[1:],
            strategy_used=RoutingStrategy.QUALITY_OPTIMIZED
        )

    def _route_by_latency(
        self,
        providers: List[str],
        request: PromptRequest
    ) -> RoutingDecision:
        """
        Route by latency optimization.

        Uses provider historical performance metrics if available.
        Falls back to quality routing if no metrics exist.
        """
        with self._lock:
            latency_order = list(self._config.latency_order)

        if latency_order:
            def latency_rank(provider: str) -> int:
                try:
                    return latency_order.index(provider)
                except ValueError:
                    return len(latency_order)

            sorted_providers = sorted(providers, key=latency_rank)

            return RoutingDecision(
                provider_id=sorted_providers[0],
                reason="Latency-optimized routing (configured order)",
                fallback_providers=sorted_providers[1:],
                strategy_used=RoutingStrategy.LATENCY_OPTIMIZED
            )

        # Collect latency data for each provider
        provider_latencies: List[tuple[str, float]] = []

        for provider_id in providers:
            provider = self._registry.get(provider_id)
            if provider and hasattr(provider, "average_latency"):
                latency = provider.average_latency
                provider_latencies.append((provider_id, latency))
            else:
                # No latency data, assign high value
                provider_latencies.append((provider_id, float('inf')))

        # Sort by latency (lowest first)
        provider_latencies.sort(key=lambda x: x[1])

        selected_id = provider_latencies[0][0]
        selected_latency = provider_latencies[0][1]

        # If no real latency data, fall back to quality
        if selected_latency == float('inf'):
            return self._route_by_quality(providers)

        return RoutingDecision(
            provider_id=selected_id,
            reason=f"Latency-optimized routing (avg: {selected_latency:.2f}s)",
            fallback_providers=[p[0] for p in provider_latencies[1:]],
            estimated_latency=selected_latency,
            strategy_used=RoutingStrategy.LATENCY_OPTIMIZED
        )

    def _route_round_robin(self, providers: List[str]) -> RoutingDecision:
        """
        Route using round-robin load balancing.

        Distributes requests evenly across all providers.
        Thread-safe operation.
        """
        with self._lock:
            index = self._round_robin_index % len(providers)
            self._round_robin_index += 1

        selected = providers[index]
        fallbacks = providers[index + 1:] + providers[:index]

        return RoutingDecision(
            provider_id=selected,
            reason=f"Round-robin routing (index: {index})",
            fallback_providers=fallbacks,
            strategy_used=RoutingStrategy.ROUND_ROBIN
        )

    def _route_by_capability(
        self,
        providers: List[str],
        request: PromptRequest
    ) -> RoutingDecision:
        """
        Route by capability matching.

        Finds providers that support the requested model.
        Falls back to quality routing if model not found.
        """
        # Try to find provider that supports the requested model
        for provider_id in providers:
            provider = self._registry.get(provider_id)
            if provider and provider.supports_model(request.model):
                # Build fallback list of other providers that support the model
                other_providers = [
                    p for p in providers
                    if p != provider_id and
                    self._registry.get(p) and
                    self._registry.get(p).supports_model(request.model)
                ]

                return RoutingDecision(
                    provider_id=provider_id,
                    reason=f"Capability-based routing (supports {request.model})",
                    fallback_providers=other_providers,
                    strategy_used=RoutingStrategy.CAPABILITY_BASED
                )

        # No provider found for model, fall back to quality routing
        return self._route_by_quality(providers)
