"""
Frontend standard workflow implementation.
"""

from __future__ import annotations

from typing import Dict, Iterable

from adws.llm import LLMOrchestrator, LLMOrchestratorConfig
from adws.providers import PromptRequest
from adws.workflows.models import WorkflowExecutionResult


class FrontendStandardWorkflow:
    """
    Executes frontend workflows using a single preferred provider/model.
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
        slash_command: str = "/adw_frontend",
        providers: Iterable[str] | None = None,
    ) -> WorkflowExecutionResult:
        """
        Execute the frontend workflow for a given requirement.
        """

        route = self.config.frontend_route
        request = PromptRequest(
            prompt=requirement,
            model=route.model,
            max_tokens=route.max_tokens,
            temperature=route.temperature,
            adw_id=adw_id,
            slash_command=slash_command,
            working_dir=self.working_dir,
            metadata={
                "workflow": "frontend_standard",
                **(metadata or {}),
            },
        )

        result = await self.orchestrator.execute(
            request, providers=providers or [route.provider]
        )

        return WorkflowExecutionResult(
            adw_id=adw_id,
            workflow_name="frontend_standard",
            success=result.response.success,
            provider=result.selected_provider,
            response_text=result.response.output,
            metadata={
                **(metadata or {}),
                "duration_seconds": result.duration_seconds,
                "total_tokens": result.response.total_tokens,
            },
        )


__all__ = ["FrontendStandardWorkflow"]
