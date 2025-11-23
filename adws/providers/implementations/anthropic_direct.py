"""
Anthropic Provider Implementation

Direct provider for Anthropic Claude using the official Anthropic Python SDK.
Makes direct API calls to Anthropic (not via Claude Code CLI).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

from adws.providers.base import BaseProvider
from adws.providers.interfaces import (
    PromptRequest,
    PromptResponse,
    ProviderConfig,
    RetryCode,
)


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic Claude models using the official SDK."""

    # Model costs (USD per 1K tokens) - as of January 2025
    # Format: (input_cost, output_cost)
    COSTS: Dict[str, Tuple[float, float]] = {
        "claude-opus-4": (0.015, 0.075),
        "claude-sonnet-4": (0.003, 0.015),
        "claude-sonnet-4-5": (0.003, 0.015),
        "claude-sonnet-4-5-20250929": (0.003, 0.015),
        "claude-3-5-sonnet-20240620": (0.003, 0.015),
        "claude-3-5-sonnet-20241022": (0.003, 0.015),
        "claude-3-opus-20240229": (0.015, 0.075),
        "claude-3-sonnet-20240229": (0.003, 0.015),
        "claude-haiku-4": (0.00025, 0.00125),
        "claude-3-haiku-20240307": (0.00025, 0.00125),
    }

    # Context window sizes
    CONTEXT_LENGTHS: Dict[str, int] = {
        "claude-opus-4": 200000,
        "claude-sonnet-4": 200000,
        "claude-sonnet-4-5": 200000,
        "claude-sonnet-4-5-20250929": 200000,
        "claude-3-5-sonnet-20240620": 200000,
        "claude-3-5-sonnet-20241022": 200000,
        "claude-3-opus-20240229": 200000,
        "claude-3-sonnet-20240229": 200000,
        "claude-haiku-4": 200000,
        "claude-3-haiku-20240307": 200000,
    }

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._last_response: Optional[PromptResponse] = None

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package not installed. Install it with: pip install anthropic"
            ) from exc

        self._anthropic_module = anthropic

        api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable or pass api_key in config"
            )

        client_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "max_retries": config.max_retries,
            "timeout": config.timeout_seconds,
        }
        if config.api_base_url:
            client_kwargs["base_url"] = config.api_base_url

        self.client = anthropic.Anthropic(**client_kwargs)

    @property
    def name(self) -> str:
        return "claude"

    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model in self.COSTS

    def max_context_length(self, model: str) -> int:
        """Get maximum context length for model."""
        return self.CONTEXT_LENGTHS.get(model, 200000)

    def cost_per_1k_tokens(self, model: str) -> Tuple[float, float]:
        """Get cost per 1K tokens (input, output) for model."""
        return self.COSTS.get(model, (0.003, 0.015))

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Rough estimation: ~4 characters per token
        return max(1, len(text) // 4)

    def _execute_impl(self, request: PromptRequest) -> PromptResponse:
        """Execute request using Anthropic API."""
        start_time = time.time()

        try:
            # Build parameters for Anthropic API
            params = {
                "model": request.model,
                "max_tokens": request.max_tokens or 4096,
                "messages": [{"role": "user", "content": request.prompt}],
            }

            if request.temperature is not None:
                params["temperature"] = request.temperature

            if request.system_message:
                params["system"] = request.system_message

            # Call Anthropic API
            response = self.client.messages.create(**params)

            duration = time.time() - start_time

            # Extract response content
            output = response.content[0].text if response.content else ""

            # Get token usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Calculate cost
            cost = self._calculate_cost(request.model, input_tokens, output_tokens)

            prompt_response = PromptResponse(
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

            self._last_response = prompt_response
            return prompt_response

        except Exception as exc:
            duration = time.time() - start_time
            # Log the full error for debugging
            import traceback
            error_details = f"{str(exc)}\n{traceback.format_exc()}"
            print(f"❌ Anthropic API Error: {error_details}")

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
                retry_code=self._determine_retry_code(exc),
                error_message=str(exc),
            )

    def _determine_retry_code(self, exc: Exception) -> RetryCode:
        """Determine appropriate retry code from exception."""
        error_str = str(exc).lower()

        if "rate" in error_str or "429" in error_str:
            return RetryCode.RATE_LIMIT
        elif "timeout" in error_str:
            return RetryCode.TIMEOUT
        elif "auth" in error_str or "401" in error_str or "403" in error_str:
            return RetryCode.AUTH_ERROR
        elif "overloaded" in error_str or "503" in error_str:
            return RetryCode.SERVER_ERROR
        else:
            return RetryCode.FATAL


__all__ = ["AnthropicProvider"]
