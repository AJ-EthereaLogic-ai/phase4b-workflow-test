"""
ADWS v2.0 State Management - Workflow Lifecycle

This module defines the workflow lifecycle states and valid state transitions
for the ADWS state machine. It provides the foundational state transition logic
that validates workflow progressions.

Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence
Phase: Phase 2 - State machine validation (NO new database fields)
"""

from enum import Enum
from typing import Dict, Set


class WorkflowLifecycle(str, Enum):
    """
    Workflow lifecycle states representing workflow execution stages.

    States represent the complete lifecycle from creation through archival,
    including error and recovery states. Each state has specific valid
    transitions defined in VALID_TRANSITIONS.

    State Categories:
        - Initial: CREATED
        - Active: INITIALIZED, RUNNING, PAUSED
        - Terminal: COMPLETED, FAILED, CANCELLED
        - Error: FAILED, STUCK
        - Archive: ARCHIVED
    """

    CREATED = "created"           # Workflow created, not yet initialized
    INITIALIZED = "initialized"   # Setup complete, ready to run
    RUNNING = "running"           # Currently executing
    PAUSED = "paused"            # Execution paused (can resume)
    COMPLETED = "completed"       # Execution successful
    FAILED = "failed"            # Execution failed with error
    CANCELLED = "cancelled"       # Execution cancelled by user
    STUCK = "stuck"              # Execution hung (timeout detected)
    ARCHIVED = "archived"        # Moved to long-term storage


# Complete state transition rules (IMPLEMENT EXACTLY AS SPECIFIED)
VALID_TRANSITIONS: Dict[WorkflowLifecycle, Set[WorkflowLifecycle]] = {
    # From CREATED: Can move to initialization, failure, or cancellation
    WorkflowLifecycle.CREATED: {
        WorkflowLifecycle.INITIALIZED,
        WorkflowLifecycle.FAILED,      # Setup failure
        WorkflowLifecycle.CANCELLED,   # User cancellation
    },

    # From INITIALIZED: Can start running, fail, or be cancelled
    WorkflowLifecycle.INITIALIZED: {
        WorkflowLifecycle.RUNNING,
        WorkflowLifecycle.FAILED,      # Pre-execution failure
        WorkflowLifecycle.CANCELLED,   # User cancellation
    },

    # From RUNNING: Can pause, complete, fail, be cancelled, or get stuck
    WorkflowLifecycle.RUNNING: {
        WorkflowLifecycle.PAUSED,
        WorkflowLifecycle.COMPLETED,
        WorkflowLifecycle.FAILED,
        WorkflowLifecycle.CANCELLED,
        WorkflowLifecycle.STUCK,       # Automatic timeout detection
    },

    # From PAUSED: Can resume, be cancelled, or stuck if paused too long
    WorkflowLifecycle.PAUSED: {
        WorkflowLifecycle.RUNNING,     # Resume execution
        WorkflowLifecycle.CANCELLED,   # User cancellation
        WorkflowLifecycle.STUCK,       # Paused timeout (24 hours)
    },

    # From COMPLETED: Only transition is archival (terminal state)
    WorkflowLifecycle.COMPLETED: {
        WorkflowLifecycle.ARCHIVED,    # Archive for long-term storage
    },

    # From FAILED: Can archive or retry from beginning
    WorkflowLifecycle.FAILED: {
        WorkflowLifecycle.ARCHIVED,    # Archive failed workflow
        WorkflowLifecycle.CREATED,     # Retry from beginning
    },

    # From CANCELLED: Can archive or restart from beginning
    WorkflowLifecycle.CANCELLED: {
        WorkflowLifecycle.ARCHIVED,    # Archive cancelled workflow
        WorkflowLifecycle.CREATED,     # Restart from beginning
    },

    # From STUCK: Can resume manually, fail, or cancel
    WorkflowLifecycle.STUCK: {
        WorkflowLifecycle.RUNNING,     # Manual recovery/unblock
        WorkflowLifecycle.FAILED,      # Give up and fail
        WorkflowLifecycle.CANCELLED,   # Cancel stuck workflow
    },

    # From ARCHIVED: Terminal state - NO transitions (must restore first)
    WorkflowLifecycle.ARCHIVED: set(),
}

# State category definitions for querying and decision logic
TERMINAL_STATES = {
    WorkflowLifecycle.COMPLETED,
    WorkflowLifecycle.FAILED,
    WorkflowLifecycle.CANCELLED,
}  # Terminal states: workflow has ended

ACTIVE_STATES = {
    WorkflowLifecycle.INITIALIZED,
    WorkflowLifecycle.RUNNING,
    WorkflowLifecycle.PAUSED,
}  # Active states: workflow is executing or can execute

CLEANABLE_STATES = TERMINAL_STATES | {WorkflowLifecycle.STUCK}
# States that can be archived/cleaned

ERROR_STATES = {
    WorkflowLifecycle.FAILED,
    WorkflowLifecycle.STUCK,
}  # Error states: workflow encountered issues


def can_transition(
    from_state: WorkflowLifecycle,
    to_state: WorkflowLifecycle
) -> bool:
    """
    Check if state transition is valid.

    Validates whether the workflow can transition from one state to another
    based on the VALID_TRANSITIONS matrix. This is the core validation
    function for the state machine.

    Args:
        from_state: Current workflow state
        to_state: Target workflow state

    Returns:
        True if transition is valid, False otherwise

    Example:
        >>> can_transition(WorkflowLifecycle.CREATED, WorkflowLifecycle.INITIALIZED)
        True
        >>> can_transition(WorkflowLifecycle.COMPLETED, WorkflowLifecycle.RUNNING)
        False
        >>> can_transition(WorkflowLifecycle.ARCHIVED, WorkflowLifecycle.RUNNING)
        False
    """
    return to_state in VALID_TRANSITIONS.get(from_state, set())
