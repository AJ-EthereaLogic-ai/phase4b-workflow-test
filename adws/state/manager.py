"""
ADWS v2.0 State Management - StateManager

This module implements the core StateManager class for workflow lifecycle
tracking and orchestration state management using SQLite with dual-write
to JSON for resilience.

Issue: #1 - StateManager SQLite Schema & Core CRUD Operations
Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence

Key Responsibilities:
- Initialize SQLite database with schema
- Create workflows with unique ID generation
- Retrieve workflow state by ID
- Update workflow state and metrics
- Delete workflows with cascade cleanup
- Manage database connections async/await
- Coordinate dual-write to SQLite and JSON backends

Design Principles:
- Async/await throughout for non-blocking operations
- Type-safe with strict mypy compliance
- Explicit error handling with meaningful messages
- Performance optimized (<10ms for CRUD operations)
- Dual-write ensures data resilience
"""

import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional

import aiosqlite

from adws.state.lifecycle import WorkflowLifecycle
from adws.state.models import IssueClass, ModelSet, WorkflowState, WorkflowType
from adws.state.persistence import HybridPersistence, JSONBackend, SQLiteBackend


class StateManager:
    """
    Manages workflow state using SQLite database.

    Provides async CRUD operations for workflow lifecycle tracking.
    Handles schema initialization, connection management, and data persistence.

    Usage:
        async with StateManager(db_path=Path(".adws/workflows.db")) as manager:
            await manager.initialize()

            workflow_id = await manager.create_workflow(
                name="my-workflow",
                workflow_type=WorkflowType.STANDARD,
                tags=["feature", "api"]
            )

            workflow = await manager.get_workflow(workflow_id)
            await manager.update_workflow(
                workflow_id=workflow_id,
                state=WorkflowLifecycle.RUNNING
            )
    """

    def __init__(
        self,
        db_path: Path,
        json_dir: Optional[Path] = None,
        event_bus: Optional[Any] = None
    ) -> None:
        """
        Initialize StateManager with database path and optional JSON directory.

        Args:
            db_path: Path to SQLite database file
            json_dir: Directory for JSON backup files (defaults to db_path.parent / "workflows_json")
            event_bus: Optional EventBus for event emission (Issue #12)
        """
        resolved_db_path = Path(db_path)
        self.db_path = resolved_db_path
        self._conn: Optional[aiosqlite.Connection] = None

        # Setup JSON directory
        if json_dir is None:
            self.json_dir = resolved_db_path.parent / "workflows_json"
        else:
            self.json_dir = Path(json_dir)

        # Initialize persistence backends
        # Note: SQLiteBackend will be created lazily after initialization
        # to avoid circular dependency issues
        self._persistence: Optional[HybridPersistence] = None

        # Event integration (Issue #12)
        self.event_bus = event_bus
        self._event_emitter: Optional[Any] = None
        if event_bus is not None:
            from adws.workflows.events import WorkflowEventEmitter
            self._event_emitter = WorkflowEventEmitter(event_bus)

    async def __aenter__(self) -> "StateManager":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager and close connection."""
        await self.close()

    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """
        Get database connection context manager.

        Yields:
            Active database connection

        Note:
            This uses the existing connection or creates a new one if needed.
        """
        if self._conn is None:
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row

        yield self._conn

    @property
    def persistence(self) -> HybridPersistence:
        """
        Get the HybridPersistence instance.

        Returns:
            HybridPersistence instance for dual-write operations

        Raises:
            RuntimeError: If persistence not initialized (call initialize() first)
        """
        if self._persistence is None:
            raise RuntimeError(
                "Persistence layer not initialized. Call initialize() first."
            )
        return self._persistence

    @property
    def event_emitter(self) -> Optional[Any]:
        """
        Get the WorkflowEventEmitter instance.

        Returns:
            WorkflowEventEmitter if event_bus was provided, None otherwise

        Example:
            >>> manager = StateManager(db_path="workflows.db", event_bus=bus)
            >>> if manager.event_emitter:
            ...     manager.event_emitter.emit_workflow_started(...)
        """
        return self._event_emitter

    async def initialize(self) -> None:
        """
        Initialize database and create schema.

        Creates parent directories if needed, then executes schema DDL to create
        all tables, indexes, and views. Also initializes the dual-write
        persistence layer.

        Performance: Should complete in <1 second.

        Raises:
            OSError: If directory creation fails
            aiosqlite.Error: If schema creation fails
        """
        # Create parent directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)

        # Read schema SQL file
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text()

        # Execute schema
        async with self._get_connection() as conn:
            await conn.executescript(schema_sql)
            await conn.commit()

        # Initialize persistence backends after DB schema is ready
        sqlite_backend = SQLiteBackend(self)
        json_backend = JSONBackend(self.json_dir)
        self._persistence = HybridPersistence(sqlite_backend, json_backend)

    async def close(self) -> None:
        """
        Close database connection.

        Safe to call multiple times. Does nothing if connection is already closed.
        """
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _generate_workflow_id(self) -> str:
        """
        Generate a unique workflow ID.

        Uses secrets.token_urlsafe for cryptographically strong random ID generation.

        Returns:
            URL-safe random string (22 characters)
        """
        return secrets.token_urlsafe(16)

    async def create_workflow(
        self,
        name: str,
        workflow_type: WorkflowType,
        tags: list[str],
        issue_number: Optional[int] = None,
        branch_name: Optional[str] = None,
        base_branch: str = "main",
        worktree_path: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        backend_port: Optional[int] = None,
        frontend_port: Optional[int] = None,
        issue_class: Optional[IssueClass] = None,
        model_set: ModelSet = ModelSet.BASE,
        phase_count: int = 0,
    ) -> str:
        """
        Create a new workflow and return its ID.

        Phase 1 implementation includes critical tac-7 integration fields.
        Phase 2 adds dual-write to SQLite and JSON for resilience.

        Args:
            name: Human-readable workflow name
            workflow_type: Type of workflow (standard, tdd, etc.)
            tags: List of categorization tags
            issue_number: GitHub issue number (tac-7 integration)
            branch_name: Git branch name (tac-7 integration)
            base_branch: Base branch for PR (default: main)
            worktree_path: Git worktree path (tac-7 integration)
            metadata: Additional metadata dictionary
            backend_port: Reserved backend dev-server port (Phase 3)
            frontend_port: Reserved frontend dev-server port (Phase 3)
            issue_class: Issue classification for analytics (Phase 3)
            model_set: Model selection for execution (Phase 3)
            phase_count: Number of executed phases (Phase 3)

        Returns:
            Generated workflow ID

        Performance: Should complete in <10ms.

        Raises:
            aiosqlite.Error: If database insert fails
            PersistenceError: If dual-write fails
        """
        workflow_id = self._generate_workflow_id()
        now = datetime.now(timezone.utc)

        # Serialize JSON fields
        tags_json = json.dumps(tags)
        metadata_json = json.dumps(metadata) if metadata else "{}"

        # Insert into SQLite first
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO workflows (
                    workflow_id,
                    workflow_name,
                    state,
                    workflow_type,
                    issue_number,
                    branch_name,
                    base_branch,
                    worktree_path,
                    tags,
                    metadata,
                    created_at,
                    last_activity_at,
                    retry_count,
                    cost_usd,
                    total_tokens,
                    backend_port,
                    frontend_port,
                    issue_class,
                    model_set,
                    phase_count
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    workflow_id,
                    name,
                    WorkflowLifecycle.CREATED.value,
                    workflow_type.value,
                    issue_number,
                    branch_name,
                    base_branch,
                    worktree_path,
                    tags_json,
                    metadata_json,
                    now.isoformat(),
                    now.isoformat(),
                    0,
                    0.0,
                    0,
                    backend_port,
                    frontend_port,
                    issue_class.value if issue_class else None,
                    model_set.value,
                    phase_count,
                ),
            )
            await conn.commit()

        # Load the workflow and write to JSON (dual-write)
        workflow = await self.get_workflow(workflow_id)
        if workflow is not None:
            # Write directly to JSON (skip SQLite since we just wrote there)
            self.persistence.json.save_workflow(workflow)

            # Emit WORKFLOW_STARTED event (Issue #12)
            if self._event_emitter is not None:
                self._event_emitter.emit_workflow_started(
                    adw_id=workflow_id,
                    workflow_name=name,
                    workflow_type=workflow_type.value,
                    initial_state={
                        "state": WorkflowLifecycle.CREATED.value,
                        "workflow_name": name,
                        "workflow_type": workflow_type.value,
                        "tags": tags,
                        "issue_number": issue_number,
                        "branch_name": branch_name,
                    }
                )

        return workflow_id

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """
        Retrieve workflow state by ID.

        Phase 1 implementation retrieves all Phase 1 fields including
        tac-7 integration fields.

        Args:
            workflow_id: Unique workflow identifier

        Returns:
            WorkflowState if found, None if not found

        Performance: Should complete in <10ms.

        Raises:
            aiosqlite.Error: If database query fails
        """
        async with self._get_connection() as conn:
            cursor = await conn.execute(
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
                    total_tokens,
                    backend_port,
                    frontend_port,
                    issue_class,
                    model_set,
                    phase_count
                FROM workflows
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        # Convert row to dict for Pydantic model
        row_dict = dict(row)

        # Pydantic model validators will handle JSON parsing and datetime conversion
        return WorkflowState(**row_dict)

    async def update_workflow(
        self,
        workflow_id: str,
        state: Optional[WorkflowLifecycle] = None,
        error_message: Optional[str] = None,
        cost_usd: Optional[float] = None,
        total_tokens: Optional[int] = None,
        backend_port: Optional[int] = None,
        frontend_port: Optional[int] = None,
        issue_class: Optional[IssueClass] = None,
        model_set: Optional[ModelSet] = None,
        phase_count: Optional[int] = None,
    ) -> None:
        """
        Update workflow state and metrics.

        Automatically updates last_activity_at timestamp.
        Sets started_at when transitioning to RUNNING.
        Sets completed_at when transitioning to terminal states.

        Phase 1 implementation uses cost_usd field (renamed from total_cost).

        Args:
            workflow_id: Workflow identifier to update
            state: New workflow state (optional)
            error_message: Error message if failed (optional)
            cost_usd: Total workflow cost in USD (optional)
            total_tokens: Total tokens used (optional)
            backend_port: Backend dev-server port (optional)
            frontend_port: Frontend dev-server port (optional)
            issue_class: Issue classification (optional)
            model_set: Model selection (optional)
            phase_count: Number of executed phases (optional)

        Performance: Should complete in <10ms.

        Raises:
            ValueError: If workflow not found
            aiosqlite.Error: If database update fails
        """
        # Verify workflow exists
        existing = await self.get_workflow(workflow_id)
        if existing is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # Build dynamic UPDATE query based on provided fields
        updates: list[str] = ["last_activity_at = ?"]
        params: list[Any] = [now_iso]

        if state is not None:
            updates.append("state = ?")
            params.append(state.value)

            # Define terminal states
            terminal_states = {
                WorkflowLifecycle.COMPLETED,
                WorkflowLifecycle.FAILED,
                WorkflowLifecycle.CANCELLED,
                WorkflowLifecycle.ARCHIVED,
            }

            # States that require started_at to be set
            needs_started_states = {
                WorkflowLifecycle.RUNNING,
                WorkflowLifecycle.PAUSED,
            } | terminal_states

            # Set started_at when transitioning to states that require it
            if state in needs_started_states and existing.started_at is None:
                updates.append("started_at = ?")
                params.append(now_iso)

            # Set completed_at when transitioning to terminal states
            if state in terminal_states and existing.completed_at is None:
                updates.append("completed_at = ?")
                params.append(now_iso)

            if state == WorkflowLifecycle.ARCHIVED and existing.archived_at is None:
                updates.append("archived_at = ?")
                params.append(now_iso)

        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if cost_usd is not None:
            updates.append("cost_usd = ?")
            params.append(cost_usd)

        if total_tokens is not None:
            updates.append("total_tokens = ?")
            params.append(total_tokens)

        if backend_port is not None:
            updates.append("backend_port = ?")
            params.append(backend_port)

        if frontend_port is not None:
            updates.append("frontend_port = ?")
            params.append(frontend_port)

        if issue_class is not None:
            updates.append("issue_class = ?")
            params.append(issue_class.value)

        if model_set is not None:
            updates.append("model_set = ?")
            params.append(model_set.value)

        if phase_count is not None:
            updates.append("phase_count = ?")
            params.append(phase_count)

        # Add workflow_id to params for WHERE clause
        params.append(workflow_id)

        # Execute update in SQLite
        async with self._get_connection() as conn:
            await conn.execute(
                f"""
                UPDATE workflows
                SET {', '.join(updates)}
                WHERE workflow_id = ?
                """,
                params,
            )
            await conn.commit()

        # Dual-write to JSON
        updated_workflow = await self.get_workflow(workflow_id)
        if updated_workflow is not None:
            # Write directly to JSON (skip SQLite since we just wrote there)
            self.persistence.json.save_workflow(updated_workflow)

            # Emit events (Issue #12)
            if self._event_emitter is not None:
                # Emit cost/usage update if metrics changed
                metrics_changed = False
                cost_changed = False
                tokens_changed = False
                if cost_usd is not None and cost_usd != existing.cost_usd:
                    metrics_changed = True
                    cost_changed = True
                if total_tokens is not None and total_tokens != existing.total_tokens:
                    metrics_changed = True
                    tokens_changed = True

                if metrics_changed:
                    self._event_emitter.emit_cost_updated(
                        adw_id=workflow_id,
                        cost_usd=updated_workflow.cost_usd if cost_changed else None,
                        total_tokens=updated_workflow.total_tokens if tokens_changed else None,
                        update_metadata={},
                    )
                # Emit state transition event if state changed
                if state is not None and state != existing.state:
                    self._event_emitter.emit_state_transition(
                        adw_id=workflow_id,
                        from_state=existing.state,
                        to_state=state,
                        transition_metadata={}
                    )

                    # Emit specific lifecycle events
                    if state == WorkflowLifecycle.COMPLETED:
                        duration = 0.0
                        if updated_workflow.started_at and updated_workflow.completed_at:
                            duration = (
                                updated_workflow.completed_at - updated_workflow.started_at
                            ).total_seconds()

                        self._event_emitter.emit_workflow_completed(
                            adw_id=workflow_id,
                            duration_seconds=duration,
                            final_state={
                                "state": state.value,
                                "exit_code": updated_workflow.exit_code,
                            },
                            metrics={
                                "cost_usd": updated_workflow.cost_usd,
                                "total_tokens": updated_workflow.total_tokens,
                            }
                        )

                    elif state == WorkflowLifecycle.FAILED:
                        self._event_emitter.emit_workflow_failed(
                            adw_id=workflow_id,
                            error_message=error_message or "Workflow failed",
                            error_type=None,
                            final_state={
                                "state": state.value,
                                "exit_code": updated_workflow.exit_code,
                            },
                            metrics={
                                "cost_usd": updated_workflow.cost_usd,
                                "total_tokens": updated_workflow.total_tokens,
                            }
                        )

                    elif state == WorkflowLifecycle.PAUSED:
                        self._event_emitter.emit_workflow_paused(
                            adw_id=workflow_id,
                            reason="state_transition",
                            pause_metadata={}
                        )

    async def query_workflows_by_state_and_time(
        self,
        state: WorkflowLifecycle,
        started_before: datetime
    ) -> List[WorkflowState]:
        """
        Query workflows by state with started_at before cutoff time.

        This is a minimal query method for Phase 2 stuck detection.
        Phase 3 will add comprehensive WorkflowFilter API.

        Args:
            state: Workflow state to query
            started_before: Maximum started_at time

        Returns:
            List of workflows matching criteria

        Example:
            >>> one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            >>> stuck = await manager.query_workflows_by_state_and_time(
            ...     WorkflowLifecycle.RUNNING,
            ...     one_hour_ago
            ... )
            >>> print(f"Found {len(stuck)} stuck workflows")
        """
        async with self._get_connection() as conn:
            cursor = await conn.execute(
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
                    total_tokens,
                    backend_port,
                    frontend_port,
                    issue_class,
                    model_set,
                    phase_count
                FROM workflows
                WHERE state = ? AND started_at IS NOT NULL AND started_at < ?
                """,
                (state.value, started_before.isoformat())
            )

            rows = await cursor.fetchall()

        workflows = []
        for row in rows:
            row_dict = dict(row)
            workflows.append(WorkflowState(**row_dict))

        return workflows

    async def delete_workflow(self, workflow_id: str) -> None:
        """
        Delete workflow from database.

        Cascades to delete related phases and events due to foreign key constraints.

        Args:
            workflow_id: Workflow identifier to delete

        Raises:
            ValueError: If workflow not found
            aiosqlite.Error: If database delete fails
        """
        # Verify workflow exists
        existing = await self.get_workflow(workflow_id)
        if existing is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        async with self._get_connection() as conn:
            await conn.execute(
                "DELETE FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            )
            await conn.commit()

    async def transition_to(
        self,
        workflow_id: str,
        new_state: WorkflowLifecycle
    ) -> "StateTransitionResult":  # type: ignore[name-defined]
        """
        Transition workflow to new state with validation.

        Validates the state transition against the VALID_TRANSITIONS matrix
        before applying the change. This is the recommended method for
        changing workflow states as it enforces state machine rules.

        Args:
            workflow_id: Workflow identifier
            new_state: Target workflow state

        Returns:
            StateTransitionResult with validation outcome

        Raises:
            ValueError: If workflow not found
            StateTransitionError: If transition is invalid

        Example:
            >>> result = await manager.transition_to("wf-123", WorkflowLifecycle.RUNNING)
            >>> if result.valid:
            ...     print("Transition successful")
            ... else:
            ...     print(f"Transition failed: {result.error_message}")

        Note:
            This method validates but does not rollback on failure.
            Use transition_with_rollback() for transactional behavior.
        """
        from adws.state.exceptions import StateTransitionError
        from adws.state.validators import StateTransitionValidator

        # Load current workflow state
        workflow = await self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Validate transition
        validator = StateTransitionValidator()
        result = validator.validate_transition(
            workflow.state,
            new_state,
            workflow_id
        )

        if not result.valid:
            raise StateTransitionError(
                result.error_message or "Invalid state transition",
                from_state=workflow.state.value,
                to_state=new_state.value,
                allowed_transitions={s.value for s in result.allowed_transitions}
            )

        # Perform state transition
        await self.update_workflow(
            workflow_id=workflow_id,
            state=new_state
        )

        # Emit WORKFLOW_RESUMED if transitioning from PAUSED to RUNNING (Issue #12)
        if (self._event_emitter is not None and
            workflow.state == WorkflowLifecycle.PAUSED and
            new_state == WorkflowLifecycle.RUNNING):
            updated = await self.get_workflow(workflow_id)
            if updated:
                self._event_emitter.emit_workflow_resumed(
                    adw_id=workflow_id,
                    resumed_from_state={
                        "state": WorkflowLifecycle.PAUSED.value,
                        "phase_count": updated.phase_count,
                    },
                    resume_metadata={}
                )

        return result

    async def transition_with_rollback(
        self,
        workflow_id: str,
        new_state: WorkflowLifecycle
    ) -> "StateTransitionResult":  # type: ignore[name-defined]
        """
        Transition workflow to new state with transactional rollback on failure.

        This method provides transaction-like semantics for state transitions.
        If the transition validation fails or the database update fails, the
        workflow state remains unchanged.

        Args:
            workflow_id: Workflow identifier
            new_state: Target workflow state

        Returns:
            StateTransitionResult with validation outcome

        Raises:
            ValueError: If workflow not found
            StateTransitionError: If transition is invalid
            aiosqlite.Error: If database update fails

        Example:
            >>> try:
            ...     result = await manager.transition_with_rollback(
            ...         "wf-123",
            ...         WorkflowLifecycle.COMPLETED
            ...     )
            ...     print("Transition successful")
            ... except StateTransitionError as e:
            ...     print(f"Invalid transition: {e}")
            ... except Exception as e:
            ...     print(f"Database error: {e}")

        Note:
            This method uses the database connection's transaction support
            to ensure atomicity. If any error occurs, the state change is
            rolled back automatically.
        """
        from adws.state.exceptions import StateTransitionError
        from adws.state.validators import StateTransitionValidator

        # Load current workflow state
        workflow = await self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Store original state for potential rollback logging
        original_state = workflow.state

        # Validate transition
        validator = StateTransitionValidator()
        result = validator.validate_transition(
            workflow.state,
            new_state,
            workflow_id
        )

        if not result.valid:
            raise StateTransitionError(
                result.error_message or "Invalid state transition",
                from_state=workflow.state.value,
                to_state=new_state.value,
                allowed_transitions={s.value for s in result.allowed_transitions}
            )

        # Perform state transition with explicit transaction
        try:
            async with self._get_connection() as conn:
                # Begin transaction
                await conn.execute("BEGIN TRANSACTION")

                try:
                    # Update workflow state
                    await self.update_workflow(
                        workflow_id=workflow_id,
                        state=new_state
                    )
                    # Commit transaction
                    await conn.commit()

                except Exception as e:
                    # Rollback on any error
                    await conn.rollback()
                    raise

        except Exception as e:
            # Log rollback
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"State transition rolled back for {workflow_id}: "
                f"{original_state.value} → {new_state.value}. Error: {e}"
            )
            raise

        return result
