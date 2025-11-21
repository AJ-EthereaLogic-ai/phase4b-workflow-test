"""
ADWS v2.0 State Management - Stuck Workflow Detector

This module detects workflows that are stuck (hung/timeout) based on
elapsed time in specific states.

Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence
Phase: Phase 2 - State machine validation (NO new database fields)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List

from adws.state.lifecycle import WorkflowLifecycle

if TYPE_CHECKING:
    from adws.state.manager import StateManager
    from adws.state.models import WorkflowState


class StuckDetector:
    """
    Detects workflows that are stuck (hung/timeout).

    Detection rules:
    - RUNNING > 1 hour: Stuck
    - PAUSED > 24 hours: Stuck

    Can be run on-demand or as scheduled background task.

    The detector uses the workflow's started_at timestamp to determine
    how long it has been in the current state. Workflows exceeding the
    timeout thresholds are considered stuck.

    Example:
        >>> detector = StuckDetector(state_manager)
        >>> stuck_workflows = detector.detect_stuck_workflows()
        >>> for workflow in stuck_workflows:
        ...     print(f"Stuck: {workflow.workflow_id} in {workflow.state}")
        ...     detector.mark_as_stuck(workflow.workflow_id)
    """

    # Timeout constants (class attributes for configurability)
    RUNNING_TIMEOUT_HOURS = 1      # 1 hour before stuck
    PAUSED_TIMEOUT_HOURS = 24      # 24 hours before stuck

    def __init__(self, state_manager: "StateManager") -> None:
        """
        Initialize stuck detector.

        Args:
            state_manager: StateManager instance for workflow access
        """
        self.state_manager = state_manager
        self.logger = logging.getLogger(__name__)

    def detect_stuck_workflows(self) -> List["WorkflowState"]:
        """
        Detect all stuck workflows.

        Queries workflows in RUNNING and PAUSED states and checks if they
        have exceeded their timeout thresholds based on started_at timestamp.

        Returns:
            List of WorkflowState objects that are stuck

        Algorithm:
            1. Query workflows in RUNNING state where
               (NOW - started_at) > 1 hour
            2. Query workflows in PAUSED state where
               (NOW - started_at) > 24 hours
            3. Combine results and return

        Example:
            >>> stuck = detector.detect_stuck_workflows()
            >>> print(f"Found {len(stuck)} stuck workflows")
            >>> for workflow in stuck:
            ...     print(f"  {workflow.workflow_id}: {workflow.state}")
            ...     # Take action: notify, recover, or mark as stuck
        """
        now = datetime.now(timezone.utc)
        stuck_workflows: List[WorkflowState] = []

        # Detect running timeouts (> 1 hour)
        running_cutoff = now - timedelta(hours=self.RUNNING_TIMEOUT_HOURS)
        running_stuck = self._query_workflows_before(
            WorkflowLifecycle.RUNNING,
            running_cutoff
        )
        stuck_workflows.extend(running_stuck)
        self.logger.info(
            f"Found {len(running_stuck)} workflows stuck in RUNNING state"
        )

        # Detect paused timeouts (> 24 hours)
        paused_cutoff = now - timedelta(hours=self.PAUSED_TIMEOUT_HOURS)
        paused_stuck = self._query_workflows_before(
            WorkflowLifecycle.PAUSED,
            paused_cutoff
        )
        stuck_workflows.extend(paused_stuck)
        self.logger.info(
            f"Found {len(paused_stuck)} workflows stuck in PAUSED state"
        )

        self.logger.info(f"Total stuck workflows detected: {len(stuck_workflows)}")
        return stuck_workflows

    def is_stuck(self, workflow: "WorkflowState") -> bool:
        """
        Check if a specific workflow is stuck.

        Evaluates a single workflow against the stuck detection rules
        without querying the database.

        Args:
            workflow: WorkflowState to check

        Returns:
            True if workflow is stuck, False otherwise

        Logic:
            - RUNNING > 1 hour: stuck
            - PAUSED > 24 hours: stuck
            - All other states: not stuck

        Example:
            >>> workflow = state_manager.get_workflow("wf-123")
            >>> if detector.is_stuck(workflow):
            ...     print(f"{workflow.workflow_id} is stuck!")
            ...     detector.mark_as_stuck(workflow.workflow_id)
        """
        if workflow.started_at is None:
            # Cannot determine stuck status without started_at
            return False

        now = datetime.now(timezone.utc)
        elapsed = now - workflow.started_at

        if workflow.state == WorkflowLifecycle.RUNNING:
            running_threshold = timedelta(hours=self.RUNNING_TIMEOUT_HOURS)
            if elapsed >= running_threshold:
                self.logger.debug(
                    f"Workflow {workflow.workflow_id} stuck in RUNNING "
                    f"(elapsed: {elapsed.total_seconds() / 3600:.1f}h)"
                )
                return True

        elif workflow.state == WorkflowLifecycle.PAUSED:
            paused_threshold = timedelta(hours=self.PAUSED_TIMEOUT_HOURS)
            if elapsed >= paused_threshold:
                self.logger.debug(
                    f"Workflow {workflow.workflow_id} stuck in PAUSED "
                    f"(elapsed: {elapsed.total_seconds() / 3600:.1f}h)"
                )
                return True

        return False

    def mark_as_stuck(self, workflow_id: str) -> None:
        """
        Mark workflow as stuck.

        Transitions the workflow to STUCK state if the transition is valid.
        This should only be called after detecting that a workflow is stuck.

        Args:
            workflow_id: Workflow to mark stuck

        Raises:
            ValueError: If workflow not found
            StateTransitionError: If transition to STUCK is invalid

        Example:
            >>> stuck_workflows = detector.detect_stuck_workflows()
            >>> for workflow in stuck_workflows:
            ...     try:
            ...         detector.mark_as_stuck(workflow.workflow_id)
            ...         print(f"Marked {workflow.workflow_id} as stuck")
            ...     except StateTransitionError as e:
            ...         print(f"Cannot mark as stuck: {e}")
        """
        import asyncio
        from adws.state.exceptions import StateTransitionError
        from adws.state.validators import StateTransitionValidator

        # Load current workflow state
        workflow = asyncio.run(self.state_manager.get_workflow(workflow_id))
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Validate transition to STUCK
        validator = StateTransitionValidator()
        result = validator.validate_transition(
            workflow.state,
            WorkflowLifecycle.STUCK,
            workflow_id
        )

        if not result.valid:
            raise StateTransitionError(
                result.error_message or "Invalid transition to STUCK",
                from_state=workflow.state.value,
                to_state=WorkflowLifecycle.STUCK.value,
                allowed_transitions={s.value for s in result.allowed_transitions}
            )

        # Perform state transition
        asyncio.run(self.state_manager.update_workflow(
            workflow_id=workflow_id,
            state=WorkflowLifecycle.STUCK
        ))

        self.logger.info(f"Marked workflow {workflow_id} as stuck")

    def _query_workflows_before(
        self,
        state: WorkflowLifecycle,
        cutoff_time: datetime
    ) -> List["WorkflowState"]:
        """
        Query workflows in given state with started_at before cutoff time.

        Uses direct SQLite queries to find workflows that have been
        in a specific state longer than the timeout threshold.

        Args:
            state: Workflow state to query
            cutoff_time: Maximum started_at time (workflows before this are stuck)

        Returns:
            List of workflows matching criteria

        Example:
            >>> cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            >>> stuck_running = detector._query_workflows_before(
            ...     WorkflowLifecycle.RUNNING,
            ...     cutoff
            ... )
        """
        import sqlite3
        from adws.state.models import WorkflowState

        try:
            # Use synchronous sqlite3 to avoid asyncio.run() issues
            conn = sqlite3.connect(str(self.state_manager.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    SELECT
                        workflow_id,
                        workflow_name,
                        state,
                        created_at,
                        started_at,
                        completed_at,
                        archived_at,
                        last_activity_at,
                        workflow_type,
                        issue_number,
                        branch_name,
                        base_branch,
                        worktree_path,
                        tags,
                        metadata,
                        exit_code,
                        error_message,
                        retry_count,
                        cost_usd,
                        total_tokens
                    FROM workflows
                    WHERE state = ? AND started_at IS NOT NULL AND started_at < ?
                    """,
                    (state.value, cutoff_time.isoformat())
                )

                rows = cursor.fetchall()
                workflows = []
                for row in rows:
                    row_dict = dict(row)
                    workflows.append(WorkflowState(**row_dict))

                self.logger.debug(
                    f"Found {len(workflows)} {state.value} workflows started before {cutoff_time}"
                )

                return workflows
            finally:
                conn.close()

        except Exception as e:
            self.logger.error(f"Error querying workflows: {e}")
            return []
