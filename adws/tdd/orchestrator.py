"""Red-Green-Refactor orchestration utilities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CompletedProcess
from typing import List, Sequence

from adws.tdd.coverage.unified_coverage_tracker import (
    CoverageReport,
    UnifiedCoverageTracker,
)
from adws.tdd.exceptions import (
    CommandExecutionError,
    TDDFailureError,
    TDDViolationError,
)
from adws.tdd.extractor import TestScenarioExtractor
from adws.tdd.generators.python import PythonTestGenerator
from adws.tdd.models import (
    TDDWorkflowState,
    TestScenario,
    TestType,
    WorkflowPhase,
    PhaseStatus,
)


class CommandRunner:
    """Abstraction for running shell commands (allows test doubles)."""

    async def run(
        self, command: Sequence[str], *, cwd: Path | None = None
    ) -> CompletedProcess[str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._blocking_run,
            list(command),
            cwd,
        )

    def _blocking_run(
        self, command: List[str], cwd: Path | None
    ) -> CompletedProcess[str]:
        from subprocess import run

        # Security exception: check=True intentionally omitted to support TDD Red phase
        # where test failures (non-zero exit) are EXPECTED and REQUIRED for workflow
        # validation. Return codes are explicitly checked by callers (_verify_red at
        # line 174 and _verify_green at line 190) to distinguish Red (must fail) from
        # Green (must pass) states.
        return run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=False,  # Security: prevent command injection
        )  # nosec B603 - shell=False prevents injection, return code checked by caller


@dataclass
class OrchestratorConfig:
    """User-configurable knobs for the workflow."""

    spec_path: Path
    target_module: Path
    project_root: Path = Path(".")
    output_directory: Path = Path("tests") / "unit"
    allowed_test_types: Sequence[TestType] = field(
        default_factory=lambda: [TestType.UNIT, TestType.INTEGRATION]
    )
    write_tests: bool = True
    expect_red_failure: bool = True
    skip_green_phase: bool = False
    test_command: Sequence[str] = field(default_factory=lambda: ["pytest"])
    run_coverage: bool = False
    coverage_source_path: Path = Path("adws")
    coverage_tests_path: Path = Path("tests")


class RedGreenRefactorOrchestrator:
    """Co-ordinates the Phase 5B workflow end-to-end."""

    def __init__(
        self,
        *,
        extractor: TestScenarioExtractor | None = None,
        python_generator: PythonTestGenerator | None = None,
        command_runner: CommandRunner | None = None,
        coverage_tracker: UnifiedCoverageTracker | None = None,
    ) -> None:
        self._extractor = extractor or TestScenarioExtractor()
        self._python_generator = python_generator or PythonTestGenerator()
        self._command_runner = command_runner or CommandRunner()
        self._coverage_tracker = coverage_tracker

    async def run(self, config: OrchestratorConfig) -> TDDWorkflowState:
        state = TDDWorkflowState()

        scenarios = self._plan_phase(state, config)
        generation = self._generate_phase(state, config, scenarios)
        await self._verify_red(state, config)

        state.record_phase(
            WorkflowPhase.BUILD, PhaseStatus.COMPLETED, "Manual implementation pending"
        )

        if not config.skip_green_phase:
            await self._verify_green(state, config)

        if config.run_coverage and self._coverage_tracker:
            await self._collect_coverage(state, config)

        state.record_phase(
            WorkflowPhase.REFACTOR,
            PhaseStatus.COMPLETED,
            "Refactor suggestions pending",
        )
        state.record_phase(
            WorkflowPhase.REVIEW, PhaseStatus.COMPLETED, "Ready for review"
        )

        state.metadata.update(
            {
                "generated_test_file": generation.test_file_path,
                "test_count": str(generation.test_count),
            }
        )

        return state

    # Phase implementations ----------------------------------------------------

    def _plan_phase(
        self,
        state: TDDWorkflowState,
        config: OrchestratorConfig,
    ) -> List[TestScenario]:
        phase = state.record_phase(WorkflowPhase.PLAN, PhaseStatus.IN_PROGRESS)
        scenarios = self._extractor.extract_scenarios(
            config.spec_path,
            config.allowed_test_types,
        )
        phase.mark_completed(f"Extracted {len(scenarios)} scenarios")
        return scenarios

    def _generate_phase(
        self,
        state: TDDWorkflowState,
        config: OrchestratorConfig,
        scenarios: Sequence[TestScenario],
    ):
        phase = state.record_phase(
            WorkflowPhase.GENERATE,
            PhaseStatus.IN_PROGRESS,
        )
        result = self._python_generator.generate_tests(
            module_path=config.target_module,
            scenarios=scenarios,
            output_path=config.output_directory
            / f"test_{Path(config.target_module).stem}.py",
            write_to_file=config.write_tests,
        )
        phase.mark_completed(
            f"Generated {result.test_count} tests @ {result.test_file_path}"
        )
        return result

    async def _verify_red(
        self,
        state: TDDWorkflowState,
        config: OrchestratorConfig,
    ) -> None:
        phase = state.record_phase(
            WorkflowPhase.VERIFY_RED,
            PhaseStatus.IN_PROGRESS,
        )
        if not config.expect_red_failure:
            phase.mark_completed("Skipping red phase (not enforced)")
            return

        result = await self._run_tests(config)
        if result.returncode == 0:
            phase.mark_failed("Tests passed unexpectedly during Red phase")
            raise TDDViolationError("Red phase must fail before implementation")

        phase.mark_completed("Red phase verified: tests failing as expected")

    async def _verify_green(
        self,
        state: TDDWorkflowState,
        config: OrchestratorConfig,
    ) -> None:
        phase = state.record_phase(
            WorkflowPhase.VERIFY_GREEN,
            PhaseStatus.IN_PROGRESS,
        )
        result = await self._run_tests(config)
        if result.returncode != 0:
            phase.mark_failed("Tests failed during Green phase")
            raise TDDFailureError("Green phase must pass")
        phase.mark_completed("Green phase verified: tests passing")

    async def _collect_coverage(
        self,
        state: TDDWorkflowState,
        config: OrchestratorConfig,
    ) -> CoverageReport | None:
        if not self._coverage_tracker:
            return None

        report = await self._coverage_tracker.track_python_coverage(
            test_path=config.coverage_tests_path,
            source_path=config.coverage_source_path,
        )
        state.metadata["coverage_percentage"] = f"{report.coverage_percentage:.2f}"
        return report

    async def _run_tests(
        self,
        config: OrchestratorConfig,
    ) -> CompletedProcess[str]:
        try:
            result = await self._command_runner.run(
                config.test_command,
                cwd=config.project_root,
            )
        except FileNotFoundError as exc:  # pragma: no cover - environment guard
            raise CommandExecutionError(
                command=list(config.test_command),
                returncode=-1,
                stdout="",
                stderr=str(exc),
            ) from exc

        return result


__all__ = ["CommandRunner", "OrchestratorConfig", "RedGreenRefactorOrchestrator"]
