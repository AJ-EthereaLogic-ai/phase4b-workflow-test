"""
Provider Interface Definitions

Defines the core protocols and data models for LLM provider abstraction.
All providers must implement the LLMProvider protocol to be usable in ADWS.
"""

from typing import (
    Protocol,
    Optional,
    Dict,
    Any,
    List,
    Iterable,
    AsyncIterator,
    Literal,
)
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum
from datetime import datetime, UTC
from dataclasses import dataclass


class RetryCode(str, Enum):
    """
    Error categorization for retry logic.

    Used to determine whether a failed request should be retried
    and with what strategy.
    """

    NONE = "none"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TIMEOUT_ERROR = "timeout_error"
    AUTHENTICATION_ERROR = "authentication_error"
    MODEL_NOT_AVAILABLE_ERROR = "model_not_available_error"
    EXECUTION_ERROR = "execution_error"
    CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
    CONTENT_FILTER_ERROR = "content_filter_error"


# ============================================================================
# Custom Provider Exception Hierarchy
# ============================================================================


class ProviderError(Exception):
    """
    Base exception for all provider-related errors.

    All provider exceptions should inherit from this class to enable
    structured error handling and deterministic retry logic.
    """

    def __init__(self, message: str, retry_code: RetryCode = RetryCode.EXECUTION_ERROR):
        super().__init__(message)
        self.retry_code = retry_code


class ProviderRateLimitError(ProviderError):
    """
    Raised when provider rate limits are exceeded.

    This typically indicates a 429 status code or explicit rate limit message.
    Should be retried with exponential backoff.
    """

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, RetryCode.RATE_LIMIT_ERROR)


class ProviderTimeoutError(ProviderError):
    """
    Raised when provider request times out.

    Can be retried with increased timeout or after a delay.
    """

    def __init__(self, message: str = "Request timeout"):
        super().__init__(message, RetryCode.TIMEOUT_ERROR)


class ProviderAuthenticationError(ProviderError):
    """
    Raised when authentication fails.

    This typically indicates invalid API keys or expired credentials.
    Should not be retried without fixing authentication.
    """

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, RetryCode.AUTHENTICATION_ERROR)


class ProviderModelNotAvailableError(ProviderError):
    """
    Raised when requested model is not available.

    This can be due to model not existing, being deprecated, or temporarily unavailable.
    May be retryable if the unavailability is temporary.
    """

    def __init__(self, message: str = "Model not available"):
        super().__init__(message, RetryCode.MODEL_NOT_AVAILABLE_ERROR)


class ProviderContextLengthError(ProviderError):
    """
    Raised when input exceeds model's context length.

    Should not be retried without reducing input size.
    """

    def __init__(self, message: str = "Context length exceeded"):
        super().__init__(message, RetryCode.CONTEXT_LENGTH_EXCEEDED)


class ProviderContentFilterError(ProviderError):
    """
    Raised when content violates provider's content policy.

    Should not be retried without modifying the content.
    """

    def __init__(self, message: str = "Content filter triggered"):
        super().__init__(message, RetryCode.CONTENT_FILTER_ERROR)


# ============================================================================
# Provider Metrics
# ============================================================================


@dataclass(frozen=True)
class ProviderMetrics:
    """
    Immutable snapshot of provider metrics.

    Provides thread-safe access to provider statistics by creating
    atomic snapshots under lock.

    Attributes:
        call_count: Total number of execute() calls
        total_cost: Cumulative cost in USD
        total_tokens: Cumulative token usage

    Example:
        >>> metrics = provider.get_metrics()
        >>> print(f"Calls: {metrics.call_count}, Cost: ${metrics.total_cost:.4f}")
    """

    call_count: int
    total_cost: float
    total_tokens: int


