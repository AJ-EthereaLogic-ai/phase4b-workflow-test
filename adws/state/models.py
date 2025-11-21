"""
ADWS v2.0 State Management - Data Models

This module defines the Pydantic models for workflow state management.
These models provide type-safe data structures with validation for workflow
lifecycle tracking.

Issue: #1 - StateManager SQLite Schema & Core CRUD Operations
Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# Import WorkflowLifecycle from lifecycle module (Phase 2)
from adws.state.lifecycle import WorkflowLifecycle


class WorkflowType(str, Enum):
    """Types of workflows supported by ADWS."""

    STANDARD = "standard"
    TDD = "tdd"
    PLAN_ONLY = "plan-only"
    TEST_ONLY = "test-only"
    REVIEW_ONLY = "review-only"


class IssueClass(str, Enum):
    """Issue classification for filtering and analytics (Phase 3)."""

    FEATURE = "feature"
    BUG = "bug"
    TEST = "test"
    REFACTOR = "refactor"
    DOCS = "docs"
    CHORE = "chore"


class ModelSet(str, Enum):
    """Model selection for workflow execution (Phase 3)."""

    BASE = "base"  # Default: Claude Haiku + GPT-4 Turbo
    FAST = "fast"  # Claude Haiku only
    POWERFUL = "powerful"  # Claude Sonnet + GPT-4 Turbo


class PhaseState(str, Enum):
    """Phase execution states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PhaseName(str, Enum):
    """Standard phase names in ADWS workflows."""

    PLAN = "plan"
    BUILD = "build"
    TEST = "test"
    REVIEW = "review"
    DEPLOY = "deploy"
    GENERATE_TESTS = "generate_tests"
    VERIFY_RED = "verify_red"
    VERIFY_GREEN = "verify_green"
    REFACTOR = "refactor"


class WorkflowPhase(BaseModel):
    """
    Model representing a single phase execution within a workflow.

    Tracks phase execution state, timing, and resource usage.
    """

    id: Optional[int] = Field(default=None, description="Database ID (auto-generated)")
    workflow_id: str = Field(..., description="Parent workflow identifier")
    phase_name: PhaseName = Field(..., description="Name of the phase")
    phase_index: int = Field(..., description="Order within workflow", ge=0)
    state: PhaseState = Field(default=PhaseState.PENDING, description="Current phase state")
    started_at: Optional[datetime] = Field(default=None, description="Phase start time")
    completed_at: Optional[datetime] = Field(default=None, description="Phase completion time")
    duration_seconds: Optional[float] = Field(default=None, description="Execution duration", ge=0)
    exit_code: Optional[int] = Field(default=None, description="Process exit code")
    error_message: Optional[str] = Field(default=None, description="Error details if failed")
    attempt_number: int = Field(default=1, description="Retry attempt number", ge=1)
    max_attempts: int = Field(default=3, description="Maximum retry attempts", ge=1)
    llm_requests: int = Field(default=0, description="Number of LLM API calls", ge=0)
    llm_tokens_input: int = Field(default=0, description="Input tokens used", ge=0)
    llm_tokens_output: int = Field(default=0, description="Output tokens used", ge=0)
    cost_usd: float = Field(default=0.0, description="Phase cost in USD", ge=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp"
    )

    model_config = {"from_attributes": True, "validate_assignment": True}


