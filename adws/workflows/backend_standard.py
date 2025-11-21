"""
Backend Standard workflow implementation.
"""

from __future__ import annotations

from typing import Dict, Iterable

from adws.llm import LLMOrchestrator, LLMOrchestratorConfig
from adws.providers import PromptRequest
from adws.workflows.models import WorkflowExecutionResult


class BackendStandardWorkflow:
    """
    Executes a single-provider backend workflow as described in the
    ADWS project scope.
    """

    def __init__(
        self,
        *,
        orchestrator: LLMOrchestrator | None = None,
        config: LLMOrchestratorConfig | None = None,
        working_dir: str = "app/server",
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
        slash_command: str = "/adw_build",
        providers: Iterable[str] | None = None,
    ) -> WorkflowExecutionResult:
        """
        Execute the workflow for the supplied requirement/specification.
        """

        route = self.config.backend_route
        request = PromptRequest(
            prompt=requirement,
            model=route.model,
            max_tokens=route.max_tokens,
            temperature=route.temperature,
            adw_id=adw_id,
            slash_command=slash_command,
            working_dir=self.working_dir,
            metadata={
                "workflow": "backend_standard",
                **(metadata or {}),
            },
        )

        result = await self.orchestrator.execute(
            request, providers=providers or [route.provider]
        )

        return WorkflowExecutionResult(
            adw_id=adw_id,
            workflow_name="backend_standard",
            success=result.response.success,
            provider=result.selected_provider,
            response_text=result.response.output,
            metadata={
                **(metadata or {}),
                "duration_seconds": result.duration_seconds,
                "total_tokens": result.response.total_tokens,
            },
        )


__all__ = ["BackendStandardWorkflow"]
