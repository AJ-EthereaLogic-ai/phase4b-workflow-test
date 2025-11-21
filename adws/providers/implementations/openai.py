"""
OpenAI Provider Implementation

Provider for OpenAI models via official OpenAI Python SDK with
support for streaming, function calling, and multimodal prompts.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, AsyncIterator, Union

from adws.providers.base import BaseProvider
from adws.providers.interfaces import (
    PromptMessage,
    PromptRequest,
    PromptResponse,
    ProviderConfig,
    RetryCode,
)


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI GPT models using the official SDK."""

    COSTS: Dict[str, Tuple[float, float]] = {
        "gpt-4-turbo-preview": (10.0, 30.0),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-4": (30.0, 60.0),
        "gpt-4-32k": (60.0, 120.0),
        "gpt-3.5-turbo": (0.5, 1.5),
        "gpt-4o-mini": (1.5, 5.0),
    }

    CONTEXT_LENGTHS: Dict[str, int] = {
        "gpt-4-turbo-preview": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-3.5-turbo": 16384,
        "gpt-4o-mini": 128000,
    }

    STREAMING_ENABLED = True
    FUNCTION_CALLING_ENABLED = True
    VISION_ENABLED = True

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._last_response: Optional[PromptResponse] = None

        try:
            import openai
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "openai package not installed. Install it with: pip install openai"
            ) from exc

        self._openai_module = openai
        self.client_class = openai.OpenAI
        self.async_client_class = getattr(openai, "AsyncOpenAI", None)

        api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable or pass api_key in config"
            )

        client_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "max_retries": config.max_retries,
            "timeout": config.timeout_seconds,
        }
        if config.api_base_url:
            client_kwargs["base_url"] = config.api_base_url

        self.client = self.client_class(**client_kwargs)
        self.async_client = (
            self.async_client_class(**client_kwargs)
            if self.async_client_class is not None
            else None
        )

    @property
    def name(self) -> str:
        return "openai"

    def _execute_impl(self, request: PromptRequest) -> PromptResponse:
        start_time = time.time()
        try:
            messages = self._build_messages(request)
            params = self._build_chat_params(request, messages, stream=False)
            response = self.client.chat.completions.create(**params)
            prompt_response = self._convert_completion_to_response(
                request=request,
                messages=messages,
                completion=response,
                duration=time.time() - start_time,
                streamed_chunks=[],
            )
            self._last_response = prompt_response
            return prompt_response
        except Exception as exc:  # pragma: no cover - exercised via tests
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
                retry_code=self._determine_retry_code(exc),
                error_message=str(exc),
            )

    async def execute_async(self, request: PromptRequest) -> PromptResponse:
        if self.async_client is None:
            return await super().execute_async(request)

        start_time = time.time()
        try:
            messages = self._build_messages(request)
            params = self._build_chat_params(request, messages, stream=False)
            completion = await self.async_client.chat.completions.create(**params)
            prompt_response = self._convert_completion_to_response(
                request=request,
                messages=messages,
                completion=completion,
                duration=time.time() - start_time,
                streamed_chunks=[],
            )
            self._last_response = prompt_response
            return prompt_response
        except Exception as exc:  # pragma: no cover - exercised via tests
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
                retry_code=self._determine_retry_code(exc),
                error_message=str(exc),
            )

    def stream(self, request: PromptRequest) -> Iterable[str]:
        self._validate_request(request)
        start_time = time.time()
        messages = self._build_messages(request)
        params = self._build_chat_params(request, messages, stream=True)
        stream = self.client.chat.completions.create(**params)

        streamed_chunks: List[str] = []
        usage = None
        finish_reason: Optional[str] = None
        function_call: Dict[str, Any] = {"name": None, "arguments": ""}

        try:
            for chunk in stream:
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    text_piece = getattr(delta, "content", None)
                    if text_piece:
                        streamed_chunks.append(text_piece)
                        yield text_piece
                    fc = getattr(delta, "function_call", None)
                    if fc:
                        if getattr(fc, "name", None):
                            function_call["name"] = fc.name
                        if getattr(fc, "arguments", None):
                            function_call["arguments"] += fc.arguments
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
        except Exception as exc:  # pragma: no cover - network exceptions
            duration = time.time() - start_time
            failure_response = PromptResponse(
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
                streamed_output=streamed_chunks,
            )
            self._last_response = failure_response
            return

        output_text = "".join(streamed_chunks)
        prompt_response = self._build_streaming_response(
            request=request,
            messages=messages,
            streamed_chunks=streamed_chunks,
            usage=usage,
            finish_reason=finish_reason,
            function_call=function_call,
            duration=time.time() - start_time,
        )
        self._last_response = prompt_response
        self._record_metrics(prompt_response)

    async def stream_async(self, request: PromptRequest) -> AsyncIterator[str]:
        if self.async_client is None:
            async for chunk in super().stream_async(request):
                yield chunk
            return

        self._validate_request(request)
        start_time = time.time()
        messages = self._build_messages(request)
        params = self._build_chat_params(request, messages, stream=True)
        stream = await self.async_client.chat.completions.create(**params)

        streamed_chunks: List[str] = []
        usage = None
        finish_reason: Optional[str] = None
        function_call: Dict[str, Any] = {"name": None, "arguments": ""}

        try:
            async for chunk in stream:
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    text_piece = getattr(delta, "content", None)
                    if text_piece:
                        streamed_chunks.append(text_piece)
                        yield text_piece
                    fc = getattr(delta, "function_call", None)
                    if fc:
                        if getattr(fc, "name", None):
                            function_call["name"] = fc.name
                        if getattr(fc, "arguments", None):
                            function_call["arguments"] += fc.arguments
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
        except Exception as exc:  # pragma: no cover - network exceptions
            duration = time.time() - start_time
            failure_response = PromptResponse(
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
                streamed_output=streamed_chunks,
            )
            self._last_response = failure_response
            return

        prompt_response = self._build_streaming_response(
            request=request,
            messages=messages,
            streamed_chunks=streamed_chunks,
            usage=usage,
            finish_reason=finish_reason,
            function_call=function_call,
            duration=time.time() - start_time,
        )
        self._last_response = prompt_response
        self._record_metrics(prompt_response)

    def supports_model(self, model: str) -> bool:
        return model in self.COSTS

    def max_context_length(self, model: str) -> int:
        if model not in self.CONTEXT_LENGTHS:
            raise ValueError(f"Model not supported: {model}")
        return self.CONTEXT_LENGTHS[model]

    def cost_per_1k_tokens(self, model: str) -> tuple[float, float]:
        if model not in self.COSTS:
            raise ValueError(f"Model not supported: {model}")
        input_cost_per_1m, output_cost_per_1m = self.COSTS[model]
        return (input_cost_per_1m / 1000, output_cost_per_1m / 1000)

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 1
        try:
            import tiktoken  # type: ignore

            model_aliases = getattr(self.config, "model_aliases", {})
            model_name = model_aliases.get("default", "gpt-3.5-turbo")
            try:
                encoding = tiktoken.encoding_for_model(model_name)
            except Exception:
                encoding = tiktoken.get_encoding("cl100k_base")
            return max(1, len(encoding.encode(text)))
        except ImportError:  # pragma: no cover - fallback path
            return max(1, len(text) // 3)

    def _build_messages(self, request: PromptRequest) -> List[Dict[str, Any]]:
        if request.messages:
            return [self._normalize_message(message) for message in request.messages]

        messages: List[Dict[str, Any]] = []
        if request.system_message:
            messages.append({"role": "system", "content": request.system_message})

        user_content: Any
        if request.media:
            user_content = self._build_multimodal_content(request)
        else:
            user_content = request.prompt

        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_multimodal_content(self, request: PromptRequest) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = []
        if request.prompt:
            content.append({"type": "text", "text": request.prompt})
        for media in request.media:
            media_type = media.get("type", "image_url")
            if media_type == "image_url" and media.get("url"):
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": media["url"]},
                    }
                )
            elif media_type == "image_base64" and media.get("data"):
                mime = media.get("mime_type", "image/png")
                data = media["data"]
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{data}"},
                    }
                )
            elif media_type == "image_path" and media.get("path"):
                path = Path(media["path"])
                if not path.exists():
                    raise FileNotFoundError(f"Image path not found: {path}")
                mime = media.get("mime_type", "image/png")
                data = base64.b64encode(path.read_bytes()).decode("utf-8")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{data}"},
                    }
                )
        if not content:
            content.append({"type": "text", "text": request.prompt})
        return content

    def _normalize_message(
        self, message: Union[PromptMessage, Dict[str, Any]]
    ) -> Dict[str, Any]:
        if isinstance(message, PromptMessage):
            raw = message.model_dump(exclude_none=True)
        else:
            raw = dict(message)
        normalized: Dict[str, Any] = {
            "role": raw.get("role", "user"),
        }
        content = raw.get("content")
        if isinstance(content, list):
            normalized["content"] = content
        elif isinstance(content, dict):
            normalized["content"] = [content]
        else:
            normalized["content"] = content or ""
        if "name" in raw:
            normalized["name"] = raw["name"]
        if "function_call" in raw:
            normalized["function_call"] = raw["function_call"]
        if "tool_call_id" in raw:
            normalized["tool_call_id"] = raw["tool_call_id"]
        return normalized

    def _build_chat_params(
        self,
        request: PromptRequest,
        messages: List[Dict[str, Any]],
        *,
        stream: bool
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }
        if request.max_tokens:
            params["max_tokens"] = request.max_tokens
        if request.stop_sequences:
            params["stop"] = request.stop_sequences

        tools = request.tools or request.metadata.get("tools") or request.metadata.get("functions")
        if tools:
            if any("type" in tool for tool in tools):
                params["tools"] = tools
            else:
                params["functions"] = tools

        tool_choice = request.tool_choice or request.metadata.get("tool_choice")
        if tool_choice:
            params["tool_choice"] = tool_choice

        function_call = request.function_call or request.metadata.get("function_call")
        if function_call:
            params["function_call"] = function_call

        response_format = request.response_format or request.metadata.get("response_format")
        if response_format:
            params["response_format"] = response_format

        if stream:
            params["stream"] = True

        return {key: value for key, value in params.items() if value is not None}

    def _convert_completion_to_response(
        self,
        *,
        request: PromptRequest,
        messages: List[Dict[str, Any]],
        completion: Any,
        duration: float,
        streamed_chunks: List[str],
    ) -> PromptResponse:
        choice = completion.choices[0]
        content = getattr(choice.message, "content", "") or ""
        usage = getattr(completion, "usage", None)
        finish_reason = getattr(choice, "finish_reason", None)

        input_tokens, output_tokens, total_tokens = self._resolve_usage(
            request=request,
            messages=messages,
            usage=usage,
            output_text=content,
        )
        cost = self._calculate_cost(request.model, input_tokens, output_tokens)

        metadata = {
            "id": getattr(completion, "id", None),
            "usage": getattr(usage, "to_dict", lambda: usage)() if usage else None,
            "finish_reason": finish_reason,
        }

        return PromptResponse(
            output=content,
            success=True,
            provider=self.name,
            model=request.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            duration_seconds=duration,
            retry_code=RetryCode.NONE,
            metadata={key: value for key, value in metadata.items() if value is not None},
            finish_reason=finish_reason,
            streamed_output=streamed_chunks,
        )

    def _build_streaming_response(
        self,
        *,
        request: PromptRequest,
        messages: List[Dict[str, Any]],
        streamed_chunks: List[str],
        usage: Any,
        finish_reason: Optional[str],
        function_call: Dict[str, Any],
        duration: float,
    ) -> PromptResponse:
        output_text = "".join(streamed_chunks)
        input_tokens, output_tokens, total_tokens = self._resolve_usage(
            request=request,
            messages=messages,
            usage=usage,
            output_text=output_text,
        )
        cost = self._calculate_cost(request.model, input_tokens, output_tokens)

        metadata: Dict[str, Any] = {
            "finish_reason": finish_reason,
            "function_call": function_call if function_call.get("name") else None,
            "usage": getattr(usage, "to_dict", lambda: usage)() if usage else None,
            "streamed": True,
        }

        return PromptResponse(
            output=output_text,
            success=True,
            provider=self.name,
            model=request.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            duration_seconds=duration,
            retry_code=RetryCode.NONE,
            metadata={key: value for key, value in metadata.items() if value is not None},
            finish_reason=finish_reason,
            streamed_output=list(streamed_chunks),
        )

    def _resolve_usage(
        self,
        *,
        request: PromptRequest,
        messages: List[Dict[str, Any]],
        usage: Any,
        output_text: str,
    ) -> Tuple[int, int, int]:
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
            if prompt_tokens is not None and completion_tokens is not None and total_tokens is not None:
                return int(prompt_tokens), int(completion_tokens), int(total_tokens)

        prompt_text = "\n".join(self._extract_text_fragments(messages))
        input_tokens = self.estimate_tokens(prompt_text)
        output_tokens = self.estimate_tokens(output_text)
        return input_tokens, output_tokens, input_tokens + output_tokens

    def _extract_text_fragments(self, messages: List[Dict[str, Any]]) -> List[str]:
        fragments: List[str] = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                fragments.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        fragments.append(part.get("text", ""))
        return fragments

    def _determine_retry_code(self, error: Exception) -> RetryCode:
        error_str = str(error).lower()

        try:  # pragma: no cover - requires openai exceptions
            from openai import (
                RateLimitError,
                APITimeoutError,
                AuthenticationError,
                NotFoundError,
                APIError,
                APIStatusError,
            )

            if isinstance(error, RateLimitError):
                return RetryCode.RATE_LIMIT_ERROR
            if isinstance(error, APITimeoutError):
                return RetryCode.TIMEOUT_ERROR
            if isinstance(error, AuthenticationError):
                return RetryCode.AUTHENTICATION_ERROR
            if isinstance(error, NotFoundError):
                return RetryCode.MODEL_NOT_AVAILABLE_ERROR
            if isinstance(error, APIStatusError):
                status = getattr(error, "status_code", None)
                if status == 429:
                    return RetryCode.RATE_LIMIT_ERROR
                if status and 500 <= status < 600:
                    return RetryCode.EXECUTION_ERROR
            if isinstance(error, APIError):
                return RetryCode.EXECUTION_ERROR
        except Exception:  # pragma: no cover - import guard
            pass

        if "rate limit" in error_str or "429" in error_str:
            return RetryCode.RATE_LIMIT_ERROR
        if "timeout" in error_str or "timed out" in error_str:
            return RetryCode.TIMEOUT_ERROR
        if "authentication" in error_str or "invalid api key" in error_str:
            return RetryCode.AUTHENTICATION_ERROR
        if "model" in error_str and "not" in error_str:
            return RetryCode.MODEL_NOT_AVAILABLE_ERROR
        if "context" in error_str or "too long" in error_str:
            return RetryCode.CONTEXT_LENGTH_EXCEEDED
        if "content" in error_str and "policy" in error_str:
            return RetryCode.CONTENT_FILTER_ERROR
        return RetryCode.EXECUTION_ERROR

    @property
    def last_response(self) -> Optional[PromptResponse]:
        return self._last_response