class WorkflowState(BaseModel):
    """
    Complete workflow state model including all Phase 1 and Phase 3 fields.

    Total: 25 fields (20 Phase 1 + 5 Phase 3)

    This is the primary data model for workflow orchestration state,
    containing all essential information needed to track and manage a workflow.

    Phase 1 includes critical integration fields for tac-7 compatibility:
    - issue_number: GitHub issue tracking
    - branch_name: Git branch context
    - base_branch: Target branch for PR
    - worktree_path: Git worktree location

    Phase 3 adds query and resource management fields:
    - backend_port: Backend dev server port allocation
    - frontend_port: Frontend dev server port allocation
    - issue_class: Issue classification for filtering
    - model_set: Model selection for execution
    - phase_count: Number of phases executed
    """

    # ========== PHASE 1: IDENTITY & CORE (4 fields) ==========
    workflow_id: str = Field(..., description="Unique workflow identifier (PRIMARY KEY)")
    workflow_name: str = Field(..., description="Human-readable workflow name")
    workflow_type: WorkflowType = Field(
        default=WorkflowType.STANDARD, description="Workflow type classification"
    )
    issue_number: Optional[int] = Field(
        default=None, description="GitHub issue number (tac-7 integration)", ge=1
    )

    # ========== PHASE 1: LIFECYCLE (1 field) ==========
    state: WorkflowLifecycle = Field(
        default=WorkflowLifecycle.CREATED, description="Lifecycle state"
    )

    # ========== PHASE 1: TIMESTAMPS (5 fields) ==========
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Workflow creation timestamp"
    )
    started_at: Optional[datetime] = Field(default=None, description="Execution start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Execution completion timestamp")
    archived_at: Optional[datetime] = Field(default=None, description="Archive timestamp")
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Most recent activity timestamp"
    )

    # ========== PHASE 1: GIT CONTEXT (3 fields) ==========
    branch_name: Optional[str] = Field(
        default=None, description="Git branch name (tac-7 integration)"
    )
    base_branch: str = Field(
        default="main", description="Base branch for PR merging"
    )
    worktree_path: Optional[str] = Field(
        default=None, description="Git worktree path (tac-7 integration)"
    )

    # ========== PHASE 1: METADATA (2 fields) ==========
    tags: list[str] = Field(default_factory=list, description="Workflow tags for categorization")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible metadata dictionary")

    # ========== PHASE 1: RESULTS (2 fields) ==========
    exit_code: Optional[int] = Field(default=None, description="Process exit code")
    error_message: Optional[str] = Field(default=None, description="Error details if execution failed")

    # ========== PHASE 1: STATISTICS (3 fields) ==========
    retry_count: int = Field(default=0, description="Number of retry attempts", ge=0)
    cost_usd: float = Field(default=0.0, description="Total workflow cost in USD", ge=0)
    total_tokens: int = Field(default=0, description="Total tokens used in workflow", ge=0)

    # ========== PHASE 3: RESOURCE ALLOCATION (2 fields) ==========
    backend_port: Optional[int] = Field(
        default=None,
        description="Backend dev server port (9100-9199 range)",
        ge=9100,
        le=9199
    )
    frontend_port: Optional[int] = Field(
        default=None,
        description="Frontend dev server port (9200-9299 range)",
        ge=9200,
        le=9299
    )

    # ========== PHASE 3: CLASSIFICATION (1 field) ==========
    issue_class: Optional[IssueClass] = Field(
        default=None,
        description="Issue type: feature, bug, test, refactor, docs, chore"
    )

    # ========== PHASE 3: MODEL CONFIGURATION (1 field) ==========
    model_set: ModelSet = Field(
        default=ModelSet.BASE,
        description="Model selection: base, fast, powerful"
    )

    # ========== PHASE 3: ADVANCED STATISTICS (1 field) ==========
    phase_count: int = Field(
        default=0, description="Number of phases executed", ge=0
    )

    model_config = {"from_attributes": True, "validate_assignment": True}

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: Any) -> list[str]:
        """
        Parse tags from JSON string or list.

        Supports both JSON string format (from SQLite) and Python list.
        """
        if v is None:
            return []
        if isinstance(v, str):
            # Parse JSON string from database
            import json

            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, ValueError):
                return []
        if isinstance(v, list):
            return v
        return []

    @field_validator("metadata", mode="before")
    @classmethod
    def parse_metadata(cls, v: Any) -> dict[str, Any]:
        """
        Parse metadata from JSON string or dict.

        Supports both JSON string format (from SQLite) and Python dict.
        """
        if v is None:
            return {}
        if isinstance(v, str):
            # Parse JSON string from database
            import json

            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        if isinstance(v, dict):
            return v
        return {}

    @field_validator("created_at", "started_at", "completed_at", "archived_at", "last_activity_at", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> Optional[datetime]:
        """
        Parse datetime from ISO string or datetime object.

        Supports both ISO 8601 string format (from SQLite) and Python datetime.
        """
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                # Parse ISO 8601 format from SQLite
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None
        return None


class WorkflowMetrics(BaseModel):
    """
    Aggregated workflow metrics for analytics.

    Used for tracking performance and success rates over time.
    """

    id: Optional[int] = Field(default=None, description="Database ID")
    metric_date: str = Field(..., description="Metrics date (YYYY-MM-DD)")
    workflow_type: WorkflowType = Field(..., description="Workflow type")
    total_workflows: int = Field(default=0, description="Total workflows", ge=0)
    completed_workflows: int = Field(default=0, description="Completed count", ge=0)
    failed_workflows: int = Field(default=0, description="Failed count", ge=0)
    cancelled_workflows: int = Field(default=0, description="Cancelled count", ge=0)
    avg_duration_seconds: Optional[float] = Field(default=None, description="Average duration", ge=0)
    min_duration_seconds: Optional[float] = Field(default=None, description="Minimum duration", ge=0)
    max_duration_seconds: Optional[float] = Field(default=None, description="Maximum duration", ge=0)
    total_cost_usd: float = Field(default=0.0, description="Total cost", ge=0)
    avg_cost_usd: float = Field(default=0.0, description="Average cost", ge=0)
    success_rate: Optional[float] = Field(
        default=None, description="Success rate (0-1)", ge=0, le=1
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"from_attributes": True, "validate_assignment": True}
