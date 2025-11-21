"""
Configuration models for the LLM orchestrator layer.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field

from adws.consensus.engine import ConsensusStrategy


class ProviderRoute(BaseModel):
    """
    Mapping between a logical workflow and a provider/model pairing.
    """

    provider: str = Field(..., description="Identifier registered inside ProviderRegistry")
    model: str = Field(..., description="Model name understood by the provider")
    max_tokens: int | None = Field(
        None,
        description="Optional override for maximum generation tokens",
        gt=0,
    )
    temperature: float | None = Field(
        None,
        description="Optional override for temperature",
        ge=0.0,
        le=2.0,
    )


class LLMOrchestratorConfig(BaseModel):
    """
    Tunable configuration for :class:`LLMOrchestrator`.
    """

    default_provider: str = Field(
        "claude",
        description="Provider to use when no override is supplied",
    )
    default_model: str = Field(
        "claude-3-5-sonnet-20241022",
        description="Model associated with the default provider",
    )
    backend_route: ProviderRoute = Field(
        default_factory=lambda: ProviderRoute(
            provider="claude",
            model="claude-3-5-sonnet-20241022",
            temperature=0.2,
        )
    )
    frontend_route: ProviderRoute = Field(
        default_factory=lambda: ProviderRoute(
            provider="openai",
            model="gpt-4o-mini",
            temperature=0.4,
        )
    )
    consensus_providers: List[str] = Field(
        default_factory=lambda: ["claude", "openai", "gemini"],
        description="Providers queried when consensus is requested",
        min_length=2,
    )
    consensus_strategy: ConsensusStrategy = Field(
        default=ConsensusStrategy.BEST_OF_N,
        description="Default consensus algorithm",
    )
    consensus_threshold: float = Field(
        0.67,
        description="Minimum agreement ratio for consensus results",
        ge=0.0,
        le=1.0,
    )
    consensus_timeout: float = Field(
        60.0,
        description="Timeout per provider during consensus collection",
        gt=0.0,
    )


__all__ = ["LLMOrchestratorConfig", "ProviderRoute"]
