"""
Global EventBus factory and configuration.

This module provides:
- EventBusConfig: Configuration for event bus backends
- get_event_bus(): Global singleton event bus
- create_event_bus(): Factory for creating event bus instances
- reset_event_bus(): Reset global singleton (for testing)

Public API exports:
- ADWEvent, EventType, EventSeverity (from models)
- EventFilter (from filters)
- EventBus (protocol)
- EventBusConfig, get_event_bus, create_event_bus, reset_event_bus
"""

import tempfile
from typing import Optional, Literal
from pydantic import BaseModel, Field
from adws.events.bus import EventBus
from adws.events.backends.file import FileEventBus
from adws.events.models import ADWEvent, EventType, EventSeverity
from adws.events.filters import EventFilter


class EventBusConfig(BaseModel):
    """
    EventBus configuration.

    Configuration can be loaded from:
    - Environment variables (ADWS_EVENT_*)
    - Config file (adws.toml)
    - Defaults (file-based backend)
    """

    backend: Literal["file", "socket", "queue"] = Field(
        default="file",
        description="Event backend type"
    )

    base_dir: str = Field(
        default="agents",
        description="Base directory for file backend"
    )

    socket_path: str = Field(
        default_factory=lambda: f"{tempfile.gettempdir()}/adws_events.sock",
        description="Unix socket path for socket backend"
    )

    queue_url: Optional[str] = Field(
        default=None,
        description="Queue URL for queue backend (redis://...)"
    )

    enable_batching: bool = Field(
        default=False,
        description="Enable event batching for performance"
    )

    batch_size: int = Field(
        default=100,
        description="Batch size if batching enabled"
    )

    @classmethod
    def from_env(cls) -> "EventBusConfig":
        """
        Load configuration from environment variables.

        Environment variables:
        - ADWS_EVENT_BACKEND: Backend type (file, socket, queue)
        - ADWS_EVENT_BASE_DIR: Base directory for file backend
        - ADWS_EVENT_SOCKET_PATH: Socket path
        - ADWS_EVENT_QUEUE_URL: Queue URL

        Returns:
            EventBusConfig with values from env or defaults
        """
        import os
        return cls(
            backend=os.getenv("ADWS_EVENT_BACKEND", "file"),  # type: ignore
            base_dir=os.getenv("ADWS_EVENT_BASE_DIR", "agents"),
            socket_path=os.getenv(
                "ADWS_EVENT_SOCKET_PATH",
                f"{tempfile.gettempdir()}/adws_events.sock"  # Security: use system temp dir
            ),
            queue_url=os.getenv("ADWS_EVENT_QUEUE_URL"),
        )


# Global event bus singleton
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    Get global event bus (lazy initialization).

    Returns:
        EventBus instance (singleton)

    Thread Safety:
    - Singleton creation is NOT thread-safe (use locks if needed)
    - The EventBus instance itself IS thread-safe (Phase 3+)
    - BaseEventBus uses RLock and copy-on-write for concurrent access

    Note:
    - The returned bus supports concurrent publish/subscribe/unsubscribe
    - For purely single-threaded workflows, no special handling needed

    Example:
        >>> from adws.events import get_event_bus, ADWEvent, EventType
        >>>
        >>> bus = get_event_bus()
        >>> event = ADWEvent(
        ...     adw_id="wf-001",
        ...     event_type=EventType.WORKFLOW_STARTED,
        ...     source="adw_plan_iso",
        ...     message="Starting plan workflow"
        ... )
        >>> bus.publish(event)
    """
    global _event_bus

    if _event_bus is None:
        config = EventBusConfig.from_env()
        _event_bus = create_event_bus(config)

    return _event_bus


def create_event_bus(config: EventBusConfig) -> EventBus:
    """
    Factory for creating event bus from configuration.

    Args:
        config: EventBus configuration

    Returns:
        EventBus instance (backend depends on config)

    Raises:
        ValueError: If unknown backend type

    Example:
        >>> config = EventBusConfig(backend="file", base_dir="agents")
        >>> bus = create_event_bus(config)
    """
    if config.backend == "file":
        return FileEventBus(config.base_dir)
    elif config.backend == "socket":
        # Socket backend implementation in Phase 5D (TUI)
        raise NotImplementedError("SocketEventBus not yet implemented (Phase 5D)")
    elif config.backend == "queue":
        # Queue backend optional (production enhancement)
        raise NotImplementedError("QueueEventBus not yet implemented")
    else:
        raise ValueError(f"Unknown event backend: {config.backend}")


def reset_event_bus() -> None:
    """
    Reset global event bus (for testing).

    Example:
        >>> # In test teardown
        >>> reset_event_bus()
    """
    global _event_bus
    if _event_bus:
        _event_bus.close()
    _event_bus = None


# Public API
__all__ = [
    "ADWEvent",
    "EventType",
    "EventSeverity",
    "EventFilter",
    "EventBus",
    "EventBusConfig",
    "get_event_bus",
    "create_event_bus",
    "reset_event_bus",
]
