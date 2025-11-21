"""
Workflow state reconstruction from event stream.

This module provides tools for rebuilding workflow state from events and
managing checkpoints for recovery.

Issue: #12 - Event Integration with Workflows
Design Principles:
- Accuracy: 100% state reconstruction accuracy requirement
- Performance: <100ms reconstruction for <1000 events
- Reliability: Event replay must be deterministic
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from adws.events.backends.file import FileEventBus
from adws.events.bus import EventBus
from adws.events.models import ADWEvent, EventType
from adws.state.models import WorkflowState
from adws.state.lifecycle import WorkflowLifecycle

logger = logging.getLogger(__name__)


class StateReconstructor:
    """
    Reconstruct workflow state from event stream.

    Provides event replay capabilities for state reconstruction and
    time-travel debugging.

    Usage:
        >>> from adws.events.backends.file import FileEventBus
        >>> bus = FileEventBus()
        >>> reconstructor = StateReconstructor(bus)
        >>>
        >>> # Reconstruct current state
        >>> state = await reconstructor.reconstruct_state("wf-001")
        >>>
        >>> # Get event timeline
        >>> timeline = await reconstructor.get_timeline("wf-001")
    """

    def __init__(self, event_bus: FileEventBus):
        """
        Initialize StateReconstructor with file event bus.

        Args:
            event_bus: FileEventBus instance for reading event history

        Note:
            Requires FileEventBus for reading historical events.
            Other EventBus types may not support event replay.
        """
        self.event_bus = event_bus

    async def reconstruct_state(self, adw_id: str) -> Optional[WorkflowState]:
        """
        Reconstruct complete workflow state from events.

        Replays all events for workflow to rebuild current state.

        Args:
            adw_id: Workflow identifier

        Returns:
            Reconstructed WorkflowState, or None if no events found

        Algorithm:
            1. Read all events for workflow
            2. Find WORKFLOW_STARTED event for initial state
            3. Apply each subsequent event to update state
            4. Return final reconstructed state

        Performance:
            Target: <100ms for <1000 events

        Example:
            >>> reconstructed = await reconstructor.reconstruct_state("wf-001")
            >>> if reconstructed:
            ...     print(f"State: {reconstructed.state}")
        """
        events = self.event_bus.read_events(adw_id)

        if not events:
            return None

        # Find WORKFLOW_STARTED event for initial state
        started_event = next(
            (e for e in events if e.event_type == EventType.WORKFLOW_STARTED),
            None
        )

        if not started_event:
            logger.warning(f"No WORKFLOW_STARTED event for {adw_id}")
            return None

        # Initialize state from WORKFLOW_STARTED event
        initial_state = started_event.data.get("initial_state", {})

        state_dict = {
            "workflow_id": adw_id,
            "workflow_name": started_event.data.get("workflow_name", "unknown"),
            "workflow_type": started_event.data.get("workflow_type", "standard"),
            "state": initial_state.get("state", "created"),
            "tags": initial_state.get("tags", []),
            "issue_number": initial_state.get("issue_number"),
            "branch_name": initial_state.get("branch_name"),
            "created_at": started_event.timestamp,
            "cost_usd": 0.0,
            "total_tokens": 0,
            "metadata": {},
        }

        # Replay subsequent events to update state
        for event in events:
            state_dict = self._apply_event(state_dict, event)

        # Construct WorkflowState from dictionary
        return WorkflowState(**state_dict)

    def _apply_event(
        self,
        state_dict: Dict[str, Any],
        event: ADWEvent
    ) -> Dict[str, Any]:
        """
        Apply single event to update state dictionary.

        Args:
            state_dict: Current state dictionary
            event: Event to apply

        Returns:
            Updated state dictionary
        """
        if event.event_type == EventType.STATE_TRANSITION:
            # Update state from transition event
            state_dict["state"] = event.data.get("to_state", state_dict["state"])
            state_dict["last_activity_at"] = event.timestamp
            # Some transitions may include metrics; incorporate if present
            metrics = event.data.get("metrics", {})
            if isinstance(metrics, dict):
                if "cost_usd" in metrics:
                    state_dict["cost_usd"] = metrics["cost_usd"]
                if "total_tokens" in metrics:
                    state_dict["total_tokens"] = metrics["total_tokens"]

        elif event.event_type == EventType.WORKFLOW_COMPLETED:
            state_dict["state"] = "completed"
            state_dict["completed_at"] = event.timestamp
            metrics = event.data.get("metrics", {})
            if "cost_usd" in metrics:
                state_dict["cost_usd"] = metrics["cost_usd"]
            if "total_tokens" in metrics:
                state_dict["total_tokens"] = metrics["total_tokens"]

        elif event.event_type == EventType.WORKFLOW_FAILED:
            state_dict["state"] = "failed"
            state_dict["completed_at"] = event.timestamp
            state_dict["error_message"] = event.data.get("error_message")
            metrics = event.data.get("metrics", {})
            if "cost_usd" in metrics:
                state_dict["cost_usd"] = metrics["cost_usd"]
            if "total_tokens" in metrics:
                state_dict["total_tokens"] = metrics["total_tokens"]

        elif event.event_type == EventType.WORKFLOW_PAUSED:
            state_dict["state"] = "paused"

        elif event.event_type == EventType.WORKFLOW_RESUMED:
            state_dict["state"] = "running"

        elif event.event_type == EventType.COST_UPDATED:
            metrics = event.data.get("metrics", {})
            if isinstance(metrics, dict):
                if "cost_usd" in metrics:
                    state_dict["cost_usd"] = metrics["cost_usd"]
                if "total_tokens" in metrics:
                    state_dict["total_tokens"] = metrics["total_tokens"]

        return state_dict

    async def reconstruct_at_time(
        self,
        adw_id: str,
        timestamp: datetime
    ) -> Optional[WorkflowState]:
        """
        Reconstruct workflow state at specific point in time.

        Replays events up to the specified timestamp.

        Args:
            adw_id: Workflow identifier
            timestamp: Point in time to reconstruct state

        Returns:
            Reconstructed WorkflowState at that timestamp, or None if no events

        Example:
            >>> from datetime import datetime, timedelta
            >>> one_hour_ago = datetime.now() - timedelta(hours=1)
            >>> past_state = await reconstructor.reconstruct_at_time("wf-001", one_hour_ago)
        """
        events = self.event_bus.read_events(adw_id)

        if not events:
            return None

        # Normalize timestamp to UTC-aware for safe comparison
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Filter events up to timestamp
        events_until_time = [e for e in events if e.timestamp <= timestamp]

        if not events_until_time:
            return None

        # Find WORKFLOW_STARTED event
        started_event = next(
            (e for e in events_until_time if e.event_type == EventType.WORKFLOW_STARTED),
            None
        )

        if not started_event:
            return None

        # Initialize and replay
        initial_state = started_event.data.get("initial_state", {})
        state_dict = {
            "workflow_id": adw_id,
            "workflow_name": started_event.data.get("workflow_name", "unknown"),
            "workflow_type": started_event.data.get("workflow_type", "standard"),
            "state": initial_state.get("state", "created"),
            "tags": initial_state.get("tags", []),
            "issue_number": initial_state.get("issue_number"),
            "branch_name": initial_state.get("branch_name"),
            "created_at": started_event.timestamp,
            "cost_usd": 0.0,
            "total_tokens": 0,
            "metadata": {},
        }

        for event in events_until_time:
            state_dict = self._apply_event(state_dict, event)

        return WorkflowState(**state_dict)

    async def get_timeline(self, adw_id: str) -> List[ADWEvent]:
        """
        Get chronological timeline of all events for workflow.

        Args:
            adw_id: Workflow identifier

        Returns:
            List of events in chronological order

        Example:
            >>> timeline = await reconstructor.get_timeline("wf-001")
            >>> for event in timeline:
            ...     print(f"{event.timestamp}: {event.event_type}")
        """
        events = self.event_bus.read_events(adw_id)
        # Events are already in chronological order from file
        return events


class CheckpointManager:
    """
    Manage workflow checkpoints for recovery.

    Provides checkpoint creation and restoration using event stream.

    Usage:
        >>> bus = FileEventBus()
        >>> reconstructor = StateReconstructor(bus)
        >>> manager = CheckpointManager(bus, reconstructor)
        >>>
        >>> # Create checkpoint
        >>> checkpoint_id = await manager.create_checkpoint(
        ...     adw_id="wf-001",
        ...     state=workflow_state,
        ...     checkpoint_metadata={"phase": "build"}
        ... )
        >>>
        >>> # Restore from checkpoint
        >>> restored = await manager.restore_from_checkpoint(
        ...     adw_id="wf-001",
        ...     checkpoint_id=checkpoint_id
        ... )
    """

    def __init__(
        self,
        event_bus: EventBus,
        state_reconstructor: StateReconstructor
    ):
        """
        Initialize CheckpointManager.

        Args:
            event_bus: EventBus for emitting checkpoint events
            state_reconstructor: StateReconstructor for state restoration
        """
        self.event_bus = event_bus
        self.state_reconstructor = state_reconstructor

    async def create_checkpoint(
        self,
        adw_id: str,
        state: WorkflowState,
        checkpoint_metadata: Dict[str, Any]
    ) -> str:
        """
        Create checkpoint by emitting checkpoint event.

        Args:
            adw_id: Workflow identifier
            state: Current workflow state to checkpoint
            checkpoint_metadata: Metadata about checkpoint (reason, automatic, etc.)

        Returns:
            Checkpoint ID for restoration

        Example:
            >>> checkpoint_id = await manager.create_checkpoint(
            ...     adw_id="wf-001",
            ...     state=workflow_state,
            ...     checkpoint_metadata={"automatic": True, "phase": "build"}
            ... )
        """
        # Generate unique checkpoint ID
        checkpoint_id = f"cp-{secrets.token_urlsafe(12)}"

        # Serialize full workflow state for checkpoint (JSON-serializable)
        checkpoint_state = state.model_dump(mode="json")

        # Emit checkpoint event
        from adws.workflows.events import WorkflowEventEmitter

        emitter = WorkflowEventEmitter(self.event_bus)
        emitter.emit_checkpoint_created(
            adw_id=adw_id,
            checkpoint_id=checkpoint_id,
            checkpoint_state=checkpoint_state,
            checkpoint_metadata={
                **checkpoint_metadata,
                "snapshot_version": 1,
            }
        )

        return checkpoint_id

    async def restore_from_checkpoint(
        self,
        adw_id: str,
        checkpoint_id: str
    ) -> Optional[WorkflowState]:
        """
        Restore workflow state from checkpoint.

        Args:
            adw_id: Workflow identifier
            checkpoint_id: Checkpoint ID to restore from

        Returns:
            Restored WorkflowState, or None if checkpoint not found

        Algorithm:
            1. Find checkpoint event by ID
            2. Get checkpoint timestamp
            3. Reconstruct state at that timestamp
            4. Return reconstructed state

        Example:
            >>> restored = await manager.restore_from_checkpoint(
            ...     adw_id="wf-001",
            ...     checkpoint_id="cp-abc123"
            ... )
        """
        # Get all events for workflow
        if not isinstance(self.event_bus, FileEventBus):
            logger.error("restore_from_checkpoint requires FileEventBus")
            return None

        events = self.event_bus.read_events(adw_id)

        # Find checkpoint event
        checkpoint_event = next(
            (e for e in events
             if e.event_type == EventType.WORKFLOW_CHECKPOINT_CREATED
             and e.data.get("checkpoint_id") == checkpoint_id),
            None
        )

        if not checkpoint_event:
            logger.warning(f"Checkpoint {checkpoint_id} not found for {adw_id}")
            return None

        # If full snapshot is present, prefer restoring directly from it
        snapshot = checkpoint_event.data.get("checkpoint_state")
        if isinstance(snapshot, dict) and snapshot:
            try:
                return WorkflowState(**snapshot)
            except Exception:
                # Fallback to event replay if snapshot parsing fails
                pass

        # Reconstruct state at checkpoint time as a fallback
        return await self.state_reconstructor.reconstruct_at_time(
            adw_id,
            checkpoint_event.timestamp
        )

    async def list_checkpoints(self, adw_id: str) -> List[Dict[str, Any]]:
        """
        List all available checkpoints for workflow.

        Args:
            adw_id: Workflow identifier

        Returns:
            List of checkpoint metadata dictionaries

        Example:
            >>> checkpoints = await manager.list_checkpoints("wf-001")
            >>> for cp in checkpoints:
            ...     print(f"{cp['checkpoint_id']}: {cp['timestamp']}")
        """
        if not isinstance(self.event_bus, FileEventBus):
            logger.error("list_checkpoints requires FileEventBus")
            return []

        events = self.event_bus.read_events(adw_id)

        # Filter checkpoint events
        checkpoint_events = [
            e for e in events
            if e.event_type == EventType.WORKFLOW_CHECKPOINT_CREATED
        ]

        # Build checkpoint list
        checkpoints = []
        for event in checkpoint_events:
            checkpoints.append({
                "checkpoint_id": event.data.get("checkpoint_id"),
                "timestamp": event.timestamp,
                "metadata": event.data.get("checkpoint_metadata", {}),
                "state_snapshot": event.data.get("checkpoint_state", {})
            })

        return checkpoints
