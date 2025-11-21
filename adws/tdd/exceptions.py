"""Domain-specific exceptions for the TDD subsystem."""

from __future__ import annotations

from dataclasses import dataclass


class ScenarioExtractionError(RuntimeError):
    """Raised when the scenario extractor cannot parse a specification."""


class TestGenerationError(RuntimeError):
    """Raised when automated test generation fails."""

    __test__ = False


class TDDViolationError(RuntimeError):
    """Raised when a TDD rule (e.g., red phase must fail) is violated."""


class TDDFailureError(RuntimeError):
    """Raised when the green or refactor phases cannot be completed."""


@dataclass
class CommandExecutionError(RuntimeError):
    """Rich error describing subprocess failures within the orchestrator."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    def __str__(self) -> str:  # pragma: no cover - trivial repr
        return (
            f"Command {self.command!r} failed with exit code {self.returncode}. "
            f"stdout={self.stdout!r} stderr={self.stderr!r}"
        )


__all__ = [
    "ScenarioExtractionError",
    "TestGenerationError",
    "TDDViolationError",
    "TDDFailureError",
    "CommandExecutionError",
]
