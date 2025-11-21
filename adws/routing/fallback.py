"""
Fallback Handler for Provider Resilience

Implements fallback chains and retry logic with exponential backoff
to ensure resilient multi-provider execution.
"""

import asyncio
import time
from datetime import datetime, UTC
from typing import List, Optional
from pydantic import BaseModel, Field

from adws.providers.interfaces import PromptRequest, PromptResponse, LLMProvider, RetryCode
from adws.providers.registry import ProviderRegistry


class FallbackConfig(BaseModel):
    """
    Configuration for fallback handling.

    Attributes:
        max_retries: Maximum retry attempts per provider
        retry_delay: Initial retry delay in seconds
        exponential_backoff: Whether to use exponential backoff
        backoff_multiplier: Multiplier for exponential backoff (default: 2)
        max_retry_delay: Maximum retry delay in seconds (default: 60)
        retry_on_codes: Retry codes that trigger retry (default: rate limit, timeout)

    Example:
        >>> config = FallbackConfig(
        ...     max_retries=3,
        ...     retry_delay=1.0,
        ...     exponential_backoff=True
        ... )
    """
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts",
        ge=1,
        le=10
    )
    retry_delay: float = Field(
        default=1.0,
        description="Initial retry delay seconds",
        ge=0.1,
        le=10.0
    )
    exponential_backoff: bool = Field(
        default=True,
        description="Use exponential backoff"
    )
    backoff_multiplier: float = Field(
        default=2.0,
        description="Backoff multiplier",
        ge=1.0,
        le=5.0
    )
    max_retry_delay: float = Field(
        default=60.0,
        description="Max retry delay seconds",
        ge=1.0,
        le=300.0
    )
    retry_on_codes: List[RetryCode] = Field(
        default_factory=lambda: [
            RetryCode.RATE_LIMIT_ERROR,
            RetryCode.TIMEOUT_ERROR,
            RetryCode.EXECUTION_ERROR
        ],
        description="Retry codes that trigger retry"
    )


class FallbackResult(BaseModel):
    """
    Result of fallback execution.

    Attributes:
        response: Final successful response
        provider_id: Provider that succeeded
        attempt_number: Total attempts made
        failed_providers: List of providers that failed
        total_retries: Total retry attempts across all providers
        total_duration: Total execution time in seconds

    Example:
        >>> result = FallbackResult(
        ...     response=response,
        ...     provider_id="claude",
        ...     attempt_number=2,
        ...     failed_providers=["openai"],
        ...     total_retries=3,
        ...     total_duration=5.2
        ... )
    """
    response: PromptResponse = Field(..., description="Successful response")
    provider_id: str = Field(..., description="Successful provider", min_length=1)
    attempt_number: int = Field(..., description="Total attempts", ge=1)
    failed_providers: List[str] = Field(
        default_factory=list,
        description="Failed providers"
    )
    total_retries: int = Field(default=0, description="Total retries", ge=0)
    total_duration: float = Field(..., description="Total duration seconds", ge=0)


