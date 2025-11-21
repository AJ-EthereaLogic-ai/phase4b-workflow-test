"""
ADWS v2.0 State Management - Custom Exceptions

This module defines the custom exception hierarchy for state management errors.
Provides specific exception types for different failure scenarios to enable
precise error handling and meaningful error messages.

Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence
Phase: Phase 2 - State machine validation (NO new database fields)
"""

from typing import Set


class StateManagementError(Exception):
    """
    Base exception for all state management errors.

    Use this for unexpected/unclassified errors that don't fit
    other specific exception types.

    This is the root exception class that all other state management
    exceptions inherit from, allowing for broad exception handling
    when needed.
    """

    pass


class StateTransitionError(StateManagementError):
    """
    Raised when attempting invalid state transition.

    This exception is raised when a workflow attempts to transition
    from one state to another state that is not allowed according to
    the VALID_TRANSITIONS matrix.

    Attributes:
        from_state: The state being transitioned from
        to_state: The state being transitioned to
        allowed_transitions: Set of valid transitions from from_state

    Example:
        >>> raise StateTransitionError(
        ...     message="Cannot transition from completed to running",
        ...     from_state="completed",
        ...     to_state="running",
        ...     allowed_transitions={"archived"}
        ... )
    """

    def __init__(
        self,
        message: str,
        from_state: str,
        to_state: str,
        allowed_transitions: Set[str]
    ):
        """
        Initialize StateTransitionError.

        Args:
            message: Human-readable error message
            from_state: The state being transitioned from
            to_state: The state being transitioned to
            allowed_transitions: Set of valid next states
        """
        super().__init__(message)
        self.from_state = from_state
        self.to_state = to_state
        self.allowed_transitions = allowed_transitions


class PersistenceError(StateManagementError):
    """
    Raised when SQLite write fails (CRITICAL error).

    This is a critical error indicating that workflow state could not be
    persisted to the primary SQLite database. This should trigger rollback
    and retry logic.

    Attributes:
        workflow_id: The workflow that failed to persist
        error_details: Details about the persistence failure

    Example:
        >>> raise PersistenceError(
        ...     message="Failed to save workflow to SQLite",
        ...     workflow_id="workflow-123",
        ...     error_details="Database is locked"
        ... )
    """

    def __init__(self, message: str, workflow_id: str, error_details: str):
        """
        Initialize PersistenceError.

        Args:
            message: Human-readable error message
            workflow_id: The workflow that failed to persist
            error_details: Technical details about the failure
        """
        super().__init__(message)
        self.workflow_id = workflow_id
        self.error_details = error_details


class SyncError(StateManagementError):
    """
    Raised when SQLite/JSON synchronization fails.

    This error indicates that the SQLite and JSON backends are out of sync
    and cannot be reconciled. This is typically a non-critical error but
    should be logged and monitored.

    Attributes:
        workflows_affected: List of workflow IDs that failed to sync
        error_details: Details about the sync failure

    Example:
        >>> raise SyncError(
        ...     message="Failed to sync 3 workflows to JSON",
        ...     workflows_affected=["wf-1", "wf-2", "wf-3"],
        ...     error_details="JSON file is corrupted"
        ... )
    """

    def __init__(
        self,
        message: str,
        workflows_affected: list[str],
        error_details: str
    ):
        """
        Initialize SyncError.

        Args:
            message: Human-readable error message
            workflows_affected: List of workflow IDs that failed to sync
            error_details: Technical details about the failure
        """
        super().__init__(message)
        self.workflows_affected = workflows_affected
        self.error_details = error_details
