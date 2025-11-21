"""
FileEventBus - JSONL file-based event persistence.

This module provides file-based event storage using JSONL format (JSON Lines).
Events are appended to: agents/{workflow_id}/events.jsonl

Benefits:
- Simple, reliable persistence
- Human-readable (can tail -f events.jsonl)
- Easy debugging and auditing
- No external dependencies
- Audit trail for all workflow events

Limitations:
- Not real-time (file I/O latency)
- No streaming to TUI (use SocketEventBus for that)
- File size grows unbounded (need cleanup policies)
"""

from pathlib import Path
from typing import List, Callable
from adws.events.bus import BaseEventBus
from adws.events.models import ADWEvent
import logging


logger = logging.getLogger(__name__)


class FileEventBus(BaseEventBus):
    """
    File-based event backend using JSONL format.

    Events are appended to: agents/{workflow_id}/events.jsonl

    Benefits:
    - Simple, reliable persistence
    - Human-readable (can tail -f events.jsonl)
    - Easy debugging and auditing
    - No external dependencies
    - Audit trail for all workflow events

    Limitations:
    - Not real-time (file I/O latency)
    - No streaming to TUI (use SocketEventBus for that)
    - File size grows unbounded (need cleanup policies)

    Usage:
        >>> bus = FileEventBus(base_dir="agents")
        >>> event = ADWEvent(adw_id="wf-001", ...)
        >>> bus.publish(event)  # Appends to agents/wf-001/events.jsonl
        >>>
        >>> # Read all events for workflow
        >>> events = bus.read_events("wf-001")
        >>>
        >>> # Replay events
        >>> def handler(event: ADWEvent):
        ...     print(f"Replay: {event.event_type}")
        >>> bus.replay_events("wf-001", handler)
    """

    def __init__(self, base_dir: str = "agents"):
        """
        Initialize file event bus.

        Args:
            base_dir: Base directory for event files (default: "agents")

        Directory structure created:
            agents/
            ├── wf-2025-001/
            │   ├── events.jsonl
            │   └── ...
            ├── wf-2025-002/
            │   ├── events.jsonl
            │   └── ...
        """
        super().__init__()
        self.base_dir = Path(base_dir)
        self.logger = logging.getLogger(__name__)

    def _publish_to_backend(self, event: ADWEvent) -> None:
        """
        Append event to JSONL file.

        File format:
            One JSON object per line (JSONL):
            {"workflow_id":"wf-001","event_type":"workflow_started",...}
            {"workflow_id":"wf-001","event_type":"phase_started",...}

        Algorithm:
            1. Create event directory if missing: agents/{workflow_id}/
            2. Open events.jsonl in append mode
            3. Write event as single JSON line + newline
            4. Flush immediately (ensure written)

        Error Handling:
        - If directory creation fails: log error, don't crash
        - If file write fails: log error, don't crash
        - Errors are non-fatal (workflow continues)
        """
        try:
            # Create event directory: agents/{workflow_id}/
            event_dir = self.base_dir / event.workflow_id
            event_dir.mkdir(parents=True, exist_ok=True)

            # Event file path: agents/{workflow_id}/events.jsonl
            event_file = event_dir / "events.jsonl"

            # Append event (one line per event)
            with open(event_file, "a", encoding="utf-8") as f:
                f.write(event.to_jsonl() + "\n")
                f.flush()  # Ensure written immediately (for tail -f)

            self.logger.debug(
                f"Event written: {event.event_type} for {event.workflow_id}"
            )

        except Exception as e:
            self.logger.error(
                f"Failed to write event {event.event_type} to file: {e}",
                exc_info=True
            )
            # Don't propagate error (non-fatal)

    def read_events(self, adw_id: str) -> List[ADWEvent]:
        """
        Read all events for workflow from file.

        Args:
            adw_id: Workflow identifier

        Returns:
            List of ADWEvent objects (in chronological order)

        Error Handling:
        - If file doesn't exist: return empty list
        - If line fails to parse: log warning, skip line, continue

        Example:
            >>> bus = FileEventBus()
            >>> events = bus.read_events("wf-2025-001")
            >>> for event in events:
            ...     print(f"{event.timestamp}: {event.event_type}")
        """
        event_file = self.base_dir / adw_id / "events.jsonl"

        if not event_file.exists():
            self.logger.debug(f"No event file for {adw_id}")
            return []

        events = []
        with open(event_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                try:
                    event = ADWEvent.from_jsonl(line.strip())
                    events.append(event)
                except Exception as e:
                    self.logger.warning(
                        f"Failed to parse event on line {line_num} in {event_file}: {e}"
                    )
                    # Skip malformed line, continue parsing

        self.logger.info(f"Read {len(events)} events for {adw_id}")
        return events

    def replay_events(
        self,
        adw_id: str,
        handler: Callable[[ADWEvent], None]
    ) -> None:
        """
        Replay all events for workflow through handler.

        Args:
            adw_id: Workflow identifier
            handler: Function to call for each event

        Use Cases:
        - Debugging: Replay events to understand workflow execution
        - Testing: Verify event sequence
        - Migration: Replay events to new backend
        - Analysis: Compute metrics from historical events

        Example:
            >>> def print_handler(event: ADWEvent):
            ...     print(f"{event.timestamp}: {event.message}")
            >>>
            >>> bus = FileEventBus()
            >>> bus.replay_events("wf-2025-001", print_handler)
        """
        events = self.read_events(adw_id)

        for event in events:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(
                    f"Handler error during replay for {event.event_type}: {e}",
                    exc_info=True
                )
                # Continue replaying despite handler errors
