"""
ADWS v2.0 State Management - State Transition Validator

This module validates workflow state transitions against defined rules.
Prevents invalid state transitions and logs all attempts for audit trail.

Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence
Phase: Phase 2 - State machine validation (NO new database fields)
"""

import logging
from dataclasses import dataclass
from typing import Optional, Set

from adws.state.lifecycle import VALID_TRANSITIONS, WorkflowLifecycle


@dataclass
class StateTransitionResult:
    """
    Result of state transition validation.

    Contains validation outcome and context for error handling.

    Attributes:
        valid: True if transition is allowed
        error_message: Error message if invalid (None if valid)
        from_state: Starting state of the transition
        to_state: Target state of the transition
        allowed_transitions: Set of all valid next states from from_state
    """

    valid: bool
    error_message: Optional[str]
    from_state: WorkflowLifecycle
    to_state: WorkflowLifecycle
    allowed_transitions: Set[WorkflowLifecycle]


class StateTransitionValidator:
    """
    Validates workflow state transitions against defined rules.

    This validator ensures that all workflow state changes follow the
    valid transition paths defined in the VALID_TRANSITIONS matrix.
    It logs all validation attempts for audit purposes.

    The validator is stateless and can be reused across multiple workflows.

    Example:
        >>> validator = StateTransitionValidator()
        >>> result = validator.validate_transition(
        ...     WorkflowLifecycle.RUNNING,
        ...     WorkflowLifecycle.COMPLETED,
        ...     "workflow-123"
        ... )
        >>> if result.valid:
        ...     # Proceed with state transition
        ...     pass
        ... else:
        ...     # Reject transition
        ...     print(result.error_message)
    """

    def __init__(self) -> None:
        """
        Initialize StateTransitionValidator.

        Sets up logging for transition validation tracking.
        """
        self.logger = logging.getLogger(__name__)

    def validate_transition(
        self,
        from_state: WorkflowLifecycle,
        to_state: WorkflowLifecycle,
        workflow_id: str
    ) -> StateTransitionResult:
        """
        Validate state transition.

        Checks if the requested state transition is valid according to
        VALID_TRANSITIONS matrix. Logs all validation attempts with
        workflow context for audit trail.

        Args:
            from_state: Current workflow state
            to_state: Desired next state
            workflow_id: Workflow identifier (for logging)

        Returns:
            StateTransitionResult with validation outcome and context

        Example:
            >>> validator = StateTransitionValidator()
            >>> result = validator.validate_transition(
            ...     WorkflowLifecycle.RUNNING,
            ...     WorkflowLifecycle.PAUSED,
            ...     "workflow-123"
            ... )
            >>> assert result.valid is True
            >>>
            >>> result = validator.validate_transition(
            ...     WorkflowLifecycle.COMPLETED,
            ...     WorkflowLifecycle.RUNNING,
            ...     "workflow-456"
            ... )
            >>> assert result.valid is False
            >>> print(result.error_message)
            Invalid state transition from completed to running...
        """
        allowed = VALID_TRANSITIONS.get(from_state, set())
        is_valid = to_state in allowed

        self.logger.info(
            f"State transition validation: {workflow_id} "
            f"{from_state.value} → {to_state.value}: "
            f"{'VALID' if is_valid else 'INVALID'}"
        )

        if not is_valid:
            error_msg = (
                f"Invalid state transition from {from_state.value} to {to_state.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )
            self.logger.warning(error_msg)
            return StateTransitionResult(
                valid=False,
                error_message=error_msg,
                from_state=from_state,
                to_state=to_state,
                allowed_transitions=allowed
            )

        return StateTransitionResult(
            valid=True,
            error_message=None,
            from_state=from_state,
            to_state=to_state,
            allowed_transitions=allowed
        )

    def get_allowed_transitions(
        self,
        from_state: WorkflowLifecycle
    ) -> Set[WorkflowLifecycle]:
        """
        Get all allowed transitions from a given state.

        Useful for displaying available actions to users or for
        programmatic decision making.

        Args:
            from_state: Current workflow state

        Returns:
            Set of valid next states (may be empty for terminal states)

        Example:
            >>> validator = StateTransitionValidator()
            >>> allowed = validator.get_allowed_transitions(WorkflowLifecycle.RUNNING)
            >>> assert WorkflowLifecycle.PAUSED in allowed
            >>> assert WorkflowLifecycle.COMPLETED in allowed
            >>> assert WorkflowLifecycle.FAILED in allowed
            >>>
            >>> # Terminal state has no transitions
            >>> archived_allowed = validator.get_allowed_transitions(
            ...     WorkflowLifecycle.ARCHIVED
            ... )
            >>> assert len(archived_allowed) == 0
        """
        return VALID_TRANSITIONS.get(from_state, set())

    def is_terminal_state(self, state: WorkflowLifecycle) -> bool:
        """
        Check if a state is terminal (no outgoing transitions except ARCHIVED).

        A terminal state is one where the workflow has ended execution.
        Terminal states are COMPLETED, FAILED, and CANCELLED.

        Note: ARCHIVED is not considered terminal in this context because
        it has no outgoing transitions at all (it's the final state).

        Args:
            state: Workflow state to check

        Returns:
            True if state is terminal (COMPLETED, FAILED, or CANCELLED)

        Example:
            >>> validator = StateTransitionValidator()
            >>> assert validator.is_terminal_state(WorkflowLifecycle.COMPLETED)
            >>> assert validator.is_terminal_state(WorkflowLifecycle.FAILED)
            >>> assert validator.is_terminal_state(WorkflowLifecycle.CANCELLED)
            >>> assert not validator.is_terminal_state(WorkflowLifecycle.RUNNING)
            >>> assert not validator.is_terminal_state(WorkflowLifecycle.ARCHIVED)
        """
        from adws.state.lifecycle import TERMINAL_STATES
        return state in TERMINAL_STATES