class PromptMessage(BaseModel):
    """
    Provider-agnostic chat message representation.

    Ensures messages always include a valid role and non-empty content so that
    downstream providers (OpenAI, Claude, etc.) receive normalized input.
    """

    role: Literal["system", "user", "assistant", "tool"] = Field(
        ..., description="Message role"
    )
    content: Any = Field(..., description="Message content (text or multimodal list)")
    name: Optional[str] = Field(None, description="Optional speaker name/identifier")
    tool_call_id: Optional[str] = Field(
        None, description="Optional tool invocation identifier"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("content must not be empty")
        if isinstance(value, str) and not value.strip():
            raise ValueError("content must not be an empty string")
        if isinstance(value, list) and not value:
            raise ValueError("content list must not be empty")
        return value


class PromptRequest(BaseModel):
    """
    Standardized prompt request across all providers.

    This model normalizes requests so workflows do not need
    provider-specific knowledge. It includes support for
    advanced functionality such as structured message history,
    streaming preferences, function/tool calling, and
    multi-modal (vision) attachments.

    Attributes:
        prompt: The prompt text to send to the LLM
        model: Model identifier (e.g., 'claude-sonnet-4', 'gpt-4')
        max_tokens: Maximum tokens to generate (None = provider default)
        temperature: Temperature for sampling (0.0-2.0, None = provider default)
        top_p: Top-p sampling parameter (0.0-1.0, None = provider default)
        adw_id: Workflow identifier for tracking
        slash_command: Slash command being executed
        working_dir: Working directory path for context
        metadata: Additional metadata for tracking/logging
        system_message: System message/instructions for the LLM
        stop_sequences: Sequences that stop generation
        messages: Optional chat history in provider-agnostic format
        media: Optional media attachments for multi-modal prompts
        tools: Optional tool/function definitions for function calling
        tool_choice: Optional explicit tool selection
        function_call: Legacy function-call directive for OpenAI compatibility
        response_format: Optional structured response schema hint
        stream: Whether the caller prefers streaming responses

    Example:
        >>> request = PromptRequest(
        ...     prompt="Explain Python decorators",
        ...     model="claude-sonnet-4",
        ...     max_tokens=2000,
        ...     temperature=0.7,
        ...     adw_id="adw_abc123",
        ...     slash_command="/explain",
        ...     working_dir="/path/to/project"
        ... )
    """

    # Core fields
    prompt: str = Field(..., description="The prompt text", min_length=1)
    model: str = Field(..., description="Model identifier", min_length=1)

    # Generation parameters
    max_tokens: Optional[int] = Field(
        None,
        description="Maximum tokens to generate",
        gt=0,
        le=200000
    )
    temperature: Optional[float] = Field(
        None,
        description="Temperature (0-2)",
        ge=0.0,
        le=2.0
    )
    top_p: Optional[float] = Field(
        None,
        description="Top-p sampling",
        ge=0.0,
        le=1.0
    )

    # Workflow context
    adw_id: str = Field(..., description="Workflow identifier")
    slash_command: str = Field(..., description="Slash command being executed")
    working_dir: str = Field(..., description="Working directory path")

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    # Advanced options
    system_message: Optional[str] = Field(
        None,
        description="System message/instructions",
    )
    stop_sequences: Optional[List[str]] = Field(
        None,
        description="Stop sequences",
    )
    messages: Optional[List[PromptMessage]] = Field(
        None,
        description="Optional structured chat history in provider-agnostic format",
    )
    media: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional multi-modal attachments such as images",
    )
    tools: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Tool/function definitions for function calling",
    )
    tool_choice: Optional[Dict[str, Any]] = Field(
        None,
        description="Explicit tool selection for providers that support it",
    )
    function_call: Optional[Dict[str, Any]] = Field(
        None,
        description="Legacy OpenAI function-call directive",
    )
    response_format: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured response schema hint",
    )
    stream: bool = Field(
        False,
        description="Whether the caller requests streaming output",
    )

    model_config = ConfigDict(
        extra="allow",  # Allow provider-specific fields
        json_schema_extra={
            "example": {
                "prompt": "Write a Python function to calculate fibonacci numbers",
                "model": "claude-sonnet-4",
                "max_tokens": 2000,
                "temperature": 0.7,
                "adw_id": "adw_abc123",
                "slash_command": "/implement",
                "working_dir": "/home/user/project",
                "stream": False
            }
        }
    )


