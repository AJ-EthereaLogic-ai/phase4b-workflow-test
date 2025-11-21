"""
Workflow event emission convenience methods.

This module provides WorkflowEventEmitter, a convenience wrapper for emitting
workflow-specific events with typed methods and consistent formatting.

Issue: #12 - Event Integration with Workflows
Design Principles:
- Type-safe: Explicit parameters for each event type
- Consistent: Standard event structure and naming
- Non-blocking: Event emission should not impact workflow performance (<5ms)
- Error-isolated: Errors in event emission don't crash workflow
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from adws.events.bus import EventBus
from adws.events.models import ADWEvent, EventSeverity, EventType
from adws.state.lifecycle import WorkflowLifecycle

logger = logging.getLogger(__name__)


class WorkflowEventEmitter:
    """
    Convenience wrapper for emitting workflow-specific events.

    Wraps EventBus with typed methods for workflow lifecycle events.
    Provides consistent event formatting and error isolation.

    Usage:
        >>> from adws.events.backends.file import FileEventBus
        >>> bus = FileEventBus()
        >>> emitter = WorkflowEventEmitter(bus)
        >>>
        >>> emitter.emit_workflow_started(
        ...     adw_id="wf-001",
        ...     workflow_name="my-workflow",
        ...     workflow_type="standard",
        ...     initial_state={"state": "created"}
        ... )

    Design Notes:
        - All emit methods are non-blocking (<5ms target)
        - Errors in event emission are logged but don't propagate
        - Events include timestamp, severity, and structured data
        - Optional correlation_id and parent_event_id for event hierarchies
    """

    def __init__(
        self,
        event_bus: EventBus,
        correlation_id: Optional[str] = None,
        parent_event_id: Optional[str] = None
    ):
        """
        Initialize WorkflowEventEmitter with event bus.

        Args:
            event_bus: EventBus instance for publishing events
            correlation_id: Optional correlation ID for all emitted events
            parent_event_id: Optional parent event ID for hierarchical events
        """
        self.event_bus = event_bus
        self.correlation_id = correlation_id
        self.parent_event_id = parent_event_id

    def _create_event(
        self,
        adw_id: str,
        event_type: EventType,
        severity: EventSeverity,
        message: str,
        data: Dict[str, Any]
    ) -> ADWEvent:
        """
        Create ADWEvent with standard fields.

        Args:
            adw_id: Workflow identifier
            event_type: Type of event
            severity: Event severity level
            message: Human-readable message
            data: Event-specific data

        Returns:
            ADWEvent instance ready for publishing
        """
        return ADWEvent(
            adw_id=adw_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            source="workflow_emitter",
            severity=severity,
            data=data,
            correlation_id=self.correlation_id,
            parent_event_id=self.parent_event_id,
            message=message
        )

    def _publish_event(self, event: ADWEvent) -> None:
        """
        Publish event with error handling.

        Errors are logged but not propagated to avoid impacting workflow execution.

        Args:
            event: Event to publish
        """
        try:
            self.event_bus.publish(event)
        except Exception as e:
            logger.error(
                f"Failed to publish event {event.event_type} for {event.adw_id}: {e}",
                exc_info=True
            )
            # Don't propagate error - event emission failures should not crash workflow

    def emit_workflow_started(
        self,
        adw_id: str,
        workflow_name: str,
        workflow_type: str,
        initial_state: Dict[str, Any]
    ) -> None:
        """
        Emit workflow started event.

        Args:
            adw_id: Workflow identifier
            workflow_name: Human-readable workflow name
            workflow_type: Type of workflow (standard, tdd, etc.)
            initial_state: Initial workflow state dictionary

        Example:
            >>> emitter.emit_workflow_started(
            ...     adw_id="wf-001",
            ...     workflow_name="feature-xyz",
            ...     workflow_type="tdd",
            ...     initial_state={"state": "created", "phase": 0}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_STARTED,
            severity=EventSeverity.INFO,
            message=f"Workflow started: {workflow_name}",
            data={
                "workflow_name": workflow_name,
                "workflow_type": workflow_type,
                "initial_state": initial_state
            }
        )
        self._publish_event(event)

    def emit_workflow_completed(
        self,
        adw_id: str,
        duration_seconds: float,
        final_state: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> None:
        """
        Emit workflow completed event.

        Args:
            adw_id: Workflow identifier
            duration_seconds: Total workflow execution time
            final_state: Final workflow state dictionary
            metrics: Workflow metrics (cost, tokens, etc.)

        Example:
            >>> emitter.emit_workflow_completed(
            ...     adw_id="wf-001",
            ...     duration_seconds=120.5,
            ...     final_state={"state": "completed", "exit_code": 0},
            ...     metrics={"cost_usd": 1.25, "total_tokens": 5000}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_COMPLETED,
            severity=EventSeverity.INFO,
            message=f"Workflow completed in {duration_seconds:.1f}s",
            data={
                "duration_seconds": duration_seconds,
                "final_state": final_state,
                "metrics": metrics
            }
        )
        self._publish_event(event)

    def emit_workflow_failed(
        self,
        adw_id: str,
        error_message: str,
        error_type: Optional[str],
        final_state: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> None:
        """
        Emit workflow failed event.

        Args:
            adw_id: Workflow identifier
            error_message: Error description
            error_type: Type/category of error (optional)
            final_state: Final workflow state dictionary
            metrics: Workflow metrics at failure time

        Example:
            >>> emitter.emit_workflow_failed(
            ...     adw_id="wf-001",
            ...     error_message="Test suite failed with 5 errors",
            ...     error_type="TestFailure",
            ...     final_state={"state": "failed", "phase": 3},
            ...     metrics={"attempts": 3}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_FAILED,
            severity=EventSeverity.ERROR,
            message=f"Workflow failed: {error_message}",
            data={
                "error_message": error_message,
                "error_type": error_type,
                "final_state": final_state,
                "metrics": metrics
            }
        )
        self._publish_event(event)

    def emit_workflow_step_started(
        self,
        adw_id: str,
        step_name: str,
        step_index: int,
        step_data: Dict[str, Any]
    ) -> None:
        """
        Emit workflow step started event.

        Args:
            adw_id: Workflow identifier
            step_name: Name of the step being started
            step_index: Sequential index of step in workflow
            step_data: Step-specific data and configuration

        Example:
            >>> emitter.emit_workflow_step_started(
            ...     adw_id="wf-001",
            ...     step_name="build",
            ...     step_index=1,
            ...     step_data={"target": "production"}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_STEP_STARTED,
            severity=EventSeverity.INFO,
            message=f"Step started: {step_name} (#{step_index})",
            data={
                "step_name": step_name,
                "step_index": step_index,
                "step_data": step_data
            }
        )
        self._publish_event(event)

    def emit_workflow_step_completed(
        self,
        adw_id: str,
        step_name: str,
        step_index: int,
        duration_seconds: float,
        step_result: Dict[str, Any]
    ) -> None:
        """
        Emit workflow step completed event.

        Args:
            adw_id: Workflow identifier
            step_name: Name of the completed step
            step_index: Sequential index of step in workflow
            duration_seconds: Step execution time
            step_result: Step execution results

        Example:
            >>> emitter.emit_workflow_step_completed(
            ...     adw_id="wf-001",
            ...     step_name="build",
            ...     step_index=1,
            ...     duration_seconds=45.2,
            ...     step_result={"success": True, "artifacts": 5}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_STEP_COMPLETED,
            severity=EventSeverity.INFO,
            message=f"Step completed: {step_name} ({duration_seconds:.1f}s)",
            data={
                "step_name": step_name,
                "step_index": step_index,
                "duration_seconds": duration_seconds,
                "step_result": step_result
            }
        )
        self._publish_event(event)

    def emit_workflow_step_failed(
        self,
        adw_id: str,
        step_name: str,
        step_index: int,
        error_message: str,
        error_data: Dict[str, Any]
    ) -> None:
        """
        Emit workflow step failed event.

        Args:
            adw_id: Workflow identifier
            step_name: Name of the failed step
            step_index: Sequential index of step in workflow
            error_message: Error description
            error_data: Additional error context and data

        Example:
            >>> emitter.emit_workflow_step_failed(
            ...     adw_id="wf-001",
            ...     step_name="test",
            ...     step_index=2,
            ...     error_message="5 tests failed",
            ...     error_data={"failed_tests": ["test1", "test2"]}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_STEP_FAILED,
            severity=EventSeverity.ERROR,
            message=f"Step failed: {step_name} - {error_message}",
            data={
                "step_name": step_name,
                "step_index": step_index,
                "error_message": error_message,
                "error_data": error_data
            }
        )
        self._publish_event(event)

    def emit_state_transition(
        self,
        adw_id: str,
        from_state: WorkflowLifecycle,
        to_state: WorkflowLifecycle,
        transition_metadata: Dict[str, Any]
    ) -> None:
        """
        Emit state transition event.

        Args:
            adw_id: Workflow identifier
            from_state: Previous workflow state
            to_state: New workflow state
            transition_metadata: Additional transition context

        Example:
            >>> emitter.emit_state_transition(
            ...     adw_id="wf-001",
            ...     from_state=WorkflowLifecycle.CREATED,
            ...     to_state=WorkflowLifecycle.RUNNING,
            ...     transition_metadata={"trigger": "manual"}
            ... )
        """
        # Determine severity based on target state
        if to_state in {WorkflowLifecycle.FAILED, WorkflowLifecycle.STUCK}:
            severity = EventSeverity.ERROR
        elif to_state in {WorkflowLifecycle.PAUSED, WorkflowLifecycle.CANCELLED}:
            severity = EventSeverity.WARNING
        else:
            severity = EventSeverity.INFO

        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.STATE_TRANSITION,
            severity=severity,
            message=f"State transition: {from_state.value} → {to_state.value}",
            data={
                "from_state": from_state.value,
                "to_state": to_state.value,
                "transition_metadata": transition_metadata
            }
        )
        self._publish_event(event)

    def emit_checkpoint_created(
        self,
        adw_id: str,
        checkpoint_id: str,
        checkpoint_state: Dict[str, Any],
        checkpoint_metadata: Dict[str, Any]
    ) -> None:
        """
        Emit checkpoint created event.

        Args:
            adw_id: Workflow identifier
            checkpoint_id: Unique checkpoint identifier
            checkpoint_state: Complete workflow state at checkpoint
            checkpoint_metadata: Checkpoint metadata (automatic, manual, etc.)

        Example:
            >>> emitter.emit_checkpoint_created(
            ...     adw_id="wf-001",
            ...     checkpoint_id="cp-001",
            ...     checkpoint_state={"phase": 2, "step": 5},
            ...     checkpoint_metadata={"automatic": True, "reason": "phase_complete"}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_CHECKPOINT_CREATED,
            severity=EventSeverity.INFO,
            message=f"Checkpoint created: {checkpoint_id}",
            data={
                "checkpoint_id": checkpoint_id,
                "checkpoint_state": checkpoint_state,
                "checkpoint_metadata": checkpoint_metadata
            }
        )
        self._publish_event(event)

    def emit_workflow_paused(
        self,
        adw_id: str,
        reason: str,
        pause_metadata: Dict[str, Any]
    ) -> None:
        """
        Emit workflow paused event.

        Args:
            adw_id: Workflow identifier
            reason: Reason for pause (manual, checkpoint, error, etc.)
            pause_metadata: Additional pause context

        Example:
            >>> emitter.emit_workflow_paused(
            ...     adw_id="wf-001",
            ...     reason="manual_pause",
            ...     pause_metadata={"user": "admin", "checkpoint": "cp-001"}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_PAUSED,
            severity=EventSeverity.WARNING,
            message=f"Workflow paused: {reason}",
            data={
                "reason": reason,
                "pause_metadata": pause_metadata
            }
        )
        self._publish_event(event)

    def emit_workflow_resumed(
        self,
        adw_id: str,
        resumed_from_state: Dict[str, Any],
        resume_metadata: Dict[str, Any]
    ) -> None:
        """
        Emit workflow resumed event.

        Args:
            adw_id: Workflow identifier
            resumed_from_state: State from which workflow is resuming
            resume_metadata: Resume context (checkpoint, manual, etc.)

        Example:
            >>> emitter.emit_workflow_resumed(
            ...     adw_id="wf-001",
            ...     resumed_from_state={"phase": 2, "step": 5},
            ...     resume_metadata={"checkpoint_id": "cp-001"}
            ... )
        """
        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.WORKFLOW_RESUMED,
            severity=EventSeverity.INFO,
            message="Workflow resumed",
            data={
                "resumed_from_state": resumed_from_state,
                "resume_metadata": resume_metadata
            }
        )
        self._publish_event(event)

    def emit_cost_updated(
        self,
        adw_id: str,
        *,
        cost_usd: float | None = None,
        total_tokens: int | None = None,
        update_metadata: Dict[str, Any] | None = None,
    ) -> None:
        """
        Emit cost/usage updated event.

        Args:
            adw_id: Workflow identifier
            cost_usd: New cost value if updated
            total_tokens: New token count if updated
            update_metadata: Optional additional context
        """
        data: Dict[str, Any] = {
            "metrics": {},
            "update_metadata": update_metadata or {},
        }
        if cost_usd is not None:
            data["metrics"]["cost_usd"] = cost_usd
        if total_tokens is not None:
            data["metrics"]["total_tokens"] = total_tokens

        event = self._create_event(
            adw_id=adw_id,
            event_type=EventType.COST_UPDATED,
            severity=EventSeverity.INFO,
            message="Workflow cost/usage updated",
            data=data,
        )
        self._publish_event(event)
