"""
ADWS v2.0 State Management - Cleanup Manager

This module manages workflow cleanup and archival with configurable
retention policies.

Issue: #7 - Query API & Cleanup Manager (Phase 3 Fields)
Phase: Phase 3 - Query and resource management
"""

import io
import json
import logging
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from adws.state.lifecycle import CLEANABLE_STATES, WorkflowLifecycle
from adws.state.models import WorkflowState
from adws.state.query import WorkflowFilter

logger = logging.getLogger(__name__)


@dataclass
class CleanupPolicy:
    """Configuration for automatic cleanup of workflows."""

    policy_name: str  # e.g., "archive_completed_30d"
    target_state: str  # State to clean (e.g., "completed")
    min_age_days: int  # Minimum age before cleanup (e.g., 30)
    action: str  # "archive" or "delete"


@dataclass
class CleanupResult:
    """Result of cleanup operation."""

    workflows_processed: int
    workflows_archived: int
    workflows_deleted: int
    total_space_freed_mb: float
    errors: List[str]
    orphan_archives_deleted: int = 0


class CleanupManager:
    """
    Manages workflow cleanup and archival.

    Cleanup process:
    1. Apply retention policies (age, count, disk usage)
    2. Archive completed workflows (tar.gz compression)
    3. Delete old archives (30+ days)
    4. Update SQLite state (state → ARCHIVED)
    """

    # Default cleanup policies
    DEFAULT_POLICIES = [
        CleanupPolicy("archive_completed", "completed", min_age_days=30, action="archive"),
        CleanupPolicy("archive_failed", "failed", min_age_days=60, action="archive"),
        CleanupPolicy("archive_cancelled", "cancelled", min_age_days=7, action="archive"),
        CleanupPolicy("delete_archived", "archived", min_age_days=180, action="delete"),
    ]

    def __init__(
        self,
        state_manager: "StateManager",  # type: ignore[name-defined]
        archive_dir: Path,
        max_archive_age_days: int = 180,
    ):
        """
        Initialize cleanup manager.

        Args:
            state_manager: StateManager for workflow access
            archive_dir: Directory for archived workflows (will create if missing)
            max_archive_age_days: Delete archives older than this (default: 180 days)
        """
        self.state_manager = state_manager
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.max_archive_age_days = max_archive_age_days
        self.logger = logging.getLogger(__name__)

        # Process cleanup work in predictable batches to avoid starving backlog.
        self._workflow_batch_size = 100

    async def run_cleanup(
        self, policies: Optional[List[CleanupPolicy]] = None
    ) -> CleanupResult:
        """
        Run cleanup based on policies.

        Args:
            policies: List of cleanup policies (uses defaults if None)

        Returns:
            CleanupResult with details of cleanup operation

        Algorithm:
            FOR EACH policy:
              1. Query workflows matching: state=policy.target_state AND age>policy.min_age_days
              2. FOR EACH matching workflow:
                 a. If action="archive": call archive_workflow()
                 b. If action="delete": call delete_archive()
              3. Log results

        Example:
            result = await cleanup_manager.run_cleanup()
            print(f"Archived {result.workflows_archived} workflows")
            print(f"Freed {result.total_space_freed_mb:.1f} MB")
        """
        policies = policies or self.DEFAULT_POLICIES
        result = CleanupResult(0, 0, 0, 0.0, [])

        # Import WorkflowQuery lazily to avoid circular dependency at module import.
        from adws.state.query import WorkflowQuery

        query = WorkflowQuery(self.state_manager)

        for policy in policies:
            self.logger.info(f"Running cleanup policy: {policy.policy_name}")
            cutoff_date = self._compute_policy_cutoff(policy)
            workflow_filter = self._build_policy_filter(policy, cutoff_date)
            await self._process_policy_batches(policy, workflow_filter, query, result, cutoff_date)

        # Final pass: remove orphaned tarballs with no DB row beyond retention window.
        orphan_cutoff = datetime.now(timezone.utc) - timedelta(
            days=self.max_archive_age_days
        )
        orphaned, orphan_space = await self._cleanup_orphan_archives(orphan_cutoff)
        result.orphan_archives_deleted += orphaned
        result.total_space_freed_mb += orphan_space

        return result

    async def archive_workflow(self, workflow_id: str) -> Path:
        """
        Archive workflow to tar.gz and update SQLite state.

        Steps:
        1. Load workflow from SQLite
        2. Create tar.gz archive with workflow data
        3. Update SQLite: state=ARCHIVED, archived_at=NOW()
        4. Return path to archive file

        Args:
            workflow_id: Workflow to archive

        Returns:
            Path to created archive file (*.tar.gz)

        Raises:
            ValueError: If workflow not found or in non-archivable state

        Archive structure:
            workflow-{id}.tar.gz
            ├── metadata.json          (WorkflowState as JSON)
            ├── phases/                (JSON for each phase)
            │   ├── phase_1.json
            │   ├── phase_2.json
            │   └── ...
            └── logs.txt               (Execution logs, if any)

        Example:
            archive_path = await cleanup_manager.archive_workflow("workflow-123")
            print(f"Archived to {archive_path}")
        """
        # Load workflow
        workflow = await self.state_manager.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        # Check if archivable
        if workflow.state not in CLEANABLE_STATES:
            raise ValueError(
                f"Cannot archive workflow in state {workflow.state.value}. "
                f"Only archivable states: {[s.value for s in CLEANABLE_STATES]}"
            )

        # Create archive
        archive_filename = f"workflow-{workflow_id}.tar.gz"
        archive_path = self.archive_dir / archive_filename

        with tarfile.open(archive_path, "w:gz") as tar:
            # Add metadata as JSON
            metadata_json = workflow.model_dump_json(indent=2)
            metadata_bytes = metadata_json.encode("utf-8")
            metadata_info = tarfile.TarInfo(name="metadata.json")
            metadata_info.size = len(metadata_bytes)
            tar.addfile(metadata_info, io.BytesIO(metadata_bytes))

            # Add placeholder for phases directory
            # (In real implementation, this would include phase execution data)
            phases_readme = b"Phase execution data would be stored here.\n"
            phases_info = tarfile.TarInfo(name="phases/README.txt")
            phases_info.size = len(phases_readme)
            tar.addfile(phases_info, io.BytesIO(phases_readme))

        self.logger.info(f"Archived {workflow_id} to {archive_path}")

        # Update SQLite state (StateManager sets archived_at atomically).
        await self.state_manager.update_workflow(
            workflow_id=workflow_id, state=WorkflowLifecycle.ARCHIVED
        )

        return archive_path

    async def restore_workflow(self, archive_path: Path) -> WorkflowState:
        """
        Restore workflow from archive back to SQLite.

        Steps:
        1. Extract metadata.json from tar.gz
        2. Parse as WorkflowState
        3. Remove ARCHIVED flag (set to previous terminal state if possible)
        4. Insert back to SQLite

        Args:
            archive_path: Path to *.tar.gz archive file

        Returns:
            Restored WorkflowState

        Raises:
            FileNotFoundError: If archive not found
            ValueError: If archive is invalid (missing metadata.json) or path traversal detected

        Example:
            workflow = await cleanup_manager.restore_workflow(
                Path("archives/workflow-123.tar.gz")
            )
        """
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        # Security: prevent path traversal attacks
        resolved_archive = archive_path.resolve()
        resolved_archive_dir = self.archive_dir.resolve()
        try:
            resolved_archive.relative_to(resolved_archive_dir)
        except ValueError:
            raise ValueError(
                f"Security: archive path {archive_path} is outside archive directory {self.archive_dir}"
            )

        with tarfile.open(archive_path, "r:gz") as tar:
            # Extract metadata.json
            try:
                metadata_file = tar.extractfile("metadata.json")
            except KeyError:
                raise ValueError("Invalid archive: missing metadata.json")

            if not metadata_file:
                raise ValueError("Invalid archive: missing metadata.json")

            metadata_json = metadata_file.read().decode("utf-8")
            workflow_data = json.loads(metadata_json)

            # Parse as WorkflowState
            workflow = WorkflowState(**workflow_data)

            # If state is ARCHIVED, restore to COMPLETED (safe terminal state)
            if workflow.state == WorkflowLifecycle.ARCHIVED:
                workflow.state = WorkflowLifecycle.COMPLETED
                workflow.archived_at = None

            # Use persistence layer to save (creates new if doesn't exist)
            self.state_manager.persistence.save_workflow(workflow)

        self.logger.info(f"Restored {workflow.workflow_id} from {archive_path}")
        return workflow

    async def delete_archive(self, workflow_id: str) -> None:
        """
        Delete archived workflow (permanent).

        Args:
            workflow_id: Workflow to delete

        Raises:
            FileNotFoundError: If archive not found

        Example:
            await cleanup_manager.delete_archive("workflow-123")
        """
        archive_filename = f"workflow-{workflow_id}.tar.gz"
        archive_path = self.archive_dir / archive_filename

        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        archive_path.unlink()
        self.logger.info(f"Deleted archive: {archive_path}")

        # Also delete from SQLite (if it exists)
        try:
            await self.state_manager.delete_workflow(workflow_id)
        except ValueError:
            # Workflow already deleted from SQLite, that's fine
            self.logger.warning(
                f"Could not delete {workflow_id} from SQLite (already deleted)"
            )

    async def list_archives(self) -> List[Path]:
        """
        List all archived workflows.

        Returns:
            List of archive file paths

        Example:
            archives = await cleanup_manager.list_archives()
            for archive_path in archives:
                print(f"Archive: {archive_path.name}")
        """
        return list(self.archive_dir.glob("workflow-*.tar.gz"))

    async def get_archive_size_mb(self) -> float:
        """
        Get total size of all archives in MB.

        Returns:
            Total size in megabytes

        Example:
            size = await cleanup_manager.get_archive_size_mb()
            print(f"Archives use {size:.1f} MB")
        """
        total_bytes = sum(
            p.stat().st_size for p in self.archive_dir.glob("workflow-*.tar.gz")
        )
        return total_bytes / (1024 * 1024)

    def _compute_policy_cutoff(self, policy: CleanupPolicy) -> datetime:
        """
        Determine the cutoff datetime for a policy, honoring max archive retention.

        Delete policies are additionally capped by max_archive_age_days so global
        retention overrides take precedence over per-policy defaults.
        """
        age_days = policy.min_age_days
        if policy.action == "delete":
            age_days = min(policy.min_age_days, self.max_archive_age_days)
        return datetime.now(timezone.utc) - timedelta(days=age_days)

    def _build_policy_filter(
        self, policy: CleanupPolicy, cutoff_date: datetime
    ) -> WorkflowFilter:
        """
        Build a WorkflowFilter that enforces ordering and paging guarantees
        for a cleanup policy. Archive policies traverse by created_at, while
        delete policies drain archived_at oldest-first.
        """
        filter_kwargs = {
            "states": [policy.target_state],
            "limit": self._workflow_batch_size,
            "offset": 0,
        }

        if policy.action == "delete" and policy.target_state == WorkflowLifecycle.ARCHIVED.value:
            filter_kwargs["archived_before"] = cutoff_date
            filter_kwargs["order_by"] = "archived_at ASC"
        else:
            filter_kwargs["created_before"] = cutoff_date
            filter_kwargs["order_by"] = "created_at ASC"

        return WorkflowFilter(**filter_kwargs)

    async def _process_policy_batches(
        self,
        policy: CleanupPolicy,
        workflow_filter: WorkflowFilter,
        query: "WorkflowQuery",  # type: ignore[name-defined]
        result: CleanupResult,
        cutoff_date: datetime,
    ) -> None:
        """
        Iterate through WorkflowQuery result pages so every eligible workflow
        is processed exactly once (oldest first).
        """
        while True:
            query_result = await query.list_workflows(workflow_filter)

            if not query_result.workflows:
                break

            processed_in_batch = 0

            for workflow in query_result.workflows:
                try:
                    if policy.action == "archive":
                        archive_path = await self.archive_workflow(workflow.workflow_id)
                        result.workflows_archived += 1
                        if archive_path.exists():
                            result.total_space_freed_mb += (
                                archive_path.stat().st_size / (1024 * 1024)
                            )

                    elif policy.action == "delete":
                        # Only delete if archive timestamp (or fallback) exceeds cutoff.
                        if self._is_archive_expired(workflow, cutoff_date):
                            archive_path = self.archive_dir / f"workflow-{workflow.workflow_id}.tar.gz"
                            freed_space_mb = (
                                archive_path.stat().st_size / (1024 * 1024)
                                if archive_path.exists()
                                else 0.0
                            )
                            await self.delete_archive(workflow.workflow_id)
                            result.workflows_deleted += 1
                            result.total_space_freed_mb += freed_space_mb
                        else:
                            self.logger.debug(
                                "Skipping delete for %s; archive not yet beyond cutoff",
                                workflow.workflow_id,
                            )
                            continue

                    result.workflows_processed += 1
                    processed_in_batch += 1

                except Exception as e:
                    error_msg = f"Failed to {policy.action} {workflow.workflow_id}: {e}"
                    self.logger.error(error_msg)
                    result.errors.append(error_msg)

            if processed_in_batch == 0:
                break

    def _is_archive_expired(
        self, workflow: WorkflowState, cutoff: datetime
    ) -> bool:
        """
        Determine if a workflow's archive exceeds the retention window.

        Uses archived_at when available and falls back to the tarball's mtime
        when the timestamp is missing (legacy data).
        """
        if workflow.archived_at:
            return workflow.archived_at <= cutoff

        archive_path = self.archive_dir / f"workflow-{workflow.workflow_id}.tar.gz"
        if not archive_path.exists():
            # If no archive file exists, treat it as expired so delete_archive
            # can clean up the dangling DB entry.
            return True

        archive_mtime = datetime.fromtimestamp(
            archive_path.stat().st_mtime, tz=timezone.utc
        )
        return archive_mtime <= cutoff

    async def _cleanup_orphan_archives(self, cutoff: datetime) -> Tuple[int, float]:
        """
        Delete tarballs that have no corresponding workflow rows once they
        are older than the retention cutoff.
        """
        orphaned = 0
        freed_space_mb = 0.0

        for archive_path in self.archive_dir.glob("workflow-*.tar.gz"):
            workflow_id = self._extract_workflow_id(archive_path.name)
            if workflow_id is None:
                continue

            workflow = await self.state_manager.get_workflow(workflow_id)
            if workflow is not None:
                continue

            archive_mtime = datetime.fromtimestamp(
                archive_path.stat().st_mtime, tz=timezone.utc
            )
            if archive_mtime > cutoff:
                continue

            self.logger.warning(
                "Removing orphaned archive %s (no workflow record)", archive_path.name
            )
            freed_space_mb += archive_path.stat().st_size / (1024 * 1024)
            archive_path.unlink()
            orphaned += 1

        return orphaned, freed_space_mb

    @staticmethod
    def _extract_workflow_id(archive_name: str) -> Optional[str]:
        """Extract workflow ID from archive filename."""
        prefix = "workflow-"
        suffix = ".tar.gz"
        if not archive_name.startswith(prefix) or not archive_name.endswith(suffix):
            return None
        return archive_name[len(prefix) : -len(suffix)]