class PromptResponse(BaseModel):
    """
    Standardized response from any provider.

    Normalizes provider responses for consistent handling across
    different LLM providers.

    Attributes:
        output: Generated output text from the LLM
        success: Whether the request succeeded
        provider: Provider name (e.g., 'claude', 'openai', 'gemini')
        model: Actual model used (may differ from requested)
        input_tokens: Input tokens consumed
        output_tokens: Output tokens generated
        total_tokens: Total tokens (input + output)
        cost_usd: Cost in USD for this request
        duration_seconds: Execution duration in seconds
        timestamp: Response timestamp (UTC)
        retry_code: Error category for retry logic
        error_message: Error message if failed
        session_id: Session/conversation ID if applicable
        metadata: Additional provider-specific metadata
        finish_reason: Provider-specific finish reason value
        streamed_output: Sequence of streamed chunks if streaming was used

    Properties:
        failed: Convenience property returning True if success is False

    Example:
        >>> response = PromptResponse(
        ...     output="Here's a Python fibonacci function...",
        ...     success=True,
        ...     provider="claude",
        ...     model="claude-sonnet-4",
        ...     input_tokens=150,
        ...     output_tokens=300,
        ...     total_tokens=450,
        ...     cost_usd=0.0135,
        ...     duration_seconds=2.5
        ... )
        >>> assert not response.failed
    """

    # Core response
    output: str = Field(..., description="Generated output text")
    success: bool = Field(..., description="Whether request succeeded")

    # Provider info
    provider: str = Field(..., description="Provider name", min_length=1)
    model: str = Field(..., description="Actual model used", min_length=1)

    # Token usage and cost
    input_tokens: int = Field(..., description="Input tokens consumed", ge=0)
    output_tokens: int = Field(..., description="Output tokens generated", ge=0)
    total_tokens: int = Field(..., description="Total tokens", ge=0)
    cost_usd: float = Field(..., description="Cost in USD", ge=0.0)

    # Performance metrics
    duration_seconds: float = Field(..., description="Execution duration", ge=0.0)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Response timestamp (UTC)",
    )

    # Error handling
    retry_code: RetryCode = Field(
        default=RetryCode.NONE,
        description="Error category for retries",
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if failed",
    )

    # Session tracking
    session_id: Optional[str] = Field(
        None,
        description="Session/conversation ID",
    )

    # Provider metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata",
    )
    finish_reason: Optional[str] = Field(
        None,
        description="Provider-specific finish reason",
    )
    streamed_output: List[str] = Field(
        default_factory=list,
        description="Captured streaming chunks in order",
    )

    @property
    def failed(self) -> bool:
        """Whether request failed"""
        return not self.success

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "output": "Here's the fibonacci function...",
                "success": True,
                "provider": "claude",
                "model": "claude-sonnet-4",
                "input_tokens": 150,
                "output_tokens": 300,
                "total_tokens": 450,
                "cost_usd": 0.0135,
                "duration_seconds": 2.5,
                "retry_code": "none",
                "finish_reason": "stop",
                "streamed_output": []
            }
        }
    )


class ProviderConfig(BaseModel):
    """
    Configuration for a single provider.

    Attributes:
        name: Provider name (e.g., 'claude', 'openai', 'gemini')
        enabled: Whether provider is enabled
        api_key: API key (or loaded from environment)
        api_base_url: Custom API base URL (optional)
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum retry attempts
        rate_limit_per_minute: Rate limit (requests per minute)
        cost_multiplier: Cost multiplier for budgeting
        model_aliases: Model name mappings

    Example:
        >>> config = ProviderConfig(
        ...     name="claude",
        ...     enabled=True,
        ...     api_key="sk-ant-...",
        ...     timeout_seconds=120.0,
        ...     max_retries=3
        ... )
    """

    name: str = Field(..., description="Provider name", min_length=1)
    enabled: bool = Field(True, description="Whether provider is enabled")
    api_key: Optional[str] = Field(None, description="API key")
    api_base_url: Optional[str] = Field(None, description="Custom API base URL")
    timeout_seconds: float = Field(
        120.0,
        description="Request timeout",
        gt=0.0,
        le=600.0
    )
    max_retries: int = Field(
        3,
        description="Maximum retry attempts",
        ge=0,
        le=10
    )
    rate_limit_per_minute: Optional[int] = Field(
        None,
        description="Rate limit (requests/min)",
        gt=0
    )

    # Cost settings
    cost_multiplier: float = Field(
        1.0,
        description="Cost multiplier for budgeting",
        gt=0.0,
        le=10.0
    )

    # Model mappings
    model_aliases: Dict[str, str] = Field(
        default_factory=dict,
        description="Model name mappings (canonical -> provider-specific)",
    )

    model_config = ConfigDict(
        extra="allow",  # Allow provider-specific config
        json_schema_extra={
            "example": {
                "name": "claude",
                "enabled": True,
                "api_key": "sk-ant-...",
                "timeout_seconds": 120.0,
                "max_retries": 3,
                "cost_multiplier": 1.0
            }
        }
    )


