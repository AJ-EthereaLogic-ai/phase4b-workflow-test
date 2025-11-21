"""
Consensus Module for Multi-LLM Output Combination

Provides consensus mechanisms to combine outputs from multiple
providers for improved quality and reliability.
"""

from adws.consensus.engine import (
    ConsensusEngine,
    ConsensusStrategy,
    ConsensusConfig,
    ConsensusScoringConfig,
    ConsensusResult,
    ProviderResponse,
)

__all__ = [
    "ConsensusEngine",
    "ConsensusStrategy",
    "ConsensusConfig",
    "ConsensusScoringConfig",
    "ConsensusResult",
    "ProviderResponse",
]
