"""
Google Gemini Provider Implementation

Provider for Google Gemini models via official Google Generative AI SDK with
streaming, multimodal prompts, and native token accounting.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from adws.providers.base import BaseProvider
from adws.providers.interfaces import (
    PromptRequest,
    PromptResponse,
    ProviderConfig,
    RetryCode,
)


class GeminiProvider(BaseProvider):
    """Provider for Google Gemini models via google-generativeai SDK."""

    COSTS: Dict[str, Tuple[float, float]] = {
        "gemini-1.5-pro-latest": (3.5, 10.5),
        "gemini-1.5-pro": (3.5, 10.5),
        "gemini-1.5-flash-latest": (0.35, 1.05),
        "gemini-1.5-flash": (0.35, 1.05),
        "gemini-pro": (0.5, 1.5),
        "gemini-pro-vision": (0.5, 1.5),
    }

    CONTEXT_LENGTHS: Dict[str, int] = {
        "gemini-1.5-pro-latest": 1_000_000,
        "gemini-1.5-pro": 1_000_000,
        "gemini-1.5-flash-latest": 1_000_000,
        "gemini-1.5-flash": 1_000_000,
        "gemini-pro": 32_768,
        "gemini-pro-vision": 16_384,
    }

    STREAMING_ENABLED = True
    VISION_ENABLED = True

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._last_response: Optional[PromptResponse] = None

        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "google-generativeai package not installed. Install it with: pip install google-generativeai"
            ) from exc

        self.genai = genai

        api_key = config.api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Google API key not provided. Set GOOGLE_API_KEY environment variable or pass api_key in config"
            )

        self.genai.configure(api_key=api_key)
        self._token_counter_model = self.genai.GenerativeModel("gemini-pro")

    @property
    def name(self) -> str:
        return "gemini"

    def _execute_impl(self, request: PromptRequest) -> PromptResponse:
        start_time = time.time()
        try:
            model = self._create_model(request)
            contents = self._build_contents(request)
            generation_config = self._build_generation_config(request)
            safety_settings = request.metadata.get("safety_settings")

            response = model.generate_content(
                contents=contents,
                generation_config=generation_config,
                safety_settings=safety_settings,
                stream=False,
            )

            output_text = self._extract_text_from_response(response)
            usage = getattr(response, "usage_metadata", None)
            finish_reason = self._extract_finish_reason(response)

            input_tokens, output_tokens, total_tokens = self._resolve_usage(
                request=request,
                contents=contents,
                usage=usage,
                output_text=output_text,
            )
            cost = self._calculate_cost(request.model, input_tokens, output_tokens)

            prompt_response = PromptResponse(
                output=output_text,
                success=True,
                provider=self.name,
                model=request.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
                duration_seconds=time.time() - start_time,
                retry_code=RetryCode.NONE,
                metadata={
                    "usage": self._maybe_to_dict(usage),
                    "finish_reason": finish_reason,
                },
                finish_reason=finish_reason,
                streamed_output=[],
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
        model = self._create_model(request)
        contents = self._build_contents(request)
        generation_config = self._build_generation_config(request)
        safety_settings = request.metadata.get("safety_settings")

        streamed_chunks: List[str] = []
        usage = None
        finish_reason: Optional[str] = None

        try:
            stream = model.generate_content(
                contents=contents,
                generation_config=generation_config,
                safety_settings=safety_settings,
                stream=True,
            )
            for chunk in stream:
                text_piece = self._extract_text_from_response(chunk)
                if text_piece:
                    streamed_chunks.append(text_piece)
                    yield text_piece
                usage = getattr(chunk, "usage_metadata", usage)
                if not finish_reason:
                    finish_reason = self._extract_finish_reason(chunk)
        except Exception as exc:  # pragma: no cover - network errors
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
        input_tokens, output_tokens, total_tokens = self._resolve_usage(
            request=request,
            contents=contents,
            usage=usage,
            output_text=output_text,
        )
        cost = self._calculate_cost(request.model, input_tokens, output_tokens)

        prompt_response = PromptResponse(
            output=output_text,
            success=True,
            provider=self.name,
            model=request.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            duration_seconds=time.time() - start_time,
            retry_code=RetryCode.NONE,
            metadata={
                "usage": self._maybe_to_dict(usage),
                "finish_reason": finish_reason,
                "streamed": True,
            },
            finish_reason=finish_reason,
            streamed_output=list(streamed_chunks),
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
            count = self._token_counter_model.count_tokens(text)
            total = getattr(count, "total_tokens", None)
            if total is None:
                total = getattr(count, "token_count", None)
            return int(total) if total is not None else max(1, int(len(text) / 3.5))
        except Exception:  # pragma: no cover - fallback
            return max(1, int(len(text) / 3.5))

    def _create_model(self, request: PromptRequest):
        tools = request.tools or request.metadata.get("tools")
        tool_config = request.metadata.get("tool_config")
        system_instruction = request.system_message or request.metadata.get("system_instruction")
        return self.genai.GenerativeModel(
            model_name=request.model,
            system_instruction=system_instruction,
            tools=tools,
            tool_config=tool_config,
        )

    def _build_contents(self, request: PromptRequest) -> List[Dict[str, Any]]:
        if request.messages:
            return [self._convert_message(message) for message in request.messages]

        parts = []
        if request.prompt:
            parts.append({"text": request.prompt})
        for media in request.media:
            parts.append(self._convert_media(media))
        if not parts:
            parts.append({"text": request.prompt})
        return [{"role": "user", "parts": parts}]

    def _convert_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        role = message.get("role", "user")
        content = message.get("content")
        parts: List[Dict[str, Any]] = []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append({"text": item.get("text", "")})
                    elif item.get("type") in {"image", "image_base64"}:
                        parts.append(self._convert_media(item))
                else:
                    parts.append({"text": str(item)})
        elif isinstance(content, dict):
            if content.get("type") == "text":
                parts.append({"text": content.get("text", "")})
            else:
                parts.append(self._convert_media(content))
        elif content is None:
            parts.append({"text": ""})
        else:
            parts.append({"text": str(content)})
        if not parts:
            parts.append({"text": ""})
        return {"role": role, "parts": parts}

    def _convert_media(self, media: Dict[str, Any]) -> Dict[str, Any]:
        media_type = media.get("type", "image_base64")
        if media_type == "image_url" and media.get("url"):
            return {"file_data": {"file_uri": media["url"]}}
        if media_type == "image_path" and media.get("path"):
            path = Path(media["path"])
            if not path.exists():
                raise FileNotFoundError(f"Image path not found: {path}")
            mime = media.get("mime_type", "image/png")
            data = path.read_bytes()
            return {"inline_data": {"mime_type": mime, "data": data}}
        if media_type in {"image_base64", "image"} and media.get("data"):
            mime = media.get("mime_type", "image/png")
            try:
                data_bytes = base64.b64decode(media["data"], validate=True)
            except Exception:
                data_bytes = media["data"].encode("utf-8")
            return {"inline_data": {"mime_type": mime, "data": data_bytes}}
        raise ValueError("Unsupported media payload for Gemini provider")

    def _build_generation_config(self, request: PromptRequest) -> Dict[str, Any]:
        config: Dict[str, Any] = {}
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.top_p is not None:
            config["top_p"] = request.top_p
        if request.max_tokens is not None:
            config["max_output_tokens"] = request.max_tokens
        response_format = request.response_format or request.metadata.get("response_format")
        if response_format:
            if "response_mime_type" in response_format:
                config["response_mime_type"] = response_format["response_mime_type"]
            if "schema" in response_format:
                config["response_schema"] = response_format["schema"]
        return config

    def _resolve_usage(
        self,
        *,
        request: PromptRequest,
        contents: List[Dict[str, Any]],
        usage: Any,
        output_text: str,
    ) -> Tuple[int, int, int]:
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", None)
            completion_tokens = getattr(usage, "candidates_token_count", None)
            total_tokens = getattr(usage, "total_token_count", None)
            if prompt_tokens is not None and completion_tokens is not None and total_tokens is not None:
                return int(prompt_tokens), int(completion_tokens), int(total_tokens)

        prompt_text = "\n".join(self._extract_text_from_contents(contents))
        input_tokens = self.estimate_tokens(prompt_text)
        output_tokens = self.estimate_tokens(output_text)
        return input_tokens, output_tokens, input_tokens + output_tokens

    def _extract_text_from_contents(self, contents: List[Dict[str, Any]]) -> List[str]:
        fragments: List[str] = []
        for message in contents:
            for part in message.get("parts", []):
                if "text" in part:
                    fragments.append(part["text"])
        return fragments

    def _extract_text_from_response(self, response: Any) -> str:
        if hasattr(response, "text") and response.text:
            return str(response.text)
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and candidate.content and getattr(candidate.content, "parts", None):
                texts = [getattr(part, "text", "") for part in candidate.content.parts]
                return "".join(texts)
        return ""

    def _extract_finish_reason(self, response: Any) -> Optional[str]:
        try:
            if hasattr(response, "candidates") and response.candidates:
                finish = response.candidates[0].finish_reason
                return str(finish) if finish is not None else None
        except Exception:
            return None
        return None

    def _maybe_to_dict(self, usage: Any) -> Any:
        if usage is None:
            return None
        to_dict = getattr(usage, "to_dict", None)
        if callable(to_dict):
            try:
                return to_dict()
            except Exception:
                return usage
        return usage

    def _determine_retry_code(self, error: Exception) -> RetryCode:
        error_str = str(error).lower()
        try:  # pragma: no cover - requires google api exceptions
            from google.api_core.exceptions import (
                ResourceExhausted,
                DeadlineExceeded,
                Unauthenticated,
                NotFound,
                InternalServerError,
                ServiceUnavailable,
            )

            if isinstance(error, ResourceExhausted):
                return RetryCode.RATE_LIMIT_ERROR
            if isinstance(error, DeadlineExceeded):
                return RetryCode.TIMEOUT_ERROR
            if isinstance(error, Unauthenticated):
                return RetryCode.AUTHENTICATION_ERROR
            if isinstance(error, NotFound):
                return RetryCode.MODEL_NOT_AVAILABLE_ERROR
            if isinstance(error, (InternalServerError, ServiceUnavailable)):
                return RetryCode.EXECUTION_ERROR
        except Exception:
            pass

        if "quota" in error_str or "rate" in error_str or "429" in error_str:
            return RetryCode.RATE_LIMIT_ERROR
        if "timeout" in error_str or "deadline" in error_str:
            return RetryCode.TIMEOUT_ERROR
        if "unauthenticated" in error_str or "authentication" in error_str or "invalid api key" in error_str:
            return RetryCode.AUTHENTICATION_ERROR
        if "model" in error_str and "not" in error_str:
            return RetryCode.MODEL_NOT_AVAILABLE_ERROR
        if "context" in error_str or "too long" in error_str:
            return RetryCode.CONTEXT_LENGTH_EXCEEDED
        if "safety" in error_str or "blocked" in error_str:
            return RetryCode.CONTENT_FILTER_ERROR
        return RetryCode.EXECUTION_ERROR

    @property
    def last_response(self) -> Optional[PromptResponse]:
        return self._last_response