class LLMProvider(Protocol):
    """
    Abstract interface for LLM providers.

    All providers must implement this protocol to be usable
    in the ADWS multi-LLM system.

    Design Notes:
        - Uses Protocol for structural subtyping (duck typing)
        - Supports both sync and async execution
        - Built-in cost tracking and token estimation
        - Health check and capability reporting
        - Streaming helpers for incremental output consumption

    Example Implementation:
        >>> class MyProvider:
        ...     @property
        ...     def name(self) -> str:
        ...         return "myprovider"
        ...
        ...     def execute(self, request: PromptRequest) -> PromptResponse:
        ...         # Implementation here
        ...         raise NotImplementedError
        ...
        ...     async def execute_async(self, request: PromptRequest) -> PromptResponse:
        ...         # Async implementation
        ...         raise NotImplementedError
        ...
        ...     def stream(self, request: PromptRequest) -> Iterable[str]:
        ...         # Streaming implementation
        ...         yield "chunk"
        ...
        ...     async def stream_async(self, request: PromptRequest) -> AsyncIterator[str]:
        ...         # Async streaming implementation
        ...         yield "chunk"
        ...
        ...     # ... implement other methods
    """

    @property
    def name(self) -> str:
        """Provider name (e.g., 'claude', 'openai', 'gemini')"""
        ...

    def execute(self, request: PromptRequest) -> PromptResponse:
        """
        Execute prompt synchronously.

        Args:
            request: Standardized prompt request

        Returns:
            Standardized response with success/failure info

        Raises:
            ValueError: If request is invalid
            RuntimeError: On unrecoverable errors
        """
        ...

    async def execute_async(self, request: PromptRequest) -> PromptResponse:
        """
        Execute prompt asynchronously (for parallel execution).

        Args:
            request: Standardized prompt request

        Returns:
            Standardized response with success/failure info

        Raises:
            ValueError: If request is invalid
            RuntimeError: On unrecoverable errors
        """
        ...

    def stream(self, request: PromptRequest) -> Iterable[str]:
        """
        Stream prompt output synchronously.

        Args:
            request: Standardized prompt request

        Yields:
            Incremental text chunks from the provider
        """
        ...

    async def stream_async(self, request: PromptRequest) -> AsyncIterator[str]:
        """
        Stream prompt output asynchronously.

        Args:
            request: Standardized prompt request

        Yields:
            Incremental text chunks from the provider
        """
        ...

    def supports_model(self, model: str) -> bool:
        """
        Check if provider supports the specified model.

        Args:
            model: Model identifier (e.g., 'claude-sonnet-4', 'gpt-4')

        Returns:
            True if model is supported, False otherwise
        """
        ...

    def max_context_length(self, model: str) -> int:
        """
        Get maximum context length for model.

        Args:
            model: Model identifier

        Returns:
            Maximum context length in tokens

        Raises:
            ValueError: If model not supported
        """
        ...

    def cost_per_1k_tokens(self, model: str) -> tuple[float, float]:
        """
        Get pricing for model.

        Args:
            model: Model identifier

        Returns:
            Tuple of (input_cost_usd, output_cost_usd) per 1000 tokens

        Raises:
            ValueError: If model not supported
        """
        ...

    def estimate_cost(self, request: PromptRequest) -> float:
        """
        Estimate cost for request (USD).

        Args:
            request: Prompt request

        Returns:
            Estimated cost in USD
        """
        ...

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        ...
