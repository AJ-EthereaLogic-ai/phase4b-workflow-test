"""
Claude Provider Implementation

Provider for Anthropic Claude via Claude Code CLI.
Wraps the existing Claude Code integration for backward compatibility.
"""

import subprocess
import time
import os
from adws.providers.base import BaseProvider
from adws.providers.interfaces import (
    PromptRequest,
    PromptResponse,
    ProviderConfig,
    RetryCode,
)


class ClaudeCodeProvider(BaseProvider):
    """
    Provider for Anthropic Claude via Claude Code CLI.

    This wraps the existing Claude Code CLI integration to maintain
    backward compatibility while providing the standard provider interface.

    Attributes:
        name: Always returns "claude"
        COSTS: Pricing per 1K tokens for each model (input, output)
        CONTEXT_LENGTHS: Maximum context window for each model

    Example:
        >>> config = ProviderConfig(name="claude", enabled=True)
        >>> provider = ClaudeCodeProvider(config)
        >>> request = PromptRequest(
        ...     prompt="Explain recursion",
        ...     model="claude-sonnet-4",
        ...     adw_id="adw_123",
        ...     slash_command="/explain",
        ...     working_dir="/tmp"
        ... )
        >>> response = provider.execute(request)
        >>> print(f"Cost: ${response.cost_usd:.4f}")
    """

    # Model costs (USD per 1K tokens) - as of January 2025
    # Format: (input_cost, output_cost)
    COSTS = {
        "claude-opus-4": (0.015, 0.075),
        "claude-sonnet-4": (0.003, 0.015),
        "claude-sonnet-4-5": (0.003, 0.015),
        "claude-sonnet-3-5": (0.003, 0.015),  # Legacy
        "claude-haiku-4": (0.0008, 0.004),
        "claude-haiku-3": (0.00025, 0.00125),  # Legacy
    }

    # Context lengths (tokens)
    CONTEXT_LENGTHS = {
        "claude-opus-4": 200000,
        "claude-sonnet-4": 200000,
        "claude-sonnet-4-5": 200000,
        "claude-sonnet-3-5": 200000,
        "claude-haiku-4": 200000,
        "claude-haiku-3": 200000,
    }

    def __init__(self, config: ProviderConfig):
        """
        Initialize Claude provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)
        self.claude_path = config.api_base_url or "claude"

    @property
    def name(self) -> str:
        """Provider name"""
        return "claude"

    def _execute_impl(self, request: PromptRequest) -> PromptResponse:
        """
        Execute via Claude Code CLI.

        Args:
            request: Standardized prompt request

        Returns:
            Standardized response

        Raises:
            subprocess.TimeoutExpired: If execution times out
            RuntimeError: If Claude CLI execution fails
        """
        start_time = time.time()

        try:
            # Build Claude Code command
            cmd = [
                self.claude_path,
                "code",
                "--model",
                request.model,
            ]

            # Add optional parameters
            if request.max_tokens:
                cmd.extend(["--max-tokens", str(request.max_tokens)])

            if request.temperature is not None:
                cmd.extend(["--temperature", str(request.temperature)])

            # Create input for stdin
            prompt_input = request.prompt
            if request.system_message:
                prompt_input = f"{request.system_message}\n\n{request.prompt}"

            # Execute Claude Code CLI
            # Security exception: check=True intentionally omitted to enable structured
            # error handling. Return codes are explicitly checked at line 136 to provide
            # detailed error responses with retry guidance to users.
            result = subprocess.run(
                cmd,
                input=prompt_input,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=request.working_dir,
                env=self._prepare_env(),
                shell=False,  # Security: prevent command injection
            )  # nosec B603 - shell=False prevents injection, return code explicitly validated

            duration = time.time() - start_time

            if result.returncode != 0:
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
                    retry_code=self._determine_retry_code(result.stderr),
                    error_message=result.stderr or "Claude CLI execution failed",
                )

            # Extract output
            output = result.stdout.strip()

            # Estimate tokens (Claude CLI doesn't always return actual counts)
            input_tokens = self.estimate_tokens(request.prompt)
            output_tokens = self.estimate_tokens(output)
            total_tokens = input_tokens + output_tokens

            # Calculate cost
            cost = self._calculate_cost(request.model, input_tokens, output_tokens)

            return PromptResponse(
                output=output,
                success=True,
                provider=self.name,
                model=request.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
                duration_seconds=duration,
                retry_code=RetryCode.NONE,
            )

        except subprocess.TimeoutExpired:
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
                retry_code=RetryCode.TIMEOUT_ERROR,
                error_message="Request timed out",
            )
        except FileNotFoundError:
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
                retry_code=RetryCode.EXECUTION_ERROR,
                error_message=f"Claude CLI not found at: {self.claude_path}",
            )

    def supports_model(self, model: str) -> bool:
        """
        Check if model is supported.

        Args:
            model: Model identifier

        Returns:
            True if supported

        Example:
            >>> provider.supports_model("claude-sonnet-4")
            True
            >>> provider.supports_model("gpt-4")
            False
        """
        return model in self.COSTS

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
        if model not in self.CONTEXT_LENGTHS:
            raise ValueError(f"Model not supported: {model}")
        return self.CONTEXT_LENGTHS[model]

    def cost_per_1k_tokens(self, model: str) -> tuple[float, float]:
        """
        Get pricing for model.

        Args:
            model: Model identifier

        Returns:
            (input_cost, output_cost) per 1000 tokens

        Raises:
            ValueError: If model not supported

        Example:
            >>> input_cost, output_cost = provider.cost_per_1k_tokens("claude-sonnet-4")
            >>> print(f"Input: ${input_cost}, Output: ${output_cost}")
        """
        if model not in self.COSTS:
            raise ValueError(f"Model not supported: {model}")
        return self.COSTS[model]

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses rough approximation of 4 characters per token.
        For more accurate counting, use actual tokenizer.

        Args:
            text: Input text

        Returns:
            Estimated token count

        Example:
            >>> tokens = provider.estimate_tokens("Hello, world!")
            >>> print(f"Estimated tokens: {tokens}")
        """
        # Rough estimate: 4 characters per token
        # This is conservative for Claude models
        return max(1, len(text) // 4)

    def _prepare_env(self) -> dict:
        """
        Prepare environment variables for Claude CLI.

        Returns:
            Environment dictionary
        """
        env = os.environ.copy()

        # Add or remove API key based on configuration.
        # The provider configuration is treated as the single source of truth:
        # - If an API key is configured, ensure ANTHROPIC_API_KEY is set.
        # - If no API key is configured, ensure ANTHROPIC_API_KEY is not present,
        #   even if it exists in the parent process environment.
        if self.config.api_key:
            env["ANTHROPIC_API_KEY"] = self.config.api_key
        else:
            env.pop("ANTHROPIC_API_KEY", None)

        return env

    def _determine_retry_code(self, error_message: str) -> RetryCode:
        """
        Determine retry code from error message.

        Args:
            error_message: Error message from CLI

        Returns:
            Appropriate RetryCode
        """
        if not error_message:
            return RetryCode.EXECUTION_ERROR

        error_lower = error_message.lower()

        if "rate limit" in error_lower or "429" in error_lower:
            return RetryCode.RATE_LIMIT_ERROR
        elif "timeout" in error_lower:
            return RetryCode.TIMEOUT_ERROR
        elif "authentication" in error_lower or "api key" in error_lower:
            return RetryCode.AUTHENTICATION_ERROR
        elif "model" in error_lower and (
            "not found" in error_lower or "unavailable" in error_lower
        ):
            return RetryCode.MODEL_NOT_AVAILABLE_ERROR
        elif "context" in error_lower or "too long" in error_lower:
            return RetryCode.CONTEXT_LENGTH_EXCEEDED
        else:
            return RetryCode.EXECUTION_ERROR
