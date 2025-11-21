"""
EventBus Protocol and BaseEventBus implementation.

This module provides:
- EventBus Protocol: Standard interface for all event bus implementations
- BaseEventBus: Base class with common subscriber management and routing logic
"""

from typing import Protocol, Callable, Optional, Dict
from adws.events.models import ADWEvent
from adws.events.filters import EventFilter
import uuid
import logging
import asyncio
import threading
import time
import inspect
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor


logger = logging.getLogger(__name__)


class EventBus(Protocol):
    """
    Event publication and subscription interface.

    All EventBus implementations (File, Socket, Queue) must implement this protocol.

    Design Principles:
    - Non-blocking: publish() should not block workflow execution
    - Error isolation: Subscriber errors must not affect other subscribers or publisher
    - Filtering: Support event filtering for targeted subscriptions
    - Async support: Both sync and async publication methods

    Implementation Requirement:
    - Implementations must handle subscriber errors gracefully
    - Failed subscribers should be logged but not propagate errors
    - Event publication must complete even if some subscribers fail
    """

    def publish(self, event: ADWEvent) -> None:
        """
        Publish event to all subscribers (synchronous).

        Args:
            event: Event to publish

        Implementation Notes:
        - Must be non-blocking (<5ms overhead target)
        - Subscriber errors must not affect other subscribers
        - Should call _publish_to_backend() for persistence/streaming

        Example:
            >>> bus = FileEventBus()
            >>> event = ADWEvent(adw_id="wf-001", event_type=EventType.WORKFLOW_STARTED, ...)
            >>> bus.publish(event)  # Returns immediately, event written to file
        """
        ...

    async def publish_async(self, event: ADWEvent) -> None:
        """
        Publish event asynchronously and wait for handler completion.

        Args:
            event: Event to publish

        Implementation Notes:
        - For async workflows, use this for proper async handler support
        - BaseEventBus implementation awaits all handlers and backend work
        - Handlers execute concurrently but publish_async waits for completion

        Example:
            >>> bus = SocketEventBus()
            >>> event = ADWEvent(...)
            >>> await bus.publish_async(event)  # Waits for handlers + backend
        """
        ...

    def subscribe(
        self,
        handler: Callable[[ADWEvent], None],
        event_filter: Optional[EventFilter] = None
    ) -> str:
        """
        Subscribe to events with optional filtering.

        Args:
            handler: Callback function to handle matching events
            event_filter: Optional filter (None = receive all events)

        Returns:
            Subscription ID (UUID) for unsubscribing

        Handler Signature:
            def handler(event: ADWEvent) -> None:
                # Process event
                # Errors in handler will be caught and logged

        Example:
            >>> def my_handler(event: ADWEvent):
            ...     print(f"Received: {event.event_type}")
            >>>
            >>> # Subscribe to all events
            >>> sub_id = bus.subscribe(my_handler)
            >>>
            >>> # Subscribe to only errors
            >>> error_filter = EventFilter(severities=[EventSeverity.ERROR])
            >>> sub_id = bus.subscribe(my_handler, error_filter)
        """
        ...

    def unsubscribe(self, subscription_id: str) -> None:
        """
        Unsubscribe from events.

        Args:
            subscription_id: ID returned by subscribe()

        Example:
            >>> sub_id = bus.subscribe(handler)
            >>> bus.unsubscribe(sub_id)  # Stop receiving events
        """
        ...

    def close(self) -> None:
        """
        Close event bus and cleanup resources.

        Implementation Notes:
        - Close file handles, sockets, connections
        - Flush pending events
        - Stop background threads (waits for ThreadPoolExecutor)
        - May log warning if async tasks are pending
        - For async cleanup, call await bus.wait_for_pending_tasks() first

        Example:
            >>> bus = SocketEventBus()
            >>> # ... use bus ...
            >>> bus.close()  # Cleanup (waits for sync handlers)
        """
        ...


