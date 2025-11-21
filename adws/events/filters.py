"""
EventFilter for targeted event subscriptions.

This module provides the EventFilter class for filtering events based on
multiple criteria: event types, workflow IDs, severity levels, and sources.
"""

from dataclasses import dataclass
from typing import Optional, List
from adws.events.models import ADWEvent, EventType, EventSeverity


@dataclass
class EventFilter:
    """
    Filter for event subscription.

    All specified criteria are ANDed together (all must match).
    None/empty list means "match all" for that criterion.

    Examples:
        # Subscribe to only errors for specific workflow
        filter = EventFilter(
            adw_ids=["wf-2025-001"],
            severities=[EventSeverity.ERROR, EventSeverity.CRITICAL]
        )

        # Subscribe to all LLM events (any workflow)
        filter = EventFilter(
            event_types=[
                EventType.LLM_REQUEST,
                EventType.LLM_RESPONSE,
                EventType.LLM_ERROR
            ]
        )

        # Subscribe to events from specific source
        filter = EventFilter(sources=["agent"])

        # Subscribe to all events (no filter)
        filter = EventFilter()  # or just pass None to subscribe()
    """

    event_types: Optional[List[EventType]] = None
    """Filter by event types (match any in list)"""

    adw_ids: Optional[List[str]] = None
    """Filter by workflow IDs (match any in list)"""

    severities: Optional[List[EventSeverity]] = None
    """Filter by severity levels (match any in list)"""

    sources: Optional[List[str]] = None
    """Filter by event source (match any in list)"""

    def matches(self, event: ADWEvent) -> bool:
        """
        Check if event matches filter criteria.

        Args:
            event: Event to check

        Returns:
            True if event matches all specified criteria (AND logic)

        Algorithm:
            For each non-None filter criterion:
                If event field not in criterion list: return False
            If all criteria passed: return True

        Examples:
            >>> filter = EventFilter(event_types=[EventType.WORKFLOW_STARTED])
            >>> event = ADWEvent(event_type=EventType.WORKFLOW_STARTED, ...)
            >>> filter.matches(event)  # True
            >>>
            >>> event2 = ADWEvent(event_type=EventType.WORKFLOW_COMPLETED, ...)
            >>> filter.matches(event2)  # False
        """
        # Check event_types filter
        if self.event_types and len(self.event_types) > 0:
            if event.event_type not in self.event_types:
                return False

        # Check adw_ids filter
        if self.adw_ids and len(self.adw_ids) > 0:
            if event.adw_id not in self.adw_ids:
                return False

        # Check severities filter
        if self.severities and len(self.severities) > 0:
            if event.severity not in self.severities:
                return False

        # Check sources filter
        if self.sources and len(self.sources) > 0:
            if event.source not in self.sources:
                return False

        # All criteria passed
        return True
