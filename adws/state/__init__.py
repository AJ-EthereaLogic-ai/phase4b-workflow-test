"""
ADWS v2.0 State Management

Workflow lifecycle tracking and orchestration state management.

Issue: #1 - StateManager SQLite Schema & Core CRUD Operations
Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence
Issue: #7 - Query API & Cleanup Manager (Phase 3 Fields)
"""

from adws.state.cleanup import CleanupManager, CleanupPolicy, CleanupResult
from adws.state.exceptions import (
    PersistenceError,
    StateManagementError,
    StateTransitionError,
    SyncError,
)
from adws.state.lifecycle import (
    ACTIVE_STATES,
    CLEANABLE_STATES,
    ERROR_STATES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    WorkflowLifecycle,
    can_transition,
)
from adws.state.manager import StateManager
from adws.state.models import (
    IssueClass,
    ModelSet,
    PhaseName,
    PhaseState,
    WorkflowMetrics,
    WorkflowPhase,
    WorkflowState,
    WorkflowType,
)
from adws.state.persistence import (
    HybridPersistence,
    JSONBackend,
    SQLiteBackend,
    SyncResult,
)
from adws.state.query import QueryResult, WorkflowFilter, WorkflowQuery
from adws.state.stuck_detector import StuckDetector
from adws.state.validators import StateTransitionResult, StateTransitionValidator

__all__ = [
    # Core
    "StateManager",
    "WorkflowState",
    "WorkflowType",
    "WorkflowPhase",
    "PhaseName",
    "PhaseState",
    "WorkflowMetrics",
    # Phase 3: Classification enums
    "IssueClass",
    "ModelSet",
    # Lifecycle
    "WorkflowLifecycle",
    "VALID_TRANSITIONS",
    "TERMINAL_STATES",
    "ACTIVE_STATES",
    "CLEANABLE_STATES",
    "ERROR_STATES",
    "can_transition",
    # Validation
    "StateTransitionValidator",
    "StateTransitionResult",
    # Persistence
    "HybridPersistence",
    "SQLiteBackend",
    "JSONBackend",
    "SyncResult",
    # Detection
    "StuckDetector",
    # Phase 3: Query API
    "WorkflowQuery",
    "WorkflowFilter",
    "QueryResult",
    # Phase 3: Cleanup Manager
    "CleanupManager",
    "CleanupPolicy",
    "CleanupResult",
    # Exceptions
    "StateManagementError",
    "StateTransitionError",
    "PersistenceError",
    "SyncError",
]
