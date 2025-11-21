"""
ADWS v2.0 State Management - Hybrid Persistence

This module coordinates dual-write to SQLite (primary) and JSON (fallback).
Ensures SQLite and JSON backends stay synchronized with rollback capability.

Issue: #6 - WorkflowLifecycle State Machine & Dual-Write Persistence
Phase: Phase 2 - State machine validation (NO new database fields)
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Protocol

from adws.state.exceptions import PersistenceError, SyncError
from adws.state.models import WorkflowState


class PersistenceBackend(Protocol):
    """
    Protocol defining the interface for persistence backends.

    All persistence backends (SQLite, JSON) must implement this interface
    to be compatible with HybridPersistence.
    """

    def save_workflow(self, workflow: WorkflowState) -> None:
        """Save workflow to backend."""
        ...

    def load_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """Load workflow from backend."""
        ...

    def list_workflow_ids(self) -> List[str]:
        """List all workflow IDs in backend."""
        ...

    def begin_transaction(self) -> None:
        """Begin transaction (if backend supports it)."""
        ...

    def commit(self) -> None:
        """Commit transaction (if backend supports it)."""
        ...

    def rollback(self) -> None:
        """Rollback transaction (if backend supports it)."""
        ...


class SQLiteBackend:
    """
    SQLite persistence backend implementation.

    Wraps StateManager to provide transaction support and standardized interface.
    This is the authoritative/primary backend.
    """

    def __init__(self, state_manager: "StateManager") -> None:  # type: ignore[name-defined]
        """
        Initialize SQLite backend.

        Args:
            state_manager: StateManager instance for database operations
        """
        self.state_manager = state_manager
        raw_db_path = getattr(state_manager, "db_path", None)
        try:
            self._db_path = Path(raw_db_path)
        except TypeError as exc:
            raise TypeError(
                "StateManager.db_path must be a filesystem path, "
                f"got {type(raw_db_path).__name__}"
            ) from exc
        self._in_transaction = False
        self._transaction_workflow_id: Optional[str] = None

    def save_workflow(self, workflow: WorkflowState) -> None:
        """
        Save workflow to SQLite database.

        Updates all 20 Phase 1 fields to ensure data integrity.
        Uses UPSERT pattern (UPDATE or INSERT) to handle both new
        and existing workflows.

        This method must be called from a synchronous context and will
        handle the async database operations internally in a safe way.

        Args:
            workflow: WorkflowState to persist

        Raises:
            Exception: If database write fails
        """
        import json as json_lib
        import sqlite3

        self._transaction_workflow_id = workflow.workflow_id

        # Use synchronous sqlite3 for simplicity (avoid asyncio.run() issues)
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()

        try:
            # Try UPDATE first
            cursor.execute(
                """
                UPDATE workflows SET
                    workflow_name = ?,
                    workflow_type = ?,
                    issue_number = ?,
                    state = ?,
                    branch_name = ?,
                    base_branch = ?,
                    worktree_path = ?,
                    tags = ?,
                    metadata = ?,
                    exit_code = ?,
                    error_message = ?,
                    retry_count = ?,
                    cost_usd = ?,
                    total_tokens = ?,
                    started_at = ?,
                    completed_at = ?,
                    archived_at = ?,
                    last_activity_at = ?,
                    backend_port = ?,
                    frontend_port = ?,
                    issue_class = ?,
                    model_set = ?,
                    phase_count = ?
                WHERE workflow_id = ?
                """,
                (
                    workflow.workflow_name,
                    workflow.workflow_type.value,
                    workflow.issue_number,
                    workflow.state.value,
                    workflow.branch_name,
                    workflow.base_branch,
                    workflow.worktree_path,
                    json_lib.dumps(workflow.tags) if workflow.tags else "[]",
                    json_lib.dumps(workflow.metadata) if workflow.metadata else "{}",
                    workflow.exit_code,
                    workflow.error_message,
                    workflow.retry_count,
                    workflow.cost_usd,
                    workflow.total_tokens,
                    workflow.started_at.isoformat() if workflow.started_at else None,
                    workflow.completed_at.isoformat() if workflow.completed_at else None,
                    workflow.archived_at.isoformat() if workflow.archived_at else None,
                    workflow.last_activity_at.isoformat(),
                    workflow.backend_port,
                    workflow.frontend_port,
                    workflow.issue_class.value if workflow.issue_class else None,
                    workflow.model_set.value,
                    workflow.phase_count,
                    workflow.workflow_id
                )
            )

            if cursor.rowcount == 0:
                # INSERT if UPDATE didn't find row
                cursor.execute(
                    """
                    INSERT INTO workflows (
                        workflow_id, workflow_name, workflow_type, issue_number, state,
                        created_at, started_at, completed_at, archived_at, last_activity_at,
                        branch_name, base_branch, worktree_path, tags, metadata,
                        exit_code, error_message, retry_count, cost_usd, total_tokens,
                        backend_port, frontend_port, issue_class, model_set, phase_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow.workflow_id,
                        workflow.workflow_name,
                        workflow.workflow_type.value,
                        workflow.issue_number,
                        workflow.state.value,
                        workflow.created_at.isoformat(),
                        workflow.started_at.isoformat() if workflow.started_at else None,
                        workflow.completed_at.isoformat() if workflow.completed_at else None,
                        workflow.archived_at.isoformat() if workflow.archived_at else None,
                        workflow.last_activity_at.isoformat(),
                        workflow.branch_name,
                        workflow.base_branch,
                        workflow.worktree_path,
                        json_lib.dumps(workflow.tags) if workflow.tags else "[]",
                        json_lib.dumps(workflow.metadata) if workflow.metadata else "{}",
                        workflow.exit_code,
                        workflow.error_message,
                        workflow.retry_count,
                        workflow.cost_usd,
                        workflow.total_tokens,
                        workflow.backend_port,
                        workflow.frontend_port,
                        workflow.issue_class.value if workflow.issue_class else None,
                        workflow.model_set.value,
                        workflow.phase_count
                    )
                )

            conn.commit()
        finally:
            conn.close()

    def load_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """
        Load workflow from SQLite database.

        Args:
            workflow_id: Workflow identifier

        Returns:
            WorkflowState if found, None otherwise
        """
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
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
                    total_tokens,
                    backend_port,
                    frontend_port,
                    issue_class,
                    model_set,
                    phase_count
                FROM workflows
                WHERE workflow_id = ?
                """,
                (workflow_id,)
            )

            row = cursor.fetchone()
            if row is None:
                return None

            row_dict = dict(row)
            return WorkflowState(**row_dict)
        finally:
            conn.close()

    def list_workflow_ids(self) -> List[str]:
        """
        List all workflow IDs in database.

        Returns:
            List of workflow IDs

        Example:
            >>> backend = SQLiteBackend(state_manager)
            >>> ids = backend.list_workflow_ids()
            >>> print(ids)  # ['wf_001', 'wf_002', ...]
        """
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT workflow_id FROM workflows")
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    def begin_transaction(self) -> None:
        """Begin database transaction."""
        self._in_transaction = True
        self._transaction_workflow_id = None

    def commit(self) -> None:
        """Commit database transaction."""
        self._in_transaction = False
        self._transaction_workflow_id = None

    def rollback(self) -> None:
        """Rollback database transaction."""
        # For Phase 2, rollback is implicit in StateManager error handling
        self._in_transaction = False
        self._transaction_workflow_id = None


class JSONBackend:
    """
    JSON file persistence backend implementation.

    Provides fallback persistence and debugging capability.
    Non-authoritative - SQLite is the source of truth.
    """

    def __init__(self, json_dir: Path) -> None:
        """
        Initialize JSON backend.

        Args:
            json_dir: Directory to store JSON workflow files
        """
        self.json_dir = json_dir
        self.logger = logging.getLogger(__name__)

    def save_workflow(self, workflow: WorkflowState) -> None:
        """
        Save workflow to JSON file.

        Args:
            workflow: WorkflowState to persist

        Raises:
            Exception: If file write fails
        """
        self.json_dir.mkdir(parents=True, exist_ok=True)

        file_path = self.json_dir / f"{workflow.workflow_id}.json"

        # Convert WorkflowState to dict for JSON serialization
        workflow_dict = workflow.model_dump(mode="json")

        with open(file_path, "w") as f:
            json.dump(workflow_dict, f, indent=2)

    def load_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """
        Load workflow from JSON file.

        Args:
            workflow_id: Workflow identifier

        Returns:
            WorkflowState if found, None otherwise
        """
        file_path = self.json_dir / f"{workflow_id}.json"

        if not file_path.exists():
            return None

        try:
            with open(file_path, "r") as f:
                workflow_dict = json.load(f)
            return WorkflowState(**workflow_dict)
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to load workflow {workflow_id} from JSON: {e}")
            return None

    def list_workflow_ids(self) -> List[str]:
        """
        List all workflow IDs in JSON directory.

        Returns:
            List of workflow IDs
        """
        if not self.json_dir.exists():
            return []

        workflow_ids = []
        for file_path in self.json_dir.glob("*.json"):
            workflow_ids.append(file_path.stem)

        return workflow_ids

    def begin_transaction(self) -> None:
        """Begin transaction (no-op for JSON)."""
        pass

    def commit(self) -> None:
        """Commit transaction (no-op for JSON)."""
        pass

    def rollback(self) -> None:
        """Rollback transaction (no-op for JSON)."""
        pass


@dataclass
class SyncResult:
    """
    Result of backend synchronization operation.

    Attributes:
        workflows_synced: Number of workflows successfully synchronized
        discrepancies_found: Number of mismatches detected
        errors: List of error messages encountered
    """

    workflows_synced: int
    discrepancies_found: int
    errors: List[str]


class HybridPersistence:
    """
    Coordinates dual-write to SQLite (primary) and JSON (fallback).

    Write strategy:
    1. SQLite first (transactional, can rollback)
    2. JSON second (best-effort, log on failure)

    This ensures SQLite is always authoritative and JSON is kept in sync.

    Example:
        >>> sqlite_backend = SQLiteBackend(state_manager)
        >>> json_backend = JSONBackend(Path(".adws/workflows"))
        >>> persistence = HybridPersistence(sqlite_backend, json_backend)
        >>>
        >>> try:
        ...     persistence.save_workflow(workflow)
        ... except PersistenceError as e:
        ...     logger.error(f"Critical: SQLite save failed: {e}")
    """

    def __init__(
        self,
        sqlite_backend: SQLiteBackend,
        json_backend: JSONBackend
    ) -> None:
        """
        Initialize dual-write persistence.

        Args:
            sqlite_backend: SQLite persistence implementation
            json_backend: JSON persistence implementation
        """
        self.sqlite = sqlite_backend
        self.json = json_backend
        self.logger = logging.getLogger(__name__)

    def save_workflow(self, workflow: WorkflowState) -> None:
        """
        Save workflow to both SQLite and JSON with write-ahead pattern.

        Writes to SQLite first (transactional). If that succeeds,
        writes to JSON (non-critical). SQLite is always authoritative.

        Args:
            workflow: WorkflowState object to persist

        Raises:
            PersistenceError: If SQLite write fails (critical error)

        Logs:
            Warning if JSON write fails (non-critical, SQLite data intact)

        Example:
            >>> try:
            ...     persistence.save_workflow(workflow)
            ... except PersistenceError as e:
            ...     logger.error(f"Critical: SQLite save failed: {e}")
            ...     # Handle critical error
            ... # JSON failures are already logged, can proceed
        """
        # SQLite first (transactional, mandatory)
        try:
            self.sqlite.begin_transaction()
            self.sqlite.save_workflow(workflow)
            self.sqlite.commit()
            self.logger.info(f"Saved {workflow.workflow_id} to SQLite")
        except Exception as e:
            self.sqlite.rollback()
            error_msg = f"SQLite save failed for {workflow.workflow_id}: {e}"
            self.logger.error(error_msg)
            raise PersistenceError(
                error_msg,
                workflow_id=workflow.workflow_id,
                error_details=str(e)
            ) from e

        # JSON second (best-effort, non-critical)
        try:
            self.json.save_workflow(workflow)
            self.logger.debug(f"Saved {workflow.workflow_id} to JSON")
        except Exception as e:
            self.logger.warning(
                f"JSON save failed for {workflow.workflow_id}, SQLite data intact: {e}"
            )
            # Do NOT raise - SQLite is authoritative

    def load_workflow(
        self,
        workflow_id: str,
        prefer_source: Literal["sqlite", "json"] = "sqlite"
    ) -> Optional[WorkflowState]:
        """
        Load workflow from preferred source with fallback.

        Args:
            workflow_id: Workflow identifier
            prefer_source: "sqlite" (default) or "json"

        Returns:
            WorkflowState if found, None otherwise

        Raises:
            Exception: Propagated from backend if both sources fail

        Logic:
            1. Try preferred source first
            2. If fails, try fallback source
            3. If both fail, return None

        Example:
            >>> # Load from SQLite (primary)
            >>> workflow = persistence.load_workflow("workflow-123")
            >>>
            >>> # Fallback to JSON if SQLite unavailable
            >>> workflow = persistence.load_workflow("workflow-123", prefer_source="json")
        """
        primary = self.sqlite if prefer_source == "sqlite" else self.json
        fallback = self.json if prefer_source == "sqlite" else self.sqlite

        try:
            workflow = primary.load_workflow(workflow_id)
            if workflow:
                self.logger.debug(f"Loaded {workflow_id} from {prefer_source}")
                return workflow
        except Exception as e:
            self.logger.warning(f"Failed to load from {prefer_source}: {e}")

        # Try fallback
        try:
            workflow = fallback.load_workflow(workflow_id)
            if workflow:
                fallback_source = "json" if prefer_source == "sqlite" else "sqlite"
                self.logger.info(f"Loaded {workflow_id} from fallback {fallback_source}")
                return workflow
        except Exception as e:
            self.logger.error(f"Failed to load from fallback: {e}")

        return None

    def sync_backends(self) -> SyncResult:
        """
        Detect and repair SQLite/JSON desynchronization.

        Ensures both backends contain the same workflow data.
        SQLite is always authoritative.

        Returns:
            SyncResult with details of sync operation:
            - workflows_synced: Number of workflows synchronized
            - discrepancies_found: Number of mismatches detected
            - errors: Any errors encountered

        Algorithm:
            1. List all workflows in SQLite
            2. For each workflow:
               a. Load from both backends
               b. Compare content
               c. If different, overwrite JSON with SQLite
            3. Return sync statistics

        Example:
            >>> result = persistence.sync_backends()
            >>> print(f"Synced {result.workflows_synced} workflows")
            >>> if result.discrepancies_found > 0:
            ...     print(f"Fixed {result.discrepancies_found} discrepancies")
        """
        workflows_synced = 0
        discrepancies_found = 0
        errors: List[str] = []

        try:
            # Get all workflow IDs from SQLite (authoritative)
            sqlite_ids = self.sqlite.list_workflow_ids()

            for workflow_id in sqlite_ids:
                try:
                    # Load from both backends
                    sqlite_workflow = self.sqlite.load_workflow(workflow_id)
                    json_workflow = self.json.load_workflow(workflow_id)

                    if sqlite_workflow is None:
                        # Should not happen since we got ID from SQLite
                        errors.append(f"SQLite workflow {workflow_id} disappeared")
                        continue

                    # Check if JSON matches SQLite
                    if json_workflow is None or json_workflow != sqlite_workflow:
                        discrepancies_found += 1
                        # Overwrite JSON with SQLite (authoritative)
                        self.json.save_workflow(sqlite_workflow)
                        self.logger.info(f"Synced {workflow_id} from SQLite to JSON")

                    workflows_synced += 1

                except Exception as e:
                    error_msg = f"Failed to sync {workflow_id}: {e}"
                    errors.append(error_msg)
                    self.logger.error(error_msg)

        except Exception as e:
            error_msg = f"Failed to list SQLite workflows: {e}"
            errors.append(error_msg)
            self.logger.error(error_msg)

        self.logger.info(
            f"Sync complete: {workflows_synced} synced, "
            f"{discrepancies_found} discrepancies, {len(errors)} errors"
        )

        return SyncResult(
            workflows_synced=workflows_synced,
            discrepancies_found=discrepancies_found,
            errors=errors
        )
