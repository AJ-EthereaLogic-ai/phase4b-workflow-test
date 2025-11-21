# ADWS Event Bus

Event-driven architecture for Agentic Data Workflows (ADW).

## Overview

The ADWS Event Bus provides a thread-safe, high-performance event distribution system with support for both synchronous and asynchronous handlers.

## Key Features

### Thread Safety (Phase 3)
- **Copy-on-Write**: Subscribers are snapshotted under lock before event dispatch
- **RLock Protection**: All subscriber operations (subscribe/unsubscribe/publish) are thread-safe
- **No Iteration Corruption**: Concurrent modifications don't cause RuntimeError

### Async Handler Support (Phase 3)
- **Automatic Detection**: Coroutine functions are automatically detected using `inspect.iscoroutinefunction()`
- **Non-Blocking Dispatch**: Handlers execute in background (thread pool or asyncio tasks)
- **Mixed Handlers**: Sync and async handlers can coexist on the same bus

### Handler Execution Strategies

The event bus uses intelligent handler dispatch based on handler type and execution context:

| Handler Type | Event Loop Running? | Dispatch Strategy |
|-------------|---------------------|-------------------|
| Coroutine Function | Yes | `asyncio.create_task()` |
| Coroutine Function | No | Skip with warning |
| Sync Function | ThreadPool Available | `executor.submit()` |
| Sync Function | No ThreadPool | Inline execution |

### Performance Metrics
- **Execution Timing**: All handlers log execution duration
- **Error Isolation**: Handler failures don't affect other subscribers
- **Configurable Concurrency**: `max_workers` controls thread pool size

## Usage

### Basic Event Publishing

```python
from adws.events import get_event_bus, ADWEvent, EventType, EventSeverity

bus = get_event_bus()

event = ADWEvent(
    adw_id="wf-001",
    event_type=EventType.WORKFLOW_STARTED,
    source="workflow_manager",
    severity=EventSeverity.INFO,
    message="Starting workflow"
)

bus.publish(event)  # Non-blocking, handlers run in background
```

### Synchronous Handler

```python
def my_handler(event: ADWEvent):
    """Sync handler - runs in thread pool."""
    print(f"Received: {event.event_type}")
    # Long-running work won't block other handlers

sub_id = bus.subscribe(my_handler)
```

### Asynchronous Handler

```python
async def async_handler(event: ADWEvent):
    """Async handler - runs as asyncio task."""
    await some_async_operation()
    print(f"Processed: {event.event_type}")

# Subscribe async handler
sub_id = bus.subscribe(async_handler)

# Must use publish_async for async handlers
# Note: publish_async waits for all handlers to complete
await bus.publish_async(event)  # Returns after handlers finish
```

**Important**: `publish_async()` waits for all handlers (sync and async) to complete before returning. This ensures event delivery is guaranteed when the await completes. For fire-and-forget behavior, use `publish()` which dispatches handlers in the background.

### Mixed Sync/Async Handlers

```python
def sync_handler(event: ADWEvent):
    """Sync handler."""
    log_to_file(event)

async def async_handler(event: ADWEvent):
    """Async handler."""
    await send_to_websocket(event)

bus.subscribe(sync_handler)    # Runs in thread pool
bus.subscribe(async_handler)   # Runs as asyncio task

# publish_async supports both
await bus.publish_async(event)
```

### Event Filtering

```python
from adws.events import EventFilter

# Only receive errors
error_filter = EventFilter(severities=[EventSeverity.ERROR])
bus.subscribe(error_handler, error_filter)

# Only workflow events
workflow_filter = EventFilter(event_types=[EventType.WORKFLOW_STARTED, EventType.WORKFLOW_COMPLETED])
bus.subscribe(workflow_handler, workflow_filter)
```

### Thread Pool Configuration

```python
from adws.events.bus import BaseEventBus

# Custom thread pool size
bus = MyEventBus(max_workers=20)  # 20 worker threads

# Disable thread pool (inline execution)
bus = MyEventBus(max_workers=0)  # Handlers run synchronously
```

## Thread Safety Guarantees

### Concurrent Subscribe/Unsubscribe
```python
# Safe from multiple threads
thread1: bus.subscribe(handler1)
thread2: bus.subscribe(handler2)
thread3: bus.unsubscribe(sub_id)
# No corruption or RuntimeError
```

### Concurrent Publish
```python
# Safe to publish from multiple threads
thread1: bus.publish(event1)
thread2: bus.publish(event2)
# Events dispatched correctly to all subscribers
```

### Copy-on-Write Protection
```python
# Publish creates snapshot before dispatching
bus.publish(event)  # Snapshot taken here

# New subscriptions don't affect in-flight publish
bus.subscribe(new_handler)  # Safe during publish
```

## Handler Execution Metrics

