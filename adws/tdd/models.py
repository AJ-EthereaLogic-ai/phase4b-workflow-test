"""Shared data models for the TDD subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Sequence
from uuid import uuid4


class TestType(str, Enum):
    """Supported scenario classifications."""

    __test__ = False

    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"


class TestPriority(str, Enum):
    """Priority levels for generated scenarios."""

    __test__ = False

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestFramework(str, Enum):
    """Supported testing frameworks."""

    PYTEST = "pytest"
    JEST = "jest"
    VITEST = "vitest"
    PLAYWRIGHT = "playwright"


@dataclass
class TestScenario:
    """Structured representation of a test requirement."""

    __test__: ClassVar[bool] = False

    name: str
    description: str
    test_type: TestType = TestType.UNIT
    priority: TestPriority = TestPriority.MEDIUM
    inputs: List[str] = field(default_factory=list)
    expected_outputs: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    error_conditions: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    source_file: Optional[Path] = None
    line_number: Optional[int] = None
    scenario_id: str = field(default_factory=lambda: str(uuid4()))

    def summary(self) -> str:
        """Short human friendly representation used in reports."""

        return f"[{self.priority.value.upper()}] {self.name} ({self.test_type.value})"


@dataclass
class ParameterInfo:
    """Metadata about a python function parameter."""

    name: str
    annotation: Optional[str] = None
    default: Optional[str] = None
    kind: str = "positional"


@dataclass
class FunctionInfo:
    """Description of a function or method to be tested."""

    name: str
    parameters: List[ParameterInfo] = field(default_factory=list)
    return_annotation: Optional[str] = None
    docstring: Optional[str] = None
    is_async: bool = False
    parent_class: Optional[str] = None


@dataclass
class ClassInfo:
    """Description of a class containing methods under test."""

    name: str
    methods: List[FunctionInfo] = field(default_factory=list)
    docstring: Optional[str] = None


@dataclass
class ModuleAnalysis:
    """Aggregated AST analysis for a python module."""

    module_path: Path
    import_path: str
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)

    @property
    def total_entities(self) -> int:
        """Number of top-level targets covered by generation."""

        method_count = sum(len(cls.methods) for cls in self.classes)
        return len(self.functions) + method_count


@dataclass
class GeneratedPythonTest:
    """Metadata about generated pytest assets."""

    test_file_path: str
    test_code: str
    test_count: int
    coverage_estimate: float
    quality_score: float
    scenarios: Sequence[str] = field(default_factory=list)


class WorkflowPhase(str, Enum):
    """Workflow phases for the orchestrator."""

    PLAN = "plan"
    GENERATE = "generate_tests"
    VERIFY_RED = "verify_red"
    BUILD = "build"
    VERIFY_GREEN = "verify_green"
    REFACTOR = "refactor"
    REVIEW = "review"


class PhaseStatus(str, Enum):
    """Status for a workflow phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PhaseResult:
    """Recorded outcome for a workflow phase."""

    phase: WorkflowPhase
    status: PhaseStatus
    details: str = ""
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None

    def mark_completed(self, details: str = "") -> None:
        self.status = PhaseStatus.COMPLETED
        self.details = details or self.details
        self.completed_at = _utcnow()

    def mark_failed(self, details: str) -> None:
        self.status = PhaseStatus.FAILED
        self.details = details
        self.completed_at = _utcnow()

    @property
    def result_summary(self) -> str:
        """Short summary for display in reports.

        Returns the details string when present; otherwise a formatted
        fallback containing phase and status.
        """
        if self.details:
            return self.details
        return f"{self.phase.value}: {self.status.value}"


@dataclass
class TDDWorkflowState:
    """Aggregated workflow execution state."""

    phase_results: List[PhaseResult] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    def record_phase(
        self,
        phase: WorkflowPhase,
        status: PhaseStatus,
        details: str = "",
    ) -> PhaseResult:
        """Append or update a phase entry."""

        result = PhaseResult(phase=phase, status=status, details=details)
        self.phase_results.append(result)
        return result

    def latest(self, phase: WorkflowPhase) -> Optional[PhaseResult]:
        """Return the most recent record for a phase."""

        for result in reversed(self.phase_results):
            if result.phase == phase:
                return result
        return None


__all__ = [
    "ClassInfo",
    "FunctionInfo",
    "GeneratedPythonTest",
    "ModuleAnalysis",
    "ParameterInfo",
    "PhaseResult",
    "PhaseStatus",
    "TDDWorkflowState",
    "TestFramework",
    "TestPriority",
    "TestScenario",
    "TestType",
    "WorkflowPhase",
]
