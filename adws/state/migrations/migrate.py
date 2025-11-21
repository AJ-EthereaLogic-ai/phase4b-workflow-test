"""
ADWS v2.0 State Management - Migration Functions

Provides utilities for migrating ADWS state databases across schema versions.
"""

import logging
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


async def migrate_to_phase1(db_path: Path, backup: bool = True) -> dict[str, int]:
    """
    Migrate database to Phase 1 schema.

    Adds Phase 1 fields to existing workflows table:
    - issue_number: GitHub issue tracking
    - branch_name: Git branch context
    - base_branch: Target branch for PR
    - worktree_path: Git worktree location
    - retry_count: Retry attempt count

    Also renames total_cost to cost_usd for clarity.

    Args:
        db_path: Path to SQLite database file
        backup: If True, creates backup before migration (default: True)

    Returns:
        Dictionary with migration statistics:
        - total_workflows: Total workflows migrated
        - workflows_with_new_fields: Workflows with new fields populated

    Raises:
        FileNotFoundError: If database doesn't exist
        aiosqlite.Error: If migration fails

    Example:
        >>> from pathlib import Path
        >>> from adws.state.migrations import migrate_to_phase1
        >>> stats = await migrate_to_phase1(Path(".adws/workflows.db"))
        >>> print(f"Migrated {stats['total_workflows']} workflows")
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    # Create backup if requested
    if backup:
        backup_path = db_path.with_suffix(f"{db_path.suffix}.backup")
        logger.info(f"Creating backup at {backup_path}")
        import shutil

        shutil.copy2(db_path, backup_path)
        logger.info(f"Backup created successfully")

    async with aiosqlite.connect(str(db_path)) as conn:
        # Check if migration is needed by inspecting schema
        cursor = await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='workflows'"
        )
        schema_sql = (await cursor.fetchone())[0]

        if "issue_number" in schema_sql:
            logger.info("Database already migrated to Phase 1")
            # Return stats for already-migrated database
            cursor = await conn.execute("SELECT COUNT(*) FROM workflows")
            total = (await cursor.fetchone())[0]
            return {"total_workflows": total, "workflows_with_new_fields": 0}

        logger.info("Starting Phase 1 migration...")

        # Read migration SQL
        migration_path = Path(__file__).parent / "001_add_phase1_fields.sql"
        migration_sql = migration_path.read_text()

        # Split SQL statements (exclude verification query)
        statements = [
            stmt.strip()
            for stmt in migration_sql.split(";")
            if stmt.strip()
            and not stmt.strip().startswith("--")
            and not stmt.strip().upper().startswith("SELECT")
        ]

        # Execute migration statements
        for stmt in statements:
            if stmt:
                logger.debug(f"Executing: {stmt[:50]}...")
                await conn.execute(stmt)

        # Handle total_cost -> cost_usd rename using SQLite's table reconstruction
        # This is necessary because SQLite doesn't support ALTER COLUMN RENAME
        logger.info("Renaming total_cost to cost_usd...")

        # Check if total_cost column exists
        cursor = await conn.execute("PRAGMA table_info(workflows)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "total_cost" in column_names and "cost_usd" not in column_names:
            # Create temporary table with new schema
            await conn.execute(
                """
                CREATE TABLE workflows_new (
                    workflow_id TEXT PRIMARY KEY NOT NULL,
                    workflow_name TEXT NOT NULL,
                    workflow_type TEXT NOT NULL DEFAULT 'standard' CHECK(workflow_type IN (
                        'standard', 'tdd', 'plan-only', 'test-only', 'review-only'
                    )),
                    issue_number INTEGER,
                    state TEXT NOT NULL CHECK(state IN (
                        'created', 'initialized', 'running', 'paused',
                        'completed', 'failed', 'cancelled', 'stuck', 'archived'
                    )),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    archived_at TIMESTAMP,
                    last_activity_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    branch_name TEXT,
                    base_branch TEXT DEFAULT 'main',
                    worktree_path TEXT,
                    tags TEXT,
                    metadata TEXT,
                    exit_code INTEGER,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    total_tokens INTEGER DEFAULT 0,
                    CHECK(state = 'archived' OR archived_at IS NULL),
                    CHECK(state NOT IN ('running', 'paused', 'completed', 'failed') OR started_at IS NOT NULL)
                )
                """
            )

            def column_expr(column: str, default_sql: str = "NULL") -> str:
                """
                Return an expression for a column if it exists, otherwise a default literal.
                """

                return column if column in column_names else default_sql

            def select_clause(column: str, default_sql: str = "NULL") -> str:
                """
                Build the SELECT clause for a column, aliasing the expression when needed.
                """

                expr = column_expr(column, default_sql)
                if expr == column:
                    return column
                return f"{expr} AS {column}"

            cost_expression = "COALESCE(total_cost, 0.0) AS cost_usd"
            state_expr = column_expr("state", "'created'")
            created_at_expr = column_expr("created_at", "CURRENT_TIMESTAMP")
            last_activity_expr = column_expr("last_activity_at", "CURRENT_TIMESTAMP")
            started_at_expr = column_expr("started_at")
            started_at_clause = (
                "CASE "
                f"WHEN {state_expr} IN ('running','paused','completed','failed') "
                f"THEN COALESCE({started_at_expr}, {created_at_expr}, {last_activity_expr}) "
                f"ELSE {started_at_expr} "
                "END AS started_at"
            )

            # Copy data from old table to new table
            await conn.execute(
                f"""
                INSERT INTO workflows_new (
                    workflow_id, workflow_name, workflow_type, issue_number,
                    state, created_at, started_at, completed_at, archived_at,
                    last_activity_at, branch_name, base_branch, worktree_path,
                    tags, metadata, exit_code, error_message, retry_count,
                    cost_usd, total_tokens
                )
                SELECT
                    {select_clause('workflow_id')},
                    {select_clause('workflow_name')},
                    {select_clause('workflow_type', "'standard'")},
                    {select_clause('issue_number')},
                    {select_clause('state', "'created'")},
                    {select_clause('created_at', 'CURRENT_TIMESTAMP')},
                    {started_at_clause},
                    {select_clause('completed_at')},
                    {select_clause('archived_at')},
                    {select_clause('last_activity_at', 'CURRENT_TIMESTAMP')},
                    {select_clause('branch_name')},
                    {select_clause('base_branch', "'main'")},
                    {select_clause('worktree_path')},
                    {select_clause('tags')},
                    {select_clause('metadata')},
                    {select_clause('exit_code')},
                    {select_clause('error_message')},
                    {select_clause('retry_count', '0')},
                    {cost_expression},
                    {select_clause('total_tokens', '0')}
                FROM workflows
                """
            )

            # Drop old table and rename new table
            await conn.execute("DROP TABLE workflows")
            await conn.execute("ALTER TABLE workflows_new RENAME TO workflows")

            # Recreate indexes
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_state ON workflows(state)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_created_at ON workflows(created_at)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_last_activity ON workflows(last_activity_at)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_workflow_type ON workflows(workflow_type)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_state_created ON workflows(state, created_at)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_issue_number ON workflows(issue_number)"
            )

        await conn.commit()

        # Gather migration statistics
        cursor = await conn.execute(
            """
            SELECT
                COUNT(*) as total_workflows,
                COUNT(issue_number) as workflows_with_issue_number,
                COUNT(branch_name) as workflows_with_branch_name,
                COUNT(worktree_path) as workflows_with_worktree_path
            FROM workflows
            """
        )
        stats_row = await cursor.fetchone()

        stats = {
            "total_workflows": stats_row[0],
            "workflows_with_issue_number": stats_row[1],
            "workflows_with_branch_name": stats_row[2],
            "workflows_with_worktree_path": stats_row[3],
        }

        logger.info(f"Migration complete: {stats}")
        return stats


async def check_migration_status(db_path: Path) -> dict[str, bool]:
    """
    Check which migrations have been applied to database.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Dictionary mapping migration names to status (True = applied)

    Raises:
        FileNotFoundError: If database doesn't exist
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    async with aiosqlite.connect(str(db_path)) as conn:
        cursor = await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='workflows'"
        )
        result = await cursor.fetchone()

        if not result:
            return {"phase1": False}

        schema_sql = result[0]

        # Check for Phase 1 fields
        phase1_applied = (
            "issue_number" in schema_sql
            and "branch_name" in schema_sql
            and "worktree_path" in schema_sql
            and "cost_usd" in schema_sql
        )

        return {"phase1": phase1_applied}
