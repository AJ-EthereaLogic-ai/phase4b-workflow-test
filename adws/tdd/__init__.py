"""
ADWS TDD (Test-Driven Development) Module

Provides intelligent test generation, coverage tracking, and quality gates
to support TDD workflows with 90%+ coverage targets.

Components:
- Coverage tracking (Python and TypeScript)
- Quality metrics calculation
- Test generation (Python and Frontend)
- TDD workflow orchestration
"""

from adws.tdd.coverage.unified_coverage_tracker import (
    UnifiedCoverageTracker,
    CoverageReport,
    CoverageFormat,
    FileCoverage,
)
from adws.tdd.quality.quality_calculator import (
    QualityMetricsCalculator,
    QualityMetrics,
)
from adws.tdd.analyzers.react_analyzer import (
    ReactComponentAnalyzer,
    ComponentInfo,
    PropInfo,
    StateInfo,
    HookUsage,
    HookType,
    EventHandler,
)
from adws.tdd.generators.jest_generator import (
    JestTestGenerator,
    GeneratedJestTest,
)
from adws.tdd.generators.playwright_generator import (
    PlaywrightTestGenerator,
    UserFlow,
    FlowStep,
    FlowActionType,
    GeneratedE2ETest,
)
from adws.tdd.generators.python import (
    PythonTestGenerator,
    PythonCodeAnalyzer,
)
from adws.tdd.generators.vitest_generator import (
    VitestTestGenerator,
    GeneratedVitestTest,
    HookInfo,
    UtilityInfo,
)
from adws.tdd.models import (
    PhaseResult,
    PhaseStatus,
    TDDWorkflowState,
    TestScenario,
    TestType,
    TestPriority,
)
from adws.tdd.orchestrator import OrchestratorConfig, RedGreenRefactorOrchestrator

__all__ = [
    # Coverage & Quality
    "UnifiedCoverageTracker",
    "CoverageReport",
    "CoverageFormat",
    "FileCoverage",
    "QualityMetricsCalculator",
    "QualityMetrics",
    # React Analyzer
    "ReactComponentAnalyzer",
    "ComponentInfo",
    "PropInfo",
    "StateInfo",
    "HookUsage",
    "HookType",
    "EventHandler",
    # Test Generators
    "JestTestGenerator",
    "GeneratedJestTest",
    "PythonTestGenerator",
    "PythonCodeAnalyzer",
    "VitestTestGenerator",
    "GeneratedVitestTest",
    "HookInfo",
    "UtilityInfo",
    "PlaywrightTestGenerator",
    "UserFlow",
    "FlowStep",
    "FlowActionType",
    "GeneratedE2ETest",
    # Models / Orchestrator
    "TestScenario",
    "TestType",
    "TestPriority",
    "PhaseResult",
    "PhaseStatus",
    "TDDWorkflowState",
    "OrchestratorConfig",
    "RedGreenRefactorOrchestrator",
]