class BaseEventBus:
    """
    Base event bus implementation with common functionality.

    Provides:
    - Subscriber management (subscribe/unsubscribe)
    - Event filtering and routing
    - Error isolation (subscriber failures don't affect others)
    - Async wrapper methods
    - Thread-safe concurrent access
    - Async handler support with non-blocking dispatch

    Subclasses must implement:
    - _publish_to_backend(event): Backend-specific event persistence/streaming

    Thread Safety:
    - All subscriber operations are protected with threading.RLock()
    - Publish operations use copy-on-write to avoid holding locks during handler execution

    Handler Execution:
    - Async handlers (coroutine functions) are dispatched via asyncio.create_task()
    - Sync handlers are dispatched via ThreadPoolExecutor to avoid blocking
    - Handler errors are logged with execution metrics

    Usage:
        class MyEventBus(BaseEventBus):
            def _publish_to_backend(self, event: ADWEvent) -> None:
                # Custom backend implementation
                pass
    """

    def __init__(self, max_workers: int = 10):
        """
        Initialize base event bus with empty subscriber registry.

        Args:
            max_workers: Maximum thread pool workers for sync handler dispatch.
                        Default is 10. Set to 0 to disable thread pool (handlers run inline).
        """
        self.subscribers: Dict[str, tuple[Callable, Optional[EventFilter]]] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers) if max_workers > 0 else None
        self._max_workers = max_workers
        self._background_tasks: set = set()  # Track async tasks for cleanup

    def publish(self, event: ADWEvent) -> None:
        """
        Publish event to all matching subscribers.

        Algorithm:
            1. Take snapshot of subscribers (copy-on-write with lock)
            2. For each subscriber:
               a. Apply event filter (if any)
               b. If event matches filter, dispatch handler asynchronously
               c. Catch and log any handler errors (don't propagate)
            3. Call _publish_to_backend() for persistence/streaming

        Thread Safety:
        - Uses lock to create snapshot of subscribers
        - Handlers execute outside lock to prevent deadlock

        Handler Dispatch:
        - Async handlers (coroutine functions) → asyncio.create_task() if event loop available
        - Sync handlers → ThreadPoolExecutor.submit() for non-blocking execution
        - Fallback to inline execution if no executor or event loop

        Error Handling:
        - Subscriber errors are logged with execution metrics
        - Backend errors are logged but don't affect subscribers
        """
        # Copy-on-write: snapshot subscribers while holding lock
        with self._lock:
            subscribers_snapshot = dict(self.subscribers)

        # Route to subscribers (outside lock to prevent deadlock)
        for sub_id, (handler, event_filter) in subscribers_snapshot.items():
            # Apply filter
            if event_filter and not event_filter.matches(event):
                continue

            # Dispatch handler with metrics
            self._dispatch_handler(sub_id, handler, event)

        # Backend-specific publication (file write, socket send, queue push)
        try:
            self._publish_to_backend(event)
        except Exception as e:
            self.logger.error(
                f"Backend publication error for {event.event_type}: {e}",
                exc_info=True
            )
            # Don't propagate backend errors to workflow

    def _dispatch_handler(self, sub_id: str, handler: Callable, event: ADWEvent) -> None:
        """
        Dispatch handler with appropriate execution strategy.

        Strategy:
        1. If handler is coroutine function AND event loop is running:
           → asyncio.create_task() for async execution
        2. Else if ThreadPoolExecutor is available:
           → executor.submit() for non-blocking execution
        3. Else:
           → Inline execution (synchronous fallback)

        Args:
            sub_id: Subscription ID for logging
            handler: Handler callable
            event: Event to pass to handler

        Metrics:
        - Logs execution time and any errors
        """
        start_time = time.time()

        try:
            # Check if handler is async coroutine function
            if inspect.iscoroutinefunction(handler):
                # Try to get running event loop
                try:
                    asyncio.get_running_loop()
                    # Schedule async handler as task
                    asyncio.create_task(
                        self._execute_async_handler(sub_id, handler, event, start_time)
                    )
                    return  # Task scheduled, don't wait
                except RuntimeError:
                    # No event loop running, log warning and skip
                    self.logger.warning(
                        f"Async handler {sub_id} skipped (no event loop running). "
                        f"Use publish_async() for async handlers."
                    )
                    return

            # Sync handler: dispatch via thread pool if available
            if self._executor:
                self._executor.submit(self._execute_sync_handler, sub_id, handler, event, start_time)
            else:
                # Inline execution (fallback)
                self._execute_sync_handler(sub_id, handler, event, start_time)

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"Handler dispatch error for {sub_id} ({event.event_type}): {e} "
                f"[duration: {duration*1000:.2f}ms]",
                exc_info=True
            )

    def _execute_sync_handler(self, sub_id: str, handler: Callable, event: ADWEvent, start_time: float) -> None:
        """Execute synchronous handler with error handling and metrics."""
        try:
            handler(event)
            duration = time.time() - start_time
            self.logger.debug(
                f"Handler {sub_id} executed successfully for {event.event_type} "
                f"[duration: {duration*1000:.2f}ms]"
            )
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"Subscriber {sub_id} error handling {event.event_type}: {e} "
                f"[duration: {duration*1000:.2f}ms]",
                exc_info=True
            )

    async def _execute_async_handler(self, sub_id: str, handler: Callable, event: ADWEvent, start_time: float) -> None:
        """Execute asynchronous handler with error handling and metrics."""
        try:
            await handler(event)
            duration = time.time() - start_time
            self.logger.debug(
                f"Async handler {sub_id} executed successfully for {event.event_type} "
                f"[duration: {duration*1000:.2f}ms]"
            )
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"Async subscriber {sub_id} error handling {event.event_type}: {e} "
                f"[duration: {duration*1000:.2f}ms]",
                exc_info=True
            )

    @abstractmethod
    def _publish_to_backend(self, event: ADWEvent) -> None:
        """
        Backend-specific event publication.

        Subclasses must implement this method.

        Args:
            event: Event to publish to backend

        Examples:
            # FileEventBus: Write to JSONL file
            # SocketEventBus: Send over socket
            # QueueEventBus: Push to Redis/RabbitMQ
        """
        raise NotImplementedError("Subclasses must implement _publish_to_backend()")

    def subscribe(
        self,
        handler: Callable[[ADWEvent], None],
        event_filter: Optional[EventFilter] = None
    ) -> str:
        """
        Subscribe to events (thread-safe).

        Args:
            handler: Callable to handle events (sync or async coroutine function)
            event_filter: Optional filter for event matching

        Returns:
            UUID subscription ID

        Thread Safety:
        - Uses lock to protect subscriber registration
        """
        sub_id = str(uuid.uuid4())

        with self._lock:
            self.subscribers[sub_id] = (handler, event_filter)

        handler_type = "async" if inspect.iscoroutinefunction(handler) else "sync"
        self.logger.info(
            f"Subscriber {sub_id} registered "
            f"(type: {handler_type}, filter: {event_filter is not None})"
        )
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """
        Unsubscribe from events (thread-safe).

        Args:
            subscription_id: ID returned by subscribe()

        Thread Safety:
        - Uses lock to protect subscriber removal
        """
        with self._lock:
            if subscription_id in self.subscribers:
                self.subscribers.pop(subscription_id)
                self.logger.info(f"Subscriber {subscription_id} unregistered")

    async def publish_async(self, event: ADWEvent) -> None:
        """
        Publish event asynchronously and wait for all handlers to complete.

        This method properly handles both sync and async handlers:
        - Async handlers are awaited directly
        - Sync handlers are dispatched via the bus's thread pool executor
        - Backend publication is done in thread pool
        - Waits for all handler and backend work before returning

        Thread Safety:
        - Uses same lock-based copy-on-write as sync publish()
        - Sync handlers use the bus's ThreadPoolExecutor (respects max_workers)

        Args:
            event: Event to publish
        """
        # Copy-on-write: snapshot subscribers while holding lock
        with self._lock:
            subscribers_snapshot = dict(self.subscribers)

        # Collect all handler tasks
        handler_tasks = []

        # Route to subscribers (outside lock to prevent deadlock)
        for sub_id, (handler, event_filter) in subscribers_snapshot.items():
            # Apply filter
            if event_filter and not event_filter.matches(event):
                continue

            # Create handler task (will be awaited)
            task = asyncio.create_task(self._dispatch_handler_async(sub_id, handler, event))
            handler_tasks.append(task)

            # Track task for cleanup
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        # Wait for all handlers to complete
        if handler_tasks:
            await asyncio.gather(*handler_tasks, return_exceptions=True)

        # Backend-specific publication (in thread pool)
        try:
            await asyncio.to_thread(self._publish_to_backend, event)
        except Exception as e:
            self.logger.error(
                f"Backend publication error for {event.event_type}: {e}",
                exc_info=True
            )
            # Don't propagate backend errors to workflow

    async def _dispatch_handler_async(self, sub_id: str, handler: Callable, event: ADWEvent) -> None:
        """
        Dispatch handler asynchronously (for use in async context).

        Strategy:
        1. If handler is coroutine function:
           → await it directly
        2. Else (sync handler):
           → run in bus's thread pool via loop.run_in_executor()

        Args:
            sub_id: Subscription ID for logging
            handler: Handler callable
            event: Event to pass to handler

        Metrics:
        - Logs execution time and any errors

        Thread Pool:
        - Sync handlers use the bus's ThreadPoolExecutor (respects max_workers)
        """
        start_time = time.time()

        try:
            # Check if handler is async coroutine function
            if inspect.iscoroutinefunction(handler):
                # Await async handler directly
                await self._execute_async_handler(sub_id, handler, event, start_time)
            else:
                # Run sync handler in bus's thread pool (respects max_workers)
                if self._executor:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        self._executor,
                        self._execute_sync_handler,
                        sub_id, handler, event, start_time
                    )
                else:
                    # No executor, run inline
                    self._execute_sync_handler(sub_id, handler, event, start_time)

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"Handler dispatch error for {sub_id} ({event.event_type}): {e} "
                f"[duration: {duration*1000:.2f}ms]",
                exc_info=True
            )

    async def wait_for_pending_tasks(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all pending async handler tasks to complete.

        Args:
            timeout: Optional timeout in seconds. If None, waits indefinitely.

        Returns:
            True if all tasks completed, False if timeout occurred

        Usage:
            >>> await bus.wait_for_pending_tasks(timeout=5.0)
        """
        if not self._background_tasks:
            return True

        try:
            if timeout:
                await asyncio.wait_for(
                    asyncio.gather(*list(self._background_tasks), return_exceptions=True),
                    timeout=timeout
                )
            else:
                await asyncio.gather(*list(self._background_tasks), return_exceptions=True)
            return True
        except asyncio.TimeoutError:
            self.logger.warning(
                f"Timeout waiting for {len(self._background_tasks)} pending handler tasks"
            )
            return False

    def close(self) -> None:
        """
        Close event bus and cleanup resources.

        Cleanup:
        - Clears all subscribers
        - Shuts down ThreadPoolExecutor (waits for pending sync handlers)
        - Subclasses should override to add backend-specific cleanup

        Thread Safety:
        - Uses lock to protect subscriber cleanup

        Note:
        - This does NOT wait for async tasks scheduled via asyncio.create_task.
        - Use await bus.wait_for_pending_tasks() before close() if needed.
        - For async cleanup, consider using async with bus: pattern in future.
        """
        with self._lock:
            self.subscribers.clear()

        # Shutdown executor and wait for pending sync handlers
        if self._executor:
            self.logger.info("Shutting down handler thread pool...")
            self._executor.shutdown(wait=True)
            self._executor = None

        # Log warning if async tasks are still pending
        if self._background_tasks:
            self.logger.warning(
                f"Closing with {len(self._background_tasks)} pending async tasks. "
                f"Consider calling await bus.wait_for_pending_tasks() first."
            )

        self.logger.info("EventBus closed")
