"""
Consensus Engine for Multi-Provider Output Combination

Implements consensus algorithms to combine outputs from multiple
LLM providers for improved quality and reliability.
"""

import asyncio
from datetime import datetime, UTC
from typing import List, Optional, Dict, Callable
from enum import Enum
from pydantic import BaseModel, Field

from adws.providers.interfaces import PromptRequest, PromptResponse, LLMProvider, RetryCode
from adws.providers.registry import ProviderRegistry

# Try to import rapidfuzz, fall back to manual implementation if not available
try:
    from rapidfuzz.distance import Levenshtein as RapidFuzzLevenshtein
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


class ConsensusStrategy(str, Enum):
    """
    Available consensus strategies.

    Strategies:
        MAJORITY_VOTE: Select most common response (requires threshold)
        BEST_OF_N: Score responses and select highest quality
        WEIGHTED_AVERAGE: Combine responses with provider weights
        ALL_AGREE: Require all providers to agree (strictest)

    Example:
        >>> strategy = ConsensusStrategy.MAJORITY_VOTE
    """
    MAJORITY_VOTE = "majority-vote"
    BEST_OF_N = "best-of-n"
    WEIGHTED_AVERAGE = "weighted-average"
    ALL_AGREE = "all-agree"


class ConsensusConfig(BaseModel):
    """
    Configuration for consensus execution.

    Attributes:
        strategy: Consensus strategy to use
        providers: List of provider IDs to query
        threshold: Agreement threshold (0.0-1.0, default 0.67 for 2/3)
        max_attempts: Maximum consensus attempts
        timeout: Timeout per provider in seconds
        similarity_threshold: Similarity threshold for grouping (default 0.8)
        provider_weights: Weights for weighted average (optional)

    Example:
        >>> config = ConsensusConfig(
        ...     strategy=ConsensusStrategy.MAJORITY_VOTE,
        ...     providers=["claude", "openai", "gemini"],
        ...     threshold=0.67,
        ...     max_attempts=3,
        ...     timeout=60.0
        ... )
    """
    strategy: ConsensusStrategy = Field(
        ...,
        description="Consensus strategy"
    )
    providers: List[str] = Field(
        ...,
        description="Provider IDs to query",
        min_length=2
    )
    threshold: float = Field(
        default=0.67,
        description="Agreement threshold",
        ge=0.0,
        le=1.0
    )
    max_attempts: int = Field(
        default=3,
        description="Maximum attempts",
        ge=1,
        le=10
    )
    timeout: float = Field(
        default=60.0,
        description="Timeout seconds",
        ge=1.0,
        le=300.0
    )
    similarity_threshold: float = Field(
        default=0.8,
        description="Similarity threshold for grouping",
        ge=0.0,
        le=1.0
    )
    provider_weights: Optional[Dict[str, float]] = Field(
        None,
        description="Provider weights for weighted average"
    )


class ConsensusScoringConfig(BaseModel):
    """
    Configuration for consensus response scoring.

    Allows customization of how responses are scored for quality.
    Higher weights increase importance of that metric.

    Attributes:
        success_weight: Weight for success status (default 50.0)
        short_response_penalty: Penalty for responses < min_length (default 30.0)
        min_response_length: Minimum response length to avoid penalty (default 50)
        long_response_penalty: Penalty for responses > max_length (default 10.0)
        max_response_length: Maximum response length to avoid penalty (default 5000)
        structured_content_bonus: Bonus for newlines in output (default 10.0)
        code_block_bonus: Bonus for code blocks in output (default 10.0)
        token_count_weight: Weight for output token count (default 0.0)
        cost_weight: Weight for cost (negative = prefer lower cost) (default 0.0)
        latency_weight: Weight for latency (negative = prefer lower latency) (default 0.0)
        provider_reputation_weight: Weight for provider reputation (default 0.0)
        custom_scorer: Optional custom scoring function (default None)

    Example:
        >>> config = ConsensusScoringConfig(
        ...     success_weight=60.0,
        ...     short_response_penalty=40.0,
        ...     code_block_bonus=15.0
        ... )
    """
    success_weight: float = Field(
        default=50.0,
        description="Weight for success status"
    )
    short_response_penalty: float = Field(
        default=30.0,
        description="Penalty for very short responses",
        ge=0.0
    )
    min_response_length: int = Field(
        default=50,
        description="Minimum response length",
        ge=0
    )
    long_response_penalty: float = Field(
        default=10.0,
        description="Penalty for very long responses",
        ge=0.0
    )
    max_response_length: int = Field(
        default=5000,
        description="Maximum response length before penalty",
        ge=0
    )
    structured_content_bonus: float = Field(
        default=10.0,
        description="Bonus for structured content (newlines)",
        ge=0.0
    )
    code_block_bonus: float = Field(
        default=10.0,
        description="Bonus for code blocks",
        ge=0.0
    )
    token_count_weight: float = Field(
        default=0.0,
        description="Weight for output token count"
    )
    cost_weight: float = Field(
        default=0.0,
        description="Weight for cost (negative = prefer lower cost)"
    )
    latency_weight: float = Field(
        default=0.0,
        description="Weight for latency (negative = prefer lower latency)"
    )
    provider_reputation_weight: float = Field(
        default=0.0,
        description="Weight for provider reputation (reserved for future use)"
    )
    custom_scorer: Optional[Callable[[PromptResponse], float]] = Field(
        default=None,
        description="Custom scoring function",
        exclude=True
    )