All handler executions are logged with timing metrics:

```
DEBUG: Handler abc-123 executed successfully for WORKFLOW_STARTED [duration: 45.32ms]
ERROR: Subscriber def-456 error handling WORKFLOW_FAILED: ValueError [duration: 12.45ms]
```

## Best Practices

### 1. Use Async Handlers in Async Context
```python
# ✅ Good: async handler with publish_async
async def handler(event: ADWEvent):
    await process_async(event)

await bus.publish_async(event)

# ❌ Bad: async handler without event loop
bus.publish(event)  # Handler will be skipped with warning
```

### 2. Error Handling in Handlers
```python
# ✅ Good: Let bus handle errors (logged automatically)
def handler(event: ADWEvent):
    result = risky_operation()  # Errors are caught and logged

# ❌ Bad: Swallowing errors silently
def handler(event: ADWEvent):
    try:
        risky_operation()
    except:
        pass  # Error not logged
```

### 3. Resource Cleanup
```python
# For sync cleanup (waits for ThreadPoolExecutor only)
bus.close()

# For async cleanup (waits for ALL handlers including async tasks)
await bus.wait_for_pending_tasks(timeout=5.0)
bus.close()
```

### 4. Thread Pool Sizing
```python
# I/O-bound handlers: Higher worker count
bus = MyEventBus(max_workers=50)

# CPU-bound handlers: Match CPU cores
import os
bus = MyEventBus(max_workers=os.cpu_count())

# Testing: Inline execution for determinism
bus = MyEventBus(max_workers=0)
```

## Performance Characteristics

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| `publish()` | O(n) | n = active subscribers, non-blocking (handlers in background) |
| `publish_async()` | O(n) | Waits for all handlers to complete |
| `subscribe()` | O(1) | Lock acquisition |
| `unsubscribe()` | O(1) | Lock acquisition |
| Handler execution | Background | Thread pool (sync) or asyncio task (async) |

## Implementation Details

### Lock Strategy
- **RLock**: Reentrant lock allows same thread to acquire multiple times
- **Copy-on-Write**: Minimizes lock hold time during publish
- **Lock-Free Dispatch**: Handlers execute outside critical section

### Handler Dispatch Flow
```
publish(event)
    ↓
[Lock] Create subscribers snapshot
    ↓
[Unlock] For each subscriber:
    ↓
Filter event → Match?
    ↓ Yes
Detect handler type
    ↓
┌─────────────┬─────────────┐
│ Coroutine   │ Sync        │
│ Function    │ Function    │
└──────┬──────┴──────┬──────┘
       │             │
Event Loop?    ThreadPool?
       │             │
asyncio.create_task()  executor.submit()
       │             │
       └─────┬───────┘
             ↓
    Background Execution
             ↓
      [Metrics Logged]
```

## Migration from Phase 2

If upgrading from Phase 2 (pre-concurrency):

### Breaking Changes
- **None**: API is fully backward compatible

### New Features
- **Thread Safety**: No changes needed, automatically thread-safe
- **Async Handlers**: Opt-in by defining `async def handler(...)`
- **Thread Pool**: Enabled by default (`max_workers=10`)

### Performance Impact
- **Publish**: Slightly slower due to lock/snapshot (< 1ms overhead)
- **Handler Execution**: Much faster due to parallel execution

## Testing

Comprehensive concurrency tests available:

```bash
# Run all event bus tests
pytest tests/events/test_bus.py

# Run specific test categories
pytest tests/events/test_bus.py -k "concurrency"
pytest tests/events/test_bus.py -k "async"
pytest tests/events/test_bus.py -k "thread_safety"
```

## Troubleshooting

### Async Handler Not Executing
**Problem**: Async handler registered but not being called

**Solution**: Ensure you use `publish_async()` and have an event loop:
```python
# ✅ Correct
await bus.publish_async(event)

# ❌ Wrong: sync publish skips async handlers without event loop
bus.publish(event)
```

### Handlers Blocking Each Other
**Problem**: One slow handler blocks all others

**Solution**: Increase `max_workers` or check if thread pool is disabled:
```python
# Increase thread pool
bus = MyEventBus(max_workers=20)

# Check current setting
print(bus._max_workers)
```

### Memory Leaks with Subscribers
**Problem**: Subscribers not being cleaned up

**Solution**: Always unsubscribe when done:
```python
sub_id = bus.subscribe(handler)
try:
    # ... use handler ...
finally:
    bus.unsubscribe(sub_id)
```

## See Also

- **Architecture**: See `docs/design/EVENT_STREAMING_DESIGN.md` for system design
- **Integration**: See `docs/design/INTEGRATION_ARCHITECTURE_DESIGN.md` for event bus integration patterns
- **API Reference**: See docstrings in `adws/events/bus.py`
