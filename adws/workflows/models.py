"""
Shared workflow data structures for ADWS workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class WorkflowExecutionResult:
    """
    Standard result container for workflow executions.

    The structure is intentionally lightweight so it can be serialized
    to JSON (by calling ``dataclasses.asdict``) or attached to workflow
    events emitted via :class:`WorkflowEventEmitter`.
    """

    adw_id: str
    workflow_name: str
    success: bool
    provider: str
    response_text: str
    artifacts: List[str] = field(default_factory=list)
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


__all__ = ["WorkflowExecutionResult"]