class FallbackHandler:
    """
    Fallback handler for resilient provider execution.

    Implements fallback chains with retry logic and exponential backoff.
    Automatically tries backup providers when primary provider fails.

    Example:
        >>> from adws.providers.registry import get_provider_registry
        >>> registry = get_provider_registry()
        >>> handler = FallbackHandler(registry)
        >>>
        >>> config = FallbackConfig(max_retries=3, exponential_backoff=True)
        >>> provider_chain = ["claude", "openai", "gemini"]
        >>>
        >>> result = await handler.execute_with_fallback_async(
        ...     request=request,
        ...     provider_chain=provider_chain,
        ...     config=config
        ... )
        >>> print(f"Success with: {result.provider_id}")
    """

    def __init__(self, registry: ProviderRegistry):
        """
        Initialize fallback handler.

        Args:
            registry: Provider registry for provider lookup
        """
        self._registry = registry

    def execute_with_fallback(
        self,
        request: PromptRequest,
        provider_chain: List[str],
        config: FallbackConfig
    ) -> FallbackResult:
        """
        Execute request with fallback chain (synchronous).

        Tries each provider in the chain until one succeeds.
        Each provider is retried according to the config before
        moving to the next provider in the chain.

        Args:
            request: Prompt request to execute
            provider_chain: Ordered list of providers to try
            config: Fallback configuration

        Returns:
            Fallback result with successful response

        Raises:
            RuntimeError: If all providers in chain fail

        Example:
            >>> result = handler.execute_with_fallback(
            ...     request=request,
            ...     provider_chain=["claude", "openai"],
            ...     config=config
            ... )
        """
        if not provider_chain:
            raise ValueError("Provider chain cannot be empty")

        start_time = time.time()
        failed_providers: List[str] = []
        total_retries = 0
        attempt_number = 0

        for provider_id in provider_chain:
            attempt_number += 1

            # Get provider
            provider = self._registry.get(provider_id)
            if not provider:
                failed_providers.append(provider_id)
                continue

            # Try with retries
            response, retries = self._execute_with_retry(
                provider=provider,
                request=request,
                config=config
            )

            total_retries += retries

            if response.success:
                total_duration = time.time() - start_time
                return FallbackResult(
                    response=response,
                    provider_id=provider_id,
                    attempt_number=attempt_number,
                    failed_providers=failed_providers,
                    total_retries=total_retries,
                    total_duration=total_duration
                )

            # Provider failed even after retries
            failed_providers.append(provider_id)

        # All providers failed
        total_duration = time.time() - start_time
        raise RuntimeError(
            f"All providers in fallback chain failed: {', '.join(failed_providers)}. "
            f"Total attempts: {attempt_number}, Total retries: {total_retries}, "
            f"Duration: {total_duration:.2f}s"
        )

    async def execute_with_fallback_async(
        self,
        request: PromptRequest,
        provider_chain: List[str],
        config: FallbackConfig
    ) -> FallbackResult:
        """
        Execute request with fallback chain (asynchronous).

        Async version of execute_with_fallback.

        Args:
            request: Prompt request to execute
            provider_chain: Ordered list of providers to try
            config: Fallback configuration

        Returns:
            Fallback result with successful response

        Raises:
            RuntimeError: If all providers in chain fail

        Example:
            >>> result = await handler.execute_with_fallback_async(
            ...     request=request,
            ...     provider_chain=["claude", "openai"],
            ...     config=config
            ... )
        """
        if not provider_chain:
            raise ValueError("Provider chain cannot be empty")

        start_time = time.time()
        failed_providers: List[str] = []
        total_retries = 0
        attempt_number = 0

        for provider_id in provider_chain:
            attempt_number += 1

            # Get provider
            provider = self._registry.get(provider_id)
            if not provider:
                failed_providers.append(provider_id)
                continue

            # Try with retries
            response, retries = await self._execute_with_retry_async(
                provider=provider,
                request=request,
                config=config
            )

            total_retries += retries

            if response.success:
                total_duration = time.time() - start_time
                return FallbackResult(
                    response=response,
                    provider_id=provider_id,
                    attempt_number=attempt_number,
                    failed_providers=failed_providers,
                    total_retries=total_retries,
                    total_duration=total_duration
                )

            # Provider failed even after retries
            failed_providers.append(provider_id)

        # All providers failed
        total_duration = time.time() - start_time
        raise RuntimeError(
            f"All providers in fallback chain failed: {', '.join(failed_providers)}. "
            f"Total attempts: {attempt_number}, Total retries: {total_retries}, "
            f"Duration: {total_duration:.2f}s"
        )

    def _execute_with_retry(
        self,
        provider: LLMProvider,
        request: PromptRequest,
        config: FallbackConfig
    ) -> tuple[PromptResponse, int]:
        """
        Execute request with retry logic (synchronous).

        Returns:
            Tuple of (response, retry_count)
        """
        retry_count = 0
        last_response: Optional[PromptResponse] = None

        for attempt in range(config.max_retries):
            try:
                response = provider.execute(request)

                # Check if retry is needed
                if response.success:
                    return response, retry_count

                # Check if this error should trigger retry
                if response.retry_code not in config.retry_on_codes:
                    # Don't retry this error type
                    return response, retry_count

                last_response = response

                # If not last attempt, sleep before retry
                if attempt < config.max_retries - 1:
                    delay = self._calculate_delay(attempt, config)
                    time.sleep(delay)
                    retry_count += 1

            except Exception as e:
                # Unexpected error - don't retry
                if last_response:
                    return last_response, retry_count

                # Create error response
                return PromptResponse(
                    output="",
                    success=False,
                    provider=provider.name,
                    model=request.model,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    cost_usd=0.0,
                    duration_seconds=0.0,
                    timestamp=datetime.now(UTC),
                    retry_code=RetryCode.EXECUTION_ERROR,
                    error_message=str(e)
                ), retry_count

        # Max retries exhausted
        return last_response or self._create_error_response(
            provider, request, "Max retries exhausted"
        ), retry_count

    async def _execute_with_retry_async(
        self,
        provider: LLMProvider,
        request: PromptRequest,
        config: FallbackConfig
    ) -> tuple[PromptResponse, int]:
        """
        Execute request with retry logic (asynchronous).

        Returns:
            Tuple of (response, retry_count)
        """
        retry_count = 0
        last_response: Optional[PromptResponse] = None

        for attempt in range(config.max_retries):
            try:
                response = await provider.execute_async(request)

                # Check if retry is needed
                if response.success:
                    return response, retry_count

                # Check if this error should trigger retry
                if response.retry_code not in config.retry_on_codes:
                    # Don't retry this error type
                    return response, retry_count

                last_response = response

                # If not last attempt, sleep before retry
                if attempt < config.max_retries - 1:
                    delay = self._calculate_delay(attempt, config)
                    await asyncio.sleep(delay)
                    retry_count += 1

            except Exception as e:
                # Unexpected error - don't retry
                if last_response:
                    return last_response, retry_count

                # Create error response
                return self._create_error_response(
                    provider, request, str(e)
                ), retry_count

        # Max retries exhausted
        return last_response or self._create_error_response(
            provider, request, "Max retries exhausted"
        ), retry_count

    def _calculate_delay(self, attempt: int, config: FallbackConfig) -> float:
        """Calculate retry delay with optional exponential backoff."""
        if config.exponential_backoff:
            delay = config.retry_delay * (config.backoff_multiplier ** attempt)
            return min(delay, config.max_retry_delay)
        else:
            return config.retry_delay

    def _create_error_response(
        self,
        provider: LLMProvider,
        request: PromptRequest,
        error_message: str
    ) -> PromptResponse:
        """Create error response."""
        return PromptResponse(
            output="",
            success=False,
            provider=provider.name,
            model=request.model,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            duration_seconds=0.0,
            timestamp=datetime.now(UTC),
            retry_code=RetryCode.EXECUTION_ERROR,
            error_message=error_message
        )