class ProviderResponse(BaseModel):
    """
    Response from a single provider in consensus.

    Attributes:
        provider_id: Provider identifier
        response: Provider's response
        score: Quality score (computed by consensus engine)

    Example:
        >>> pr = ProviderResponse(
        ...     provider_id="claude",
        ...     response=response,
        ...     score=0.95
        ... )
    """
    provider_id: str = Field(..., description="Provider ID", min_length=1)
    response: PromptResponse = Field(..., description="Provider response")
    score: Optional[float] = Field(
        None,
        description="Quality score (0-120 scale before normalization)",
        ge=0.0,
    )


class ConsensusResult(BaseModel):
    """
    Result of consensus execution.

    Attributes:
        response: Selected/combined response
        agreement: Agreement level (0.0-1.0)
        responses: All provider responses with scores
        total_cost: Total cost across all providers
        total_latency: Total latency in seconds
        strategy_used: Strategy that produced this result
        success: Whether consensus was reached

    Example:
        >>> result = ConsensusResult(
        ...     response=selected_response,
        ...     agreement=0.75,
        ...     responses=[pr1, pr2, pr3],
        ...     total_cost=0.05,
        ...     total_latency=3.2,
        ...     strategy_used=ConsensusStrategy.MAJORITY_VOTE,
        ...     success=True
        ... )
    """
    response: PromptResponse = Field(..., description="Selected response")
    agreement: float = Field(..., description="Agreement level", ge=0.0, le=1.0)
    responses: List[ProviderResponse] = Field(
        ...,
        description="All responses",
        min_length=1
    )
    total_cost: float = Field(..., description="Total cost USD", ge=0.0)
    total_latency: float = Field(..., description="Total latency sec", ge=0.0)
    strategy_used: ConsensusStrategy = Field(..., description="Strategy used")
    success: bool = Field(..., description="Consensus reached")


