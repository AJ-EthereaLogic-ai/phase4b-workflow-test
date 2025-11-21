"""
High-level orchestrator that coordinates multiple LLM providers.
"""

from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from adws.consensus.engine import (
    ConsensusConfig,
    ConsensusEngine,
    ConsensusResult,
    ConsensusStrategy,
)
from adws.llm.config import LLMOrchestratorConfig
from adws.providers import (
    ProviderRegistry,
    PromptRequest,
    PromptResponse,
    get_provider_registry,
)


class LLMRunResult(BaseModel):
    """
    Result payload returned by :class:`LLMOrchestrator`.
    """

    request: PromptRequest
    selected_provider: str
    response: PromptResponse
    provider_responses: Dict[str, PromptResponse] = Field(
        default_factory=dict,
        description="Raw responses keyed by provider id",
    )
    consensus: Optional[ConsensusResult] = Field(
        default=None, description="Consensus metadata if multi-provider execution ran"
    )
    duration_seconds: float = Field(..., description="Total wall-clock duration")


class LLMOrchestrator:
    """
    Coordinates prompt execution across multiple providers.
    """

    def __init__(
        self,
        *,
        registry: ProviderRegistry | None = None,
        config: LLMOrchestratorConfig | None = None,
        consensus_engine: ConsensusEngine | None = None,
    ) -> None:
        self._registry = registry or get_provider_registry()
        self.config = config or LLMOrchestratorConfig()
        self._consensus_engine = consensus_engine or ConsensusEngine(
            self._registry
        )

    async def execute(
        self,
        request: PromptRequest,
        *,
        providers: Optional[Iterable[str]] = None,
        consensus_strategy: ConsensusStrategy | None = None,
    ) -> LLMRunResult:
        """
        Execute a prompt on one or more providers.
        """

        provider_list = self._resolve_providers(providers)
        start = time.perf_counter()

        if len(provider_list) == 1:
            provider_name = provider_list[0]
            response = await self._execute_single(provider_name, request)
            duration = time.perf_counter() - start
            return LLMRunResult(
                request=request,
                selected_provider=provider_name,
                response=response,
                provider_responses={provider_name: response},
                duration_seconds=duration,
            )

        consensus_result = await self._execute_consensus(
            request=request,
            providers=provider_list,
            strategy=consensus_strategy or self.config.consensus_strategy,
        )
        duration = time.perf_counter() - start
        provider_responses = {
            pr.provider_id: pr.response for pr in consensus_result.responses
        }
        return LLMRunResult(
            request=request,
            selected_provider=consensus_result.response.provider,
            response=consensus_result.response,
            provider_responses=provider_responses,
            consensus=consensus_result,
            duration_seconds=duration,
        )

    def _resolve_providers(
        self, providers: Optional[Iterable[str]]
    ) -> List[str]:
        """Normalize provider identifiers."""
        if providers:
            resolved = [p.strip().lower() for p in providers if p.strip()]
        else:
            resolved = [self.config.default_provider]

        if not resolved:
            raise ValueError("At least one provider must be specified")
        return resolved

    async def _execute_single(
        self, provider_name: str, request: PromptRequest
    ) -> PromptResponse:
        provider = self._registry.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider not registered: {provider_name}")

        return await provider.execute_async(request)

    async def _execute_consensus(
        self,
        *,
        request: PromptRequest,
        providers: Iterable[str],
        strategy: ConsensusStrategy,
    ) -> ConsensusResult:
        valid_providers = [
            provider
            for provider in providers
            if self._registry.has_provider(provider)
        ]
        if len(valid_providers) < 2:
            raise ValueError(
                "Consensus execution requires at least two registered providers"
            )
        config = ConsensusConfig(
            strategy=strategy,
            providers=list(valid_providers),
            threshold=self.config.consensus_threshold,
            timeout=self.config.consensus_timeout,
        )
        return await self._consensus_engine.get_consensus_async(
            request, config
        )


__all__ = ["LLMOrchestrator", "LLMRunResult"]
