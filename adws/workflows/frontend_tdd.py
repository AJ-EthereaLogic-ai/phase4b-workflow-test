"""
Frontend TDD workflow implementation.
"""

from __future__ import annotations

from typing import Dict, Iterable

from adws.consensus.engine import ConsensusStrategy
from adws.llm import LLMOrchestrator, LLMOrchestratorConfig
from adws.providers import PromptRequest
from adws.workflows.models import WorkflowExecutionResult


class FrontendTDDWorkflow:
    """
    Multi-provider workflow that focuses on component tests first.
    """

    def __init__(
        self,
        *,
        orchestrator: LLMOrchestrator | None = None,
        config: LLMOrchestratorConfig | None = None,
        working_dir: str = "app/client",
    ) -> None:
        self.config = config or LLMOrchestratorConfig()
        self.orchestrator = orchestrator or LLMOrchestrator(config=self.config)
        self.working_dir = working_dir

    async def execute(
        self,
        requirement: str,
        *,
        adw_id: str,
        metadata: Dict[str, str] | None = None,
        slash_command: str = "/adw_tdd_frontend",
        providers: Iterable[str] | None = None,
        consensus_strategy: ConsensusStrategy | None = None,
    ) -> WorkflowExecutionResult:
        """
        Execute the workflow for a given frontend requirement specification.
        """

        request = PromptRequest(
            prompt=requirement,
            model=self.config.frontend_route.model,
            max_tokens=self.config.frontend_route.max_tokens,
            temperature=self.config.frontend_route.temperature,
            adw_id=adw_id,
            slash_command=slash_command,
            working_dir=self.working_dir,
            metadata={
                "workflow": "frontend_tdd",
                "tdd": True,
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

        return WorkflowExecutionResult(
            adw_id=adw_id,
            workflow_name="frontend_tdd",
            success=result.response.success,
            provider=result.selected_provider,
            response_text=result.response.output,
            metadata={
                **(metadata or {}),
                "duration_seconds": result.duration_seconds,
                "providers_used": provider_list,
            },
            notes=(
                f"Consensus agreement {result.consensus.agreement:.2%}"
                if result.consensus
                else "Single-provider execution"
            ),
        )


__all__ = ["FrontendTDDWorkflow"]