class ConsensusEngine:
    """
    Consensus engine for multi-provider output combination.

    Executes requests across multiple providers in parallel and
    combines outputs using configurable consensus strategies.

    Supports:
    - Majority vote (most common response)
    - Best-of-N (highest quality)
    - Weighted average (provider-weighted combination)
    - All-agree (strictest consensus)

    Example:
        >>> from adws.providers.registry import get_provider_registry
        >>> registry = get_provider_registry()
        >>> engine = ConsensusEngine(registry)
        >>>
        >>> config = ConsensusConfig(
        ...     strategy=ConsensusStrategy.MAJORITY_VOTE,
        ...     providers=["claude", "openai", "gemini"],
        ...     threshold=0.67
        ... )
        >>>
        >>> result = await engine.get_consensus_async(request, config)
        >>> print(f"Agreement: {result.agreement:.2%}")
        >>> print(f"Output: {result.response.output}")
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        scoring_config: Optional[ConsensusScoringConfig] = None
    ):
        """
        Initialize consensus engine.

        Args:
            registry: Provider registry for provider lookup
            scoring_config: Optional scoring configuration (uses default if None)
        """
        self._registry = registry
        self.scoring_config = scoring_config if scoring_config is not None else ConsensusScoringConfig()

    async def get_consensus_async(
        self,
        request: PromptRequest,
        config: ConsensusConfig
    ) -> ConsensusResult:
        """
        Get consensus from multiple providers (asynchronous).

        Executes request across all configured providers in parallel
        and applies consensus strategy to select/combine outputs.

        Args:
            request: Prompt request to execute
            config: Consensus configuration

        Returns:
            Consensus result with selected response and metadata

        Raises:
            ValueError: If consensus threshold not met
            RuntimeError: If all providers fail

        Example:
            >>> result = await engine.get_consensus_async(request, config)
            >>> if result.success:
            ...     print(f"Consensus: {result.response.output}")
        """
        # Execute across all providers in parallel
        provider_responses = await self._execute_multi_provider_async(
            request,
            config.providers,
            config.timeout
        )

        if not provider_responses:
            raise RuntimeError("All providers failed to respond")

        # Apply consensus strategy
        result = self._apply_consensus(provider_responses, config)

        return result

    def get_consensus(
        self,
        request: PromptRequest,
        config: ConsensusConfig
    ) -> ConsensusResult:
        """
        Get consensus from multiple providers (synchronous).

        Synchronous wrapper around get_consensus_async.

        Args:
            request: Prompt request to execute
            config: Consensus configuration

        Returns:
            Consensus result with selected response and metadata

        Example:
            >>> result = engine.get_consensus(request, config)
        """
        return asyncio.run(self.get_consensus_async(request, config))

    async def _execute_multi_provider_async(
        self,
        request: PromptRequest,
        provider_ids: List[str],
        timeout: float
    ) -> List[ProviderResponse]:
        """
        Execute request across multiple providers in parallel.

        Returns:
            List of provider responses
        """
        tasks = []

        for provider_id in provider_ids:
            provider = self._registry.get(provider_id)
            if not provider:
                continue

            task = self._execute_provider_with_timeout(
                provider,
                provider_id,
                request,
                timeout
            )
            tasks.append(task)

        # Execute all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all provider responses (successful or failed)
        collected_responses: List[ProviderResponse] = []
        for result in results:
            if isinstance(result, ProviderResponse) and result.response.success:
                collected_responses.append(result)

        return collected_responses

    async def _execute_provider_with_timeout(
        self,
        provider: LLMProvider,
        provider_id: str,
        request: PromptRequest,
        timeout: float
    ) -> ProviderResponse:
        """Execute provider request with timeout."""
        try:
            response = await asyncio.wait_for(
                provider.execute_async(request),
                timeout=timeout
            )

            return ProviderResponse(
                provider_id=provider_id,
                response=response
            )

        except asyncio.TimeoutError:
            # Create timeout response
            return ProviderResponse(
                provider_id=provider_id,
                response=PromptResponse(
                    output="",
                    success=False,
                    provider=provider_id,
                    model=request.model,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    cost_usd=0.0,
                    duration_seconds=timeout,
                    timestamp=datetime.now(UTC),
                    retry_code=RetryCode.TIMEOUT_ERROR,
                    error_message=f"Consensus timeout after {timeout}s"
                )
            )

        except Exception as e:
            # Create error response
            return ProviderResponse(
                provider_id=provider_id,
                response=PromptResponse(
                    output="",
                    success=False,
                    provider=provider_id,
                    model=request.model,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    cost_usd=0.0,
                    duration_seconds=0.0,
                    timestamp=datetime.now(UTC),
                    retry_code=RetryCode.EXECUTION_ERROR,
                    error_message=str(e)
                )
            )

    def _apply_consensus(
        self,
        responses: List[ProviderResponse],
        config: ConsensusConfig
    ) -> ConsensusResult:
        """Apply consensus strategy to responses."""
        if config.strategy == ConsensusStrategy.MAJORITY_VOTE:
            return self._majority_vote(responses, config)
        elif config.strategy == ConsensusStrategy.BEST_OF_N:
            return self._best_of_n(responses, config)
        elif config.strategy == ConsensusStrategy.WEIGHTED_AVERAGE:
            return self._weighted_average(responses, config)
        elif config.strategy == ConsensusStrategy.ALL_AGREE:
            return self._all_agree(responses, config)
        else:
            raise ValueError(f"Unknown consensus strategy: {config.strategy}")

    def _majority_vote(
        self,
        responses: List[ProviderResponse],
        config: ConsensusConfig
    ) -> ConsensusResult:
        """
        Majority vote consensus.

        Groups similar responses and selects the most common one.
        Requires threshold to be met.
        """
        total_providers = len(responses)
        if total_providers == 0:
            raise ValueError("No provider responses available for consensus")

        successful_responses = [
            response for response in responses if response.response.success
        ]

        if not successful_responses:
            raise ValueError("Consensus not reached: no successful provider responses")

        # Group similar responses across successful providers
        groups = self._group_similar_responses(
            successful_responses,
            config.similarity_threshold
        )

        if not groups:
            raise ValueError("No valid response groups")

        # Find largest group of successful providers
        largest_group = max(groups, key=len)
        agreement = len(largest_group) / total_providers
        agreement = max(0.0, min(1.0, agreement))

        if agreement < config.threshold:
            raise ValueError(
                f"Consensus not reached: agreement={agreement:.2%} "
                f"< threshold={config.threshold:.2%}"
            )

        # Select first response from largest group
        selected = largest_group[0]

        # Calculate total cost and latency
        total_cost = sum(r.response.cost_usd for r in responses)
        total_latency = sum(r.response.duration_seconds for r in responses)

        return ConsensusResult(
            response=selected.response,
            agreement=agreement,
            responses=responses,
            total_cost=total_cost,
            total_latency=total_latency,
            strategy_used=ConsensusStrategy.MAJORITY_VOTE,
            success=True
        )

    def _best_of_n(
        self,
        responses: List[ProviderResponse],
        config: ConsensusConfig
    ) -> ConsensusResult:
        """
        Best-of-N consensus.

        Scores each response for quality and selects the highest.
        """
        # Score each response
        scored_responses = []
        for pr in responses:
            score = self._score_response(pr.response)
            scored_responses.append(
                ProviderResponse(
                    provider_id=pr.provider_id,
                    response=pr.response,
                    score=score
                )
            )

        # Sort by score (highest first)
        scored_responses.sort(key=lambda x: x.score or 0, reverse=True)

        # Select best
        best = scored_responses[0]
        agreement = ((best.score or 0.0) / 100.0)
        # Clamp agreement to [0.0, 1.0] range to prevent validation errors
        agreement = max(0.0, min(1.0, agreement))

        # Calculate total cost and latency
        total_cost = sum(r.response.cost_usd for r in responses)
        total_latency = sum(r.response.duration_seconds for r in responses)

        return ConsensusResult(
            response=best.response,
            agreement=agreement,
            responses=scored_responses,
            total_cost=total_cost,
            total_latency=total_latency,
            strategy_used=ConsensusStrategy.BEST_OF_N,
            success=True
        )

    def _weighted_average(
        self,
        responses: List[ProviderResponse],
        config: ConsensusConfig
    ) -> ConsensusResult:
        """
        Weighted average consensus.

        For text outputs, this is complex - we use best-of-N instead
        with provider weights influencing the scoring.
        """
        # Apply weights to scores if provided
        if config.provider_weights:
            weights = {
                provider_id: max(0.0, weight)
                for provider_id, weight in config.provider_weights.items()
            }
            max_weight = max(weights.values(), default=1.0)
            if max_weight <= 0:
                max_weight = 1.0

            weighted_candidates = []
            for pr in responses:
                base_score = self._score_response(pr.response)
                provider_response = ProviderResponse(
                    provider_id=pr.provider_id,
                    response=pr.response,
                    score=base_score
                )

                weight = weights.get(pr.provider_id, 1.0)
                normalized_weight = weight / max_weight if max_weight else 1.0
                weighted_value = base_score * normalized_weight
                weighted_candidates.append((weighted_value, provider_response))

            weighted_candidates.sort(key=lambda item: item[0], reverse=True)
            sorted_responses = [candidate[1] for candidate in weighted_candidates]

            if not sorted_responses:
                raise ValueError("No provider responses available for weighted consensus")

            best = sorted_responses[0]
            agreement = (best.score or 0.0) / 100.0
            # Clamp agreement to [0.0, 1.0] range to prevent validation errors
            agreement = max(0.0, min(1.0, agreement))

            # Calculate total cost and latency
            total_cost = sum(r.response.cost_usd for r in responses)
            total_latency = sum(r.response.duration_seconds for r in responses)

            return ConsensusResult(
                response=best.response,
                agreement=agreement,
                responses=sorted_responses,
                total_cost=total_cost,
                total_latency=total_latency,
                strategy_used=ConsensusStrategy.WEIGHTED_AVERAGE,
                success=True
            )
        else:
            # No weights provided, fall back to best-of-N
            return self._best_of_n(responses, config)

    def _all_agree(
        self,
        responses: List[ProviderResponse],
        config: ConsensusConfig
    ) -> ConsensusResult:
        """
        All-agree consensus.

        Requires all providers to produce similar responses.
        Strictest consensus strategy.
        """
        total_providers = len(responses)
        if total_providers == 0:
            raise ValueError("No provider responses available for consensus")

        if any(not pr.response.success for pr in responses):
            raise ValueError("All providers did not agree: at least one provider failed")

        # Group similar responses
        groups = self._group_similar_responses(
            responses,
            config.similarity_threshold
        )

        if len(groups) != 1 or len(groups[0]) != total_providers:
            raise ValueError(
                f"All providers did not agree: {len(groups)} different response groups"
            )

        # All responses are similar - use first
        selected = responses[0]

        # Calculate total cost and latency
        total_cost = sum(r.response.cost_usd for r in responses)
        total_latency = sum(r.response.duration_seconds for r in responses)

        return ConsensusResult(
            response=selected.response,
            agreement=1.0,
            responses=responses,
            total_cost=total_cost,
            total_latency=total_latency,
            strategy_used=ConsensusStrategy.ALL_AGREE,
            success=True
        )

    def _group_similar_responses(
        self,
        responses: List[ProviderResponse],
        threshold: float
    ) -> List[List[ProviderResponse]]:
        """
        Group similar responses using similarity threshold.

        Returns:
            List of groups, where each group contains similar responses
        """
        groups: List[List[ProviderResponse]] = []

        for response in responses:
            # Try to find matching group
            found_group = False

            for group in groups:
                # Compare with first response in group
                if self._are_similar(
                    response.response.output,
                    group[0].response.output,
                    threshold
                ):
                    group.append(response)
                    found_group = True
                    break

            # Create new group if no match
            if not found_group:
                groups.append([response])

        return groups

    def _are_similar(
        self,
        text1: str,
        text2: str,
        threshold: float
    ) -> bool:
        """
        Check if two texts are similar using Levenshtein distance.

        Args:
            text1: First text
            text2: Second text
            threshold: Similarity threshold (0.0-1.0)

        Returns:
            True if similarity >= threshold
        """
        similarity = self._calculate_similarity(text1, text2)
        return similarity >= threshold

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings.

        Uses normalized Levenshtein distance: 1.0 = identical, 0.0 = completely different
        Uses rapidfuzz library when available, falls back to manual implementation.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity score (0.0-1.0)
        """
        if not str1 and not str2:
            return 1.0

        if not str1 or not str2:
            return 0.0

        # Calculate Levenshtein distance
        if RAPIDFUZZ_AVAILABLE:
            # Use rapidfuzz library (faster and battle-tested)
            distance = RapidFuzzLevenshtein.distance(str1, str2)
        else:
            # Fall back to manual implementation
            distance = self._levenshtein_distance_fallback(str1, str2)

        # Normalize: similarity = 1 - (distance / max_length)
        max_length = max(len(str1), len(str2))
        similarity = (max_length - distance) / max_length

        return max(0.0, min(1.0, similarity))

    def _levenshtein_distance_fallback(self, str1: str, str2: str) -> int:
        """
        Calculate Levenshtein distance between two strings (fallback implementation).

        Dynamic programming implementation used when rapidfuzz is not available.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Edit distance (number of operations to transform str1 to str2)
        """
        m, n = len(str1), len(str2)

        # Create DP table
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        # Initialize base cases
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        # Fill DP table
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if str1[i - 1] == str2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(
                        dp[i - 1][j],      # deletion
                        dp[i][j - 1],      # insertion
                        dp[i - 1][j - 1]   # substitution
                    )

        return dp[m][n]

    def _score_response(self, response: PromptResponse) -> float:
        """
        Score response quality using configurable scoring.

        Uses ConsensusScoringConfig to determine scoring weights and penalties.
        Supports custom scoring functions via config.

        Args:
            response: The response to score

        Returns:
            Score (typically 0-120 range with default config, but can vary)
        """
        # Use custom scorer if provided
        if self.scoring_config.custom_scorer is not None:
            return self.scoring_config.custom_scorer(response)

        # Base score
        score = 100.0

        output = response.output
        config = self.scoring_config

        # Penalize very short responses
        if len(output) < config.min_response_length:
            score -= config.short_response_penalty

        # Penalize very long responses (might be verbose)
        if len(output) > config.max_response_length:
            score -= config.long_response_penalty

        # Bonus for structured content
        if '\n' in output:
            score += config.structured_content_bonus

        # Bonus for code blocks (markdown)
        if '```' in output:
            score += config.code_block_bonus

        # Major penalty if not successful
        if not response.success:
            score -= config.success_weight

        # Apply token count weight (if configured)
        if config.token_count_weight != 0.0:
            score += response.output_tokens * config.token_count_weight

        # Apply cost weight (negative = prefer lower cost)
        if config.cost_weight != 0.0:
            score += response.cost_usd * config.cost_weight

        # Apply latency weight (negative = prefer lower latency)
        if config.latency_weight != 0.0:
            score += response.duration_seconds * config.latency_weight

        # NOTE: provider_reputation_weight is not currently applied because
        # PromptResponse does not include reputation metadata. To implement
        # reputation scoring, we would need to:
        # 1. Add reputation tracking infrastructure to ProviderRegistry
        # 2. Include reputation score in PromptResponse or provider metadata
        # 3. Apply the weight here: score += reputation * config.provider_reputation_weight

        return max(0.0, score)
