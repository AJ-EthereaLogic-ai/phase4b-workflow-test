"""
Base Provider Implementation

Abstract base class providing common functionality for all LLM providers.
"""

import asyncio
import time
import threading
from abc import ABC, abstractmethod
from typing import Iterable, AsyncIterator, List
from adws.providers.interfaces import (
    PromptRequest,
    PromptResponse,
    RetryCode,
    ProviderConfig,
    ProviderMetrics,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderAuthenticationError,
    ProviderModelNotAvailableError,
    ProviderContextLengthError,
    ProviderContentFilterError,
)


class BaseProvider(ABC):
    """
    Abstract base provider providing common functionality.

    Subclasses must implement:
    - name property
    - _execute_impl()
    - supports_model()
    - max_context_length()
    - cost_per_1k_tokens()
    - estimate_tokens()

    Example:
        >>> class MyProvider(BaseProvider):
        ...     @property
        ...     def name(self) -> str:
        ...         return "myprovider"
        ...
        ...     def _execute_impl(self, request: PromptRequest) -> PromptResponse:
        ...         # Implementation
        ...         raise NotImplementedError
        ...     # ... implement other abstract methods
    """

    def __init__(self, config: ProviderConfig):
        """
        Initialize base provider.

        Args:
            config: Provider configuration
        """
        self.config = config
        self._call_count = 0
        self._total_cost = 0.0
        self._total_tokens = 0
        self._metrics_lock = threading.Lock()

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'claude', 'openai', 'gemini')"""
        raise NotImplementedError

    def execute(self, request: PromptRequest) -> PromptResponse:
        """
        Execute prompt synchronously.

        This method handles validation, delegates to _execute_impl,
        and accumulates provider metrics.

        Args:
            request: Standardized prompt request

        Returns:
            Standardized response

        Raises:
            ValueError: If request is invalid
        """
        start_time = time.time()

        try:
            self._validate_request(request)
            response = self._execute_impl(request)
            self._record_metrics(response)
            return response
        except Exception as exc:
            duration = time.time() - start_time
            return PromptResponse(
                output="",
                success=False,
                provider=self.name,
                model=request.model,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
                duration_seconds=duration,
                retry_code=self._categorize_error(exc),
                error_message=str(exc),
            )

    async def execute_async(self, request: PromptRequest) -> PromptResponse:
        """
        Execute prompt asynchronously.

        The default implementation offloads the synchronous execute
        call to a background thread. Providers can override this for
        native async implementations.

        Args:
            request: Standardized prompt request

        Returns:
            Standardized response
        """
        return await asyncio.to_thread(self.execute, request)

    def stream(self, request: PromptRequest) -> Iterable[str]:
        """
        Stream prompt output synchronously.

        Providers that support streaming can override this method.
        The default implementation executes the full request and
        yields the final output as a single chunk.

        Args:
            request: Standardized prompt request

        Yields:
            Incremental text chunks
        """
        response = self.execute(request)
        if response.output:
            yield response.output

    async def stream_async(self, request: PromptRequest) -> AsyncIterator[str]:
        """
        Stream prompt output asynchronously.

        The default implementation yields chunks incrementally by
        wrapping the synchronous stream() in an async generator that
        pulls chunks lazily from a thread-safe queue.

        Args:
            request: Standardized prompt request

        Yields:
            Incremental text chunks as they become available
        """
        import queue

        # Use a queue to pass chunks from the sync stream to async iterator
        chunk_queue: queue.Queue[str | None] = queue.Queue()

        def _stream_to_queue():
            """Helper to run sync stream in thread and populate queue."""
            try:
                for chunk in self.stream(request):
                    chunk_queue.put(chunk)
            finally:
                # Signal completion
                chunk_queue.put(None)

        # Start streaming in background thread
        stream_task = asyncio.create_task(
            asyncio.to_thread(_stream_to_queue)
        )

        try:
            # Yield chunks as they arrive
            while True:
                # Poll queue without blocking event loop
                chunk = await asyncio.to_thread(chunk_queue.get)
                if chunk is None:
                    break
                yield chunk
        finally:
            # Ensure thread completes
            await stream_task

    @abstractmethod
    def _execute_impl(self, request: PromptRequest) -> PromptResponse:
        """
        Provider-specific execution implementation.

        Args:
            request: Standardized prompt request

        Returns:
            Standardized response

        Raises:
            Exception: On execution failure
        """
        raise NotImplementedError

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """
        Check if provider supports model.

        Args:
            model: Model identifier

        Returns:
            True if supported
        """
        raise NotImplementedError

    @abstractmethod
    def max_context_length(self, model: str) -> int:
        """
        Get maximum context length for model.

        Args:
            model: Model identifier

        Returns:
            Max context length in tokens

        Raises:
            ValueError: If model not supported
        """
        raise NotImplementedError

    @abstractmethod
    def cost_per_1k_tokens(self, model: str) -> tuple[float, float]:
        """
        Get pricing for model.

        Args:
            model: Model identifier

        Returns:
            (input_cost_usd, output_cost_usd) per 1000 tokens

        Raises:
            ValueError: If model not supported
        """
        raise NotImplementedError

    def estimate_cost(self, request: PromptRequest) -> float:
        """
        Estimate cost for request.

        Args:
            request: Prompt request

        Returns:
            Estimated cost in USD
        """
        input_tokens = self.estimate_tokens(request.prompt)
        output_tokens = request.max_tokens or 1000
        input_cost, output_cost = self.cost_per_1k_tokens(request.model)
        return (input_tokens * input_cost + output_tokens * output_cost) / 1000

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        raise NotImplementedError

    def _time_operation(self, request: PromptRequest, operation: callable) -> PromptResponse:
        """
        Execute an operation and track its duration.

        This helper method wraps an operation (typically _execute_impl) and measures
        its execution time. If the operation fails, it returns a failed PromptResponse
        with the appropriate retry code and error message.

        Args:
            request: The prompt request being processed
            operation: Callable that returns a PromptResponse

        Returns:
            PromptResponse with duration tracking and error handling
        """
        start_time = time.time()

        try:
            response = operation()
            duration = time.time() - start_time
            # Update the response with actual duration
            return response.model_copy(update={"duration_seconds": duration})
        except Exception as exc:
            duration = time.time() - start_time
            return PromptResponse(
                output="",
                success=False,
                provider=self.name,
                model=request.model,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
                duration_seconds=duration,
                retry_code=self._categorize_error(exc),
                error_message=str(exc),
            )

    def _validate_request(self, request: PromptRequest) -> None:
        """
        Validate request before execution.

        Args:
            request: Request to validate

        Raises:
            ValueError: If request is invalid
        """
        if not request.prompt and not request.messages:
            raise ValueError("Prompt cannot be empty")

        if not request.model:
            raise ValueError("Model must be specified")

        if not self.supports_model(request.model):
            raise ValueError(
                f"Model '{request.model}' not supported by {self.name}"
            )

        if request.max_tokens and request.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")

        if request.temperature is not None and not (0.0 <= request.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")

        if request.top_p is not None and not (0.0 <= request.top_p <= 1.0):
            raise ValueError("top_p must be between 0.0 and 1.0")

    def _categorize_error(self, error: Exception) -> RetryCode:
        """
        Categorize error for retry logic using structured exception inspection.

        This method uses isinstance checks for deterministic error classification,
        falling back to HTTP status codes and string heuristics for SDK exceptions.

        Args:
            error: Exception that occurred

        Returns:
            Appropriate RetryCode for retry logic
        """
        # First, check for our custom provider exceptions
        if isinstance(error, ProviderRateLimitError):
            return RetryCode.RATE_LIMIT_ERROR
        if isinstance(error, ProviderTimeoutError):
            return RetryCode.TIMEOUT_ERROR
        if isinstance(error, ProviderAuthenticationError):
            return RetryCode.AUTHENTICATION_ERROR
        if isinstance(error, ProviderModelNotAvailableError):
            return RetryCode.MODEL_NOT_AVAILABLE_ERROR
        if isinstance(error, ProviderContextLengthError):
            return RetryCode.CONTEXT_LENGTH_EXCEEDED
        if isinstance(error, ProviderContentFilterError):
            return RetryCode.CONTENT_FILTER_ERROR
        if isinstance(error, ProviderError):
            return error.retry_code

        # Check for HTTP status code on exception (common in SDK exceptions)
        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            if status_code == 429:
                return RetryCode.RATE_LIMIT_ERROR
            if status_code in (401, 403):
                return RetryCode.AUTHENTICATION_ERROR
            if status_code == 408:
                return RetryCode.TIMEOUT_ERROR

        # Check common SDK exception types by name
        error_type = type(error).__name__
        if "RateLimitError" in error_type or "RateLimited" in error_type:
            return RetryCode.RATE_LIMIT_ERROR
        if "TimeoutError" in error_type or "Timeout" in error_type:
            return RetryCode.TIMEOUT_ERROR
        if "AuthenticationError" in error_type or "Unauthorized" in error_type:
            return RetryCode.AUTHENTICATION_ERROR

        # Fall back to string inspection for unknown exceptions
        error_str = str(error).lower()
        if "rate limit" in error_str or "429" in error_str:
            return RetryCode.RATE_LIMIT_ERROR
        if "timeout" in error_str:
            return RetryCode.TIMEOUT_ERROR
        if "auth" in error_str or "401" in error_str or "403" in error_str:
            return RetryCode.AUTHENTICATION_ERROR
        if "model" in error_str and "not" in error_str:
            return RetryCode.MODEL_NOT_AVAILABLE_ERROR
        if "context" in error_str or "too long" in error_str:
            return RetryCode.CONTEXT_LENGTH_EXCEEDED
        if "content" in error_str and "filter" in error_str:
            return RetryCode.CONTENT_FILTER_ERROR

        return RetryCode.EXECUTION_ERROR

    def _calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate cost in USD.

        Args:
            model: Model identifier
            input_tokens: Input tokens used
            output_tokens: Output tokens generated

        Returns:
            Cost in USD
        """
        input_cost, output_cost = self.cost_per_1k_tokens(model)
        return (input_tokens * input_cost + output_tokens * output_cost) / 1000

    def get_metrics(self) -> ProviderMetrics:
        """
        Get atomic snapshot of provider metrics.

        Returns thread-safe immutable snapshot of current metrics.

        Returns:
            ProviderMetrics: Immutable metrics snapshot

        Example:
            >>> metrics = provider.get_metrics()
            >>> print(f"Calls: {metrics.call_count}, Cost: ${metrics.total_cost:.4f}")
        """
        with self._metrics_lock:
            return ProviderMetrics(
                call_count=self._call_count,
                total_cost=self._total_cost,
                total_tokens=self._total_tokens,
            )

    @property
    def call_count(self) -> int:
        """Number of execute() calls made (thread-safe)"""
        with self._metrics_lock:
            return self._call_count

    @property
    def total_cost(self) -> float:
        """Total cost across all calls in USD (thread-safe)"""
        with self._metrics_lock:
            return self._total_cost

    @property
    def total_tokens(self) -> int:
        """Total tokens across all calls (thread-safe)"""
        with self._metrics_lock:
            return self._total_tokens

    def _record_metrics(self, response: PromptResponse) -> None:
        """Record metrics for a completed request in a thread-safe manner."""
        with self._metrics_lock:
            self._call_count += 1
            self._total_cost += response.cost_usd
            self._total_tokens += response.total_tokens
