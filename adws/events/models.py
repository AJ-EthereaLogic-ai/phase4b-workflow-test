"""
ADWEvent data model with complete event type enumeration.

This module defines:
- EventType enum: All 37 possible event types in ADWS v2.0
- EventSeverity enum: 5 severity levels for filtering and display
- ADWEvent model: Universal event model for all ADWS workflows

Design Principles:
- Self-contained: All necessary context in one event
- Correlation: Support event hierarchies via correlation_id/parent_event_id
- Flexible: Generic data dict for event-specific payloads
- Queryable: Indexed fields for efficient filtering
"""

from pydantic import BaseModel, Field, field_serializer, AliasChoices
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from enum import Enum


class EventType(str, Enum):
    """
    All possible event types in ADWS v2.0.

    Total: 37 event types across 9 categories:
    - Workflow lifecycle (10 events)
    - Phase lifecycle (4 events)
    - LLM interactions (4 events)
    - Test execution (4 events)
    - Coverage tracking (3 events)
    - State management (2 events)
    - Resource management (3 events)
    - Cost tracking (3 events)
    - Errors and logging (4 events)
    """

    # Workflow lifecycle (10 events)
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_STEP_STARTED = "workflow_step_started"
    WORKFLOW_STEP_COMPLETED = "workflow_step_completed"
    WORKFLOW_STEP_FAILED = "workflow_step_failed"
    WORKFLOW_CHECKPOINT_CREATED = "workflow_checkpoint_created"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_RESUMED = "workflow_resumed"

    # Phase lifecycle (4 events)
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_FAILED = "phase_failed"
    PHASE_PROGRESS = "phase_progress"  # Progress updates during long phases

    # LLM interactions (4 events)
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"
    LLM_RETRY = "llm_retry"

    # Test execution (4 events)
    TEST_STARTED = "test_started"
    TEST_COMPLETED = "test_completed"
    TEST_FAILED = "test_failed"
    TEST_SUITE_COMPLETED = "test_suite_completed"

    # Coverage tracking (3 events)
    COVERAGE_UPDATED = "coverage_updated"
    COVERAGE_THRESHOLD_MET = "coverage_threshold_met"
    COVERAGE_THRESHOLD_FAILED = "coverage_threshold_failed"

    # State management (2 events)
    STATE_UPDATED = "state_updated"
    STATE_TRANSITION = "state_transition"

    # Resource management (3 events)
    WORKTREE_CREATED = "worktree_created"
    WORKTREE_CLEANED = "worktree_cleaned"
    PORT_ALLOCATED = "port_allocated"

    # Cost tracking (3 events)
    COST_UPDATED = "cost_updated"
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Errors and logging (4 events)
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class EventSeverity(str, Enum):
    """Event severity levels for filtering and display."""
    DEBUG = "debug"      # Detailed debugging information
    INFO = "info"        # General informational events
    WARNING = "warning"  # Warning conditions (non-fatal)
    ERROR = "error"      # Error conditions (recoverable)
    CRITICAL = "critical"  # Critical errors (workflow-stopping)


class ADWEvent(BaseModel):
    """
    Universal event model for ADWS workflows.

    All events published in the system use this standardized format.
    Events are serialized to JSONL (one event per line) for persistence.

    Design Principles:
    - Self-contained: All necessary context in one event
    - Correlation: Support event hierarchies via correlation_id/parent_event_id
    - Flexible: Generic data dict for event-specific payloads
    - Queryable: Indexed fields for efficient filtering

    Examples:
        # Workflow started event
        event = ADWEvent(
            adw_id="wf-2025-001",
            event_type=EventType.WORKFLOW_STARTED,
            source="adw_plan_iso",
            severity=EventSeverity.INFO,
            message="Starting plan workflow for issue #42",
            data={
                "workflow": "adw_plan_iso",
                "issue_number": 42,
                "branch_name": "feature-xyz"
            }
        )

        # LLM response event with cost tracking
        event = ADWEvent(
            adw_id="wf-2025-001",
            event_type=EventType.LLM_RESPONSE,
            source="agent",
            severity=EventSeverity.INFO,
            message="Received response from Claude Sonnet",
            data={
                "provider": "claude",
                "model": "claude-sonnet-4",
                "success": True,
                "input_tokens": 1500,
                "output_tokens": 3000,
                "cost_usd": 0.15,
                "duration_seconds": 12.5
            }
        )
    """

    # Core identification (required)
    adw_id: str = Field(
        ...,
        description="Workflow identifier (e.g., 'wf-2025-001')",
        # Accept both 'adw_id' and 'workflow_id' on input; serialize as 'workflow_id'
        validation_alias=AliasChoices("adw_id", "workflow_id"),
        serialization_alias="workflow_id",
    )
    event_type: EventType = Field(
        ...,
        description="Type of event (from EventType enum)"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event timestamp (ISO 8601, UTC)"
    )

    # Event metadata (required)
    source: str = Field(
        ...,
        description="Component that emitted event (e.g., 'adw_plan_iso', 'agent', 'test')"
    )
    severity: EventSeverity = Field(
        default=EventSeverity.INFO,
        description="Event severity level"
    )

    # Event data (flexible payload)
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (see event data schemas in spec)"
    )

    # Correlation (for tracing and hierarchies)
    correlation_id: Optional[str] = Field(
        None,
        description="Correlation ID for related events (e.g., all events in one LLM call)"
    )
    parent_event_id: Optional[str] = Field(
        None,
        description="Parent event ID for hierarchical events (e.g., phase events under workflow)"
    )

    # Optional human-readable message
    message: Optional[str] = Field(
        None,
        description="Human-readable event message for logs/TUI display"
    )

    model_config = {
        "use_enum_values": True,
    }

    @field_serializer("timestamp")
    def _serialize_timestamp(self, value: datetime):
        """Serialize datetime to ISO 8601 string for JSONL output."""
        return value.isoformat()

    def to_jsonl(self) -> str:
        """
        Serialize to JSONL format (one event per line).

        Returns:
            JSON string representing event (no newline)

        Example:
            >>> event = ADWEvent(...)
            >>> line = event.to_jsonl()
            >>> print(line)
            {"adw_id":"wf-001","event_type":"workflow_started",...}
        """
        # Use aliases so 'workflow_id' appears in serialized output
        return self.model_dump_json(by_alias=True)

    @classmethod
    def from_jsonl(cls, line: str) -> "ADWEvent":
        """
        Deserialize from JSONL.

        Args:
            line: JSON string (single line from JSONL file)

        Returns:
            ADWEvent instance

        Raises:
            ValidationError: If JSON is invalid or missing required fields

        Example:
            >>> line = '{"adw_id":"wf-001","event_type":"workflow_started",...}'
            >>> event = ADWEvent.from_jsonl(line)
        """
        return cls.model_validate_json(line)

    # Backward/forward compatibility convenience: expose workflow_id property
    @property
    def workflow_id(self) -> str:
        """Canonical accessor for the workflow identifier."""
        return self.adw_id
