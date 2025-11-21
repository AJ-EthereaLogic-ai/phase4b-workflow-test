"""
Backend TDD workflow implementation.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from adws.consensus.engine import ConsensusStrategy
from adws.llm import LLMOrchestrator, LLMOrchestratorConfig
from adws.providers import PromptRequest
from adws.workflows.models import WorkflowExecutionResult


class BackendTDDWorkflow:
    """
    Runs backend workflows using multi-provider consensus to maximise quality.
    """

    def __init__(
        self,
        *,
        orchestrator: LLMOrchestrator | None = None,
        config: LLMOrchestratorConfig | None = None,
        working_dir: str = "app/server",
        test_directories: List[str] | None = None,
    ) -> None:
        self.config = config or LLMOrchestratorConfig()
        self.orchestrator = orchestrator or LLMOrchestrator(config=self.config)
        self.working_dir = working_dir
        self.test_directories = test_directories or ["tests"]

    async def execute(
        self,
        requirement: str,
        *,
        adw_id: str,
        metadata: Dict[str, str] | None = None,
        slash_command: str = "/adw_tdd_backend",
        providers: Iterable[str] | None = None,
        consensus_strategy: ConsensusStrategy | None = None,
    ) -> WorkflowExecutionResult:
        """
        Execute a consensus-backed workflow for backend development.
        """

        request = PromptRequest(
            prompt=requirement,
            model=self.config.backend_route.model,
            max_tokens=self.config.backend_route.max_tokens,
            temperature=self.config.backend_route.temperature,
            adw_id=adw_id,
            slash_command=slash_command,
            working_dir=self.working_dir,
            metadata={
                "workflow": "backend_tdd",
                "tdd": True,
                "test_directories": self.test_directories,
                **(metadata or {}),
            },
        )

        provider_list = providers or self.config.consensus_providers

        result = await self.orchestrator.execute(
            request,
            providers=provider_list,
            consensus_strategy=consensus_strategy
            or self.config.consensus_strategy,
        )

        notes = (
            f"Consensus strategy {result.consensus.strategy_used.value}"
            if result.consensus
            else "Single-provider execution"
        )

        return WorkflowExecutionResult(
            adw_id=adw_id,
            workflow_name="backend_tdd",
            success=result.response.success,
            provider=result.selected_provider,
            response_text=result.response.output,
            notes=notes,
            metadata={
                **(metadata or {}),
                "duration_seconds": result.duration_seconds,
                "providers_used": provider_list,
                "agreement": (
                    result.consensus.agreement if result.consensus else 1.0
                ),
            },
        )


__all__ = ["BackendTDDWorkflow"]
