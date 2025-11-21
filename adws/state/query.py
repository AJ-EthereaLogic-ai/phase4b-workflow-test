"""
ADWS v2.0 State Management - Query API

This module provides high-level query operations with filter builder pattern
for workflow state management.

Issue: #7 - Query API & Cleanup Manager (Phase 3 Fields)
Phase: Phase 3 - Query and resource management
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from adws.state.lifecycle import WorkflowLifecycle
from adws.state.models import IssueClass, ModelSet, WorkflowState


@dataclass
class WorkflowFilter:
    """
    Multi-criteria filter for workflow queries.

    All criteria are optional and ANDed together.
    Leave as None to match all workflows.
    """

    # Workflow identity
    workflow_ids: Optional[List[str]] = None
    workflow_names: Optional[List[str]] = None

    # State filtering
    states: Optional[List[str]] = None  # e.g., ["running", "paused"]

    # Time range filtering
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    started_after: Optional[datetime] = None
    started_before: Optional[datetime] = None
    completed_after: Optional[datetime] = None
    completed_before: Optional[datetime] = None

    # Archive time filtering
    archived_after: Optional[datetime] = None
    archived_before: Optional[datetime] = None

    # Activity filtering (for cleanup decisions)
    last_activity_before: Optional[datetime] = None  # Inactive for X days

    # Classification filtering
    issue_classes: Optional[List[IssueClass]] = None
    issue_numbers: Optional[List[int]] = None

    # Tag filtering
    tags: Optional[List[str]] = None  # Match workflows with ANY of these tags

    # Model selection filtering
    model_sets: Optional[List[ModelSet]] = None

    # Cost filtering
    min_cost_usd: Optional[float] = None
    max_cost_usd: Optional[float] = None

    # Token filtering
    min_tokens: Optional[int] = None
    max_tokens: Optional[int] = None

    # Pagination
    limit: int = 100
    offset: int = 0

    # Sorting
    order_by: str = "created_at DESC"  # SQL ORDER BY clause

    def __post_init__(self) -> None:
        """Validate filter parameters."""
        if self.limit < 1 or self.limit > 10000:
            raise ValueError("limit must be between 1 and 10000")
        if self.offset < 0:
            raise ValueError("offset must be >= 0")


@dataclass
class QueryResult:
    """Result of a workflow query."""

    workflows: List[WorkflowState]
    total_count: int  # Total matching workflows (ignoring limit/offset)
    returned_count: int  # Actual workflows returned
    query_time_ms: float


class WorkflowQuery:
    """
    Provides high-level query operations over SQLite backend.

    Uses WorkflowFilter to build complex queries.
    All queries are parameterized (prevent SQL injection).
    """

    # Allowlist of sortable columns for ORDER BY clause
    _ALLOWED_ORDER_FIELDS = {
        "workflow_name",
        "created_at",
        "started_at",
        "completed_at",
        "archived_at",
        "last_activity_at",
        "cost_usd",
        "total_tokens",
        "issue_number",
        "phase_count",
        "state",
    }
    _ALLOWED_ORDER_DIRECTIONS = {"ASC", "DESC"}
    _DEFAULT_ORDER = "created_at DESC"

    def __init__(self, state_manager: "StateManager") -> None:  # type: ignore[name-defined]
        """
        Initialize query engine.

        Args:
            state_manager: StateManager instance for database access
        """
        self.state_manager = state_manager
        self.logger = logging.getLogger(__name__)

    async def list_workflows(
        self, filter: Optional[WorkflowFilter] = None
    ) -> QueryResult:
        """
        List workflows matching filter criteria.

        Args:
            filter: WorkflowFilter with query criteria (None = all workflows)

        Returns:
            QueryResult with matching workflows and metadata

        Example:
            # Get all running workflows
            result = await query.list_workflows(
                filter=WorkflowFilter(states=["running"])
            )

            # Get completed workflows from past week, page 2
            result = await query.list_workflows(
                filter=WorkflowFilter(
                    states=["completed"],
                    completed_after=datetime.now() - timedelta(days=7),
                    limit=50,
                    offset=50
                )
            )
        """
        filter = filter or WorkflowFilter()

        # Build SQL query
        sql, params = self._build_query(filter)

        # Execute query
        start_time = time.time()
        workflows = await self._execute_query(sql, params)
        query_time_ms = (time.time() - start_time) * 1000

        # Get total count (ignoring limit/offset)
        count_sql, count_params = self._build_count_query(filter)
        total_count = await self._execute_count_query(count_sql, count_params)

        return QueryResult(
            workflows=workflows,
            total_count=total_count,
            returned_count=len(workflows),
            query_time_ms=query_time_ms,
        )

    async def search_workflows(
        self,
        query: str,
        fields: Optional[List[str]] = None,
    ) -> List[WorkflowState]:
        """
        Full-text search for workflows.

        Args:
            query: Search query string (will search across fields)
            fields: Fields to search (default: name, tags, metadata)

        Returns:
            List of matching workflows

        Example:
            # Search for "authentication" in workflow name
            workflows = await query.search_workflows("authentication")
        """
        if fields is None:
            fields = ["workflow_name", "tags", "metadata"]

        search_pattern = f"%{query}%"
        conditions = []
        params: Dict[str, Any] = {"query": search_pattern}

        if "workflow_name" in fields:
            conditions.append("workflow_name LIKE :query")
        if "tags" in fields:
            conditions.append("tags LIKE :query")
        if "metadata" in fields:
            conditions.append("metadata LIKE :query")

        if not conditions:
            return []

        where_clause = " OR ".join(conditions)
        sql = f"SELECT * FROM workflows WHERE {where_clause} ORDER BY created_at DESC"

        return await self._execute_query(sql, params)

    async def count_by_state(self) -> Dict[str, int]:
        """
        Count workflows in each state.

        Returns:
            Dictionary: state → count

        Example:
            counts = await query.count_by_state()
            # Returns: {"running": 5, "completed": 42, "failed": 2, ...}
        """
        sql = """
        SELECT state, COUNT(*) as count
        FROM workflows
        GROUP BY state
        ORDER BY count DESC
        """
        rows = await self._execute_raw_query(sql, {})
        return {row["state"]: row["count"] for row in rows}

    async def get_stuck_workflows(self) -> List[WorkflowState]:
        """
        Get all workflows detected as stuck.

        Returns:
            List of stuck workflows

        Example:
            stuck = await query.get_stuck_workflows()
            for workflow in stuck:
                print(f"Stuck: {workflow.workflow_id} since {workflow.started_at}")
        """
        filter = WorkflowFilter(states=["stuck"])
        result = await self.list_workflows(filter)
        return result.workflows

    async def get_metrics(
        self, filter: Optional[WorkflowFilter] = None
    ) -> Dict[str, Any]:
        """
        Get aggregate metrics for workflows matching filter.

        Returns:
            Dictionary with metrics:
            - total_count: Number of matching workflows
            - avg_cost_usd: Average cost
            - total_cost_usd: Sum of costs
            - avg_tokens: Average tokens used
            - total_tokens: Sum of tokens
            - success_rate: % of completed/successful workflows
            - avg_duration_minutes: Average execution time

        Example:
            metrics = await query.get_metrics(
                filter=WorkflowFilter(
                    states=["completed"],
                    issue_classes=[IssueClass.FEATURE]
                )
            )
            print(f"Feature success rate: {metrics['success_rate']:.1%}")
        """
        filter = filter or WorkflowFilter()
        sql, params = self._build_metrics_query(filter)

        rows = await self._execute_raw_query(sql, params)
        row = rows[0] if rows else {}

        return {
            "total_count": row.get("total_count", 0),
            "avg_cost_usd": row.get("avg_cost_usd", 0.0),
            "total_cost_usd": row.get("total_cost_usd", 0.0),
            "avg_tokens": row.get("avg_tokens", 0),
            "total_tokens": row.get("total_tokens", 0),
            "success_rate": row.get("success_rate", 0.0),
            "avg_duration_minutes": row.get("avg_duration_minutes", 0.0),
        }

    def _build_query(self, filter: WorkflowFilter) -> tuple[str, Dict[str, Any]]:
        """
        Build SQL query from filter criteria.

        Returns:
            (sql_query, parameters_dict) for parameterized execution
        """
        conditions = []
        params: Dict[str, Any] = {}

        # Identity filters
        if filter.workflow_ids:
            placeholders = ",".join(
                [f":wf_id_{i}" for i in range(len(filter.workflow_ids))]
            )
            conditions.append(f"workflow_id IN ({placeholders})")
            for i, wf_id in enumerate(filter.workflow_ids):
                params[f"wf_id_{i}"] = wf_id

        if filter.workflow_names:
            placeholders = ",".join(
                [f":wf_name_{i}" for i in range(len(filter.workflow_names))]
            )
            conditions.append(f"workflow_name IN ({placeholders})")
            for i, name in enumerate(filter.workflow_names):
                params[f"wf_name_{i}"] = name

        # State filters
        if filter.states:
            placeholders = ",".join([f":state_{i}" for i in range(len(filter.states))])
            conditions.append(f"state IN ({placeholders})")
            for i, state in enumerate(filter.states):
                params[f"state_{i}"] = state

        # Time filters
        if filter.created_after:
            conditions.append("created_at >= :created_after")
            params["created_after"] = filter.created_after.isoformat()

        if filter.created_before:
            conditions.append("created_at <= :created_before")
            params["created_before"] = filter.created_before.isoformat()

        if filter.started_after:
            conditions.append("started_at >= :started_after")
            params["started_after"] = filter.started_after.isoformat()

        if filter.started_before:
            conditions.append("started_at <= :started_before")
            params["started_before"] = filter.started_before.isoformat()

        if filter.completed_after:
            conditions.append("completed_at >= :completed_after")
            params["completed_after"] = filter.completed_after.isoformat()

        if filter.completed_before:
            conditions.append("completed_at <= :completed_before")
            params["completed_before"] = filter.completed_before.isoformat()

        if filter.archived_after:
            conditions.append("archived_at >= :archived_after")
            params["archived_after"] = filter.archived_after.isoformat()

        if filter.archived_before:
            conditions.append("archived_at <= :archived_before")
            params["archived_before"] = filter.archived_before.isoformat()

        if filter.last_activity_before:
            conditions.append("last_activity_at <= :last_activity_before")
            params["last_activity_before"] = filter.last_activity_before.isoformat()

        # Classification filters
        if filter.issue_classes:
            placeholders = ",".join(
                [f":issue_class_{i}" for i in range(len(filter.issue_classes))]
            )
            conditions.append(f"issue_class IN ({placeholders})")
            for i, issue_class in enumerate(filter.issue_classes):
                params[f"issue_class_{i}"] = issue_class.value

        if filter.issue_numbers:
            placeholders = ",".join(
                [f":issue_num_{i}" for i in range(len(filter.issue_numbers))]
            )
            conditions.append(f"issue_number IN ({placeholders})")
            for i, issue_num in enumerate(filter.issue_numbers):
                params[f"issue_num_{i}"] = issue_num

        # Tag filtering (JSON LIKE query)
        if filter.tags:
            tag_conditions = []
            for i, tag in enumerate(filter.tags):
                tag_conditions.append(f"tags LIKE :tag_{i}")
                params[f"tag_{i}"] = f'%"{tag}"%'
            conditions.append(f"({' OR '.join(tag_conditions)})")

        # Model set filters
        if filter.model_sets:
            placeholders = ",".join(
                [f":model_set_{i}" for i in range(len(filter.model_sets))]
            )
            conditions.append(f"model_set IN ({placeholders})")
            for i, model_set in enumerate(filter.model_sets):
                params[f"model_set_{i}"] = model_set.value

        # Cost filters
        if filter.min_cost_usd is not None:
            conditions.append("cost_usd >= :min_cost_usd")
            params["min_cost_usd"] = filter.min_cost_usd

        if filter.max_cost_usd is not None:
            conditions.append("cost_usd <= :max_cost_usd")
            params["max_cost_usd"] = filter.max_cost_usd

        # Token filters
        if filter.min_tokens is not None:
            conditions.append("total_tokens >= :min_tokens")
            params["min_tokens"] = filter.min_tokens

        if filter.max_tokens is not None:
            conditions.append("total_tokens <= :max_tokens")
            params["max_tokens"] = filter.max_tokens

        # Build final query
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        order_clause = self._build_order_clause(filter.order_by)
        sql = f"""
        SELECT * FROM workflows
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT {filter.limit} OFFSET {filter.offset}
        """

        return sql, params

    def _build_count_query(
        self, filter: WorkflowFilter
    ) -> tuple[str, Dict[str, Any]]:
        """
        Build COUNT query from filter criteria.

        Returns:
            (sql_query, parameters_dict)
        """
        # Reuse the WHERE clause logic from _build_query
        conditions = []
        params: Dict[str, Any] = {}

        # Copy all filter logic from _build_query (excluding ORDER BY, LIMIT, OFFSET)
        if filter.workflow_ids:
            placeholders = ",".join(
                [f":wf_id_{i}" for i in range(len(filter.workflow_ids))]
            )
            conditions.append(f"workflow_id IN ({placeholders})")
            for i, wf_id in enumerate(filter.workflow_ids):
                params[f"wf_id_{i}"] = wf_id

        if filter.workflow_names:
            placeholders = ",".join(
                [f":wf_name_{i}" for i in range(len(filter.workflow_names))]
            )
            conditions.append(f"workflow_name IN ({placeholders})")
            for i, name in enumerate(filter.workflow_names):
                params[f"wf_name_{i}"] = name

        if filter.states:
            placeholders = ",".join([f":state_{i}" for i in range(len(filter.states))])
            conditions.append(f"state IN ({placeholders})")
            for i, state in enumerate(filter.states):
                params[f"state_{i}"] = state

        if filter.created_after:
            conditions.append("created_at >= :created_after")
            params["created_after"] = filter.created_after.isoformat()

        if filter.created_before:
            conditions.append("created_at <= :created_before")
            params["created_before"] = filter.created_before.isoformat()

        if filter.started_after:
            conditions.append("started_at >= :started_after")
            params["started_after"] = filter.started_after.isoformat()

        if filter.started_before:
            conditions.append("started_at <= :started_before")
            params["started_before"] = filter.started_before.isoformat()

        if filter.completed_after:
            conditions.append("completed_at >= :completed_after")
            params["completed_after"] = filter.completed_after.isoformat()

        if filter.completed_before:
            conditions.append("completed_at <= :completed_before")
            params["completed_before"] = filter.completed_before.isoformat()

        if filter.archived_after:
            conditions.append("archived_at >= :archived_after")
            params["archived_after"] = filter.archived_after.isoformat()

        if filter.archived_before:
            conditions.append("archived_at <= :archived_before")
            params["archived_before"] = filter.archived_before.isoformat()

        if filter.last_activity_before:
            conditions.append("last_activity_at <= :last_activity_before")
            params["last_activity_before"] = filter.last_activity_before.isoformat()

        if filter.issue_classes:
            placeholders = ",".join(
                [f":issue_class_{i}" for i in range(len(filter.issue_classes))]
            )
            conditions.append(f"issue_class IN ({placeholders})")
            for i, issue_class in enumerate(filter.issue_classes):
                params[f"issue_class_{i}"] = issue_class.value

        if filter.issue_numbers:
            placeholders = ",".join(
                [f":issue_num_{i}" for i in range(len(filter.issue_numbers))]
            )
            conditions.append(f"issue_number IN ({placeholders})")
            for i, issue_num in enumerate(filter.issue_numbers):
                params[f"issue_num_{i}"] = issue_num

        if filter.tags:
            tag_conditions = []
            for i, tag in enumerate(filter.tags):
                tag_conditions.append(f"tags LIKE :tag_{i}")
                params[f"tag_{i}"] = f'%"{tag}"%'
            conditions.append(f"({' OR '.join(tag_conditions)})")

        if filter.model_sets:
            placeholders = ",".join(
                [f":model_set_{i}" for i in range(len(filter.model_sets))]
            )
            conditions.append(f"model_set IN ({placeholders})")
            for i, model_set in enumerate(filter.model_sets):
                params[f"model_set_{i}"] = model_set.value

        if filter.min_cost_usd is not None:
            conditions.append("cost_usd >= :min_cost_usd")
            params["min_cost_usd"] = filter.min_cost_usd

        if filter.max_cost_usd is not None:
            conditions.append("cost_usd <= :max_cost_usd")
            params["max_cost_usd"] = filter.max_cost_usd

        if filter.min_tokens is not None:
            conditions.append("total_tokens >= :min_tokens")
            params["min_tokens"] = filter.min_tokens

        if filter.max_tokens is not None:
            conditions.append("total_tokens <= :max_tokens")
            params["max_tokens"] = filter.max_tokens

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
        SELECT COUNT(*) as count
        FROM workflows
        WHERE {where_clause}
        """

        return sql, params

    def _build_metrics_query(
        self, filter: WorkflowFilter
    ) -> tuple[str, Dict[str, Any]]:
        """
        Build metrics aggregation query.

        Returns:
            (sql_query, parameters_dict)
        """
        # Reuse WHERE clause from count query
        _, params = self._build_count_query(filter)
        conditions = []

        # Rebuild conditions for WHERE clause (same as count_query)
        if filter.workflow_ids:
            placeholders = ",".join(
                [f":wf_id_{i}" for i in range(len(filter.workflow_ids))]
            )
            conditions.append(f"workflow_id IN ({placeholders})")

        if filter.workflow_names:
            placeholders = ",".join(
                [f":wf_name_{i}" for i in range(len(filter.workflow_names))]
            )
            conditions.append(f"workflow_name IN ({placeholders})")

        if filter.states:
            placeholders = ",".join([f":state_{i}" for i in range(len(filter.states))])
            conditions.append(f"state IN ({placeholders})")

        if filter.created_after:
            conditions.append("created_at >= :created_after")

        if filter.created_before:
            conditions.append("created_at <= :created_before")

        if filter.started_after:
            conditions.append("started_at >= :started_after")

        if filter.started_before:
            conditions.append("started_at <= :started_before")

        if filter.completed_after:
            conditions.append("completed_at >= :completed_after")

        if filter.completed_before:
            conditions.append("completed_at <= :completed_before")

        if filter.archived_after:
            conditions.append("archived_at >= :archived_after")

        if filter.archived_before:
            conditions.append("archived_at <= :archived_before")

        if filter.last_activity_before:
            conditions.append("last_activity_at <= :last_activity_before")

        if filter.issue_classes:
            placeholders = ",".join(
                [f":issue_class_{i}" for i in range(len(filter.issue_classes))]
            )
            conditions.append(f"issue_class IN ({placeholders})")

        if filter.issue_numbers:
            placeholders = ",".join(
                [f":issue_num_{i}" for i in range(len(filter.issue_numbers))]
            )
            conditions.append(f"issue_number IN ({placeholders})")

        if filter.tags:
            tag_conditions = []
            for i, tag in enumerate(filter.tags):
                tag_conditions.append(f"tags LIKE :tag_{i}")
            conditions.append(f"({' OR '.join(tag_conditions)})")

        if filter.model_sets:
            placeholders = ",".join(
                [f":model_set_{i}" for i in range(len(filter.model_sets))]
            )
            conditions.append(f"model_set IN ({placeholders})")

        if filter.min_cost_usd is not None:
            conditions.append("cost_usd >= :min_cost_usd")

        if filter.max_cost_usd is not None:
            conditions.append("cost_usd <= :max_cost_usd")

        if filter.min_tokens is not None:
            conditions.append("total_tokens >= :min_tokens")

        if filter.max_tokens is not None:
            conditions.append("total_tokens <= :max_tokens")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
        SELECT
            COUNT(*) as total_count,
            AVG(cost_usd) as avg_cost_usd,
            SUM(cost_usd) as total_cost_usd,
            AVG(total_tokens) as avg_tokens,
            SUM(total_tokens) as total_tokens,
            CAST(SUM(CASE WHEN state IN ('completed', 'archived') THEN 1 ELSE 0 END) AS FLOAT) /
                CAST(COUNT(*) AS FLOAT) as success_rate,
            AVG(CAST((julianday(completed_at) - julianday(started_at)) * 24 * 60 AS FLOAT)) as avg_duration_minutes
        FROM workflows
        WHERE {where_clause}
        """

        return sql, params

    def _build_order_clause(self, requested: str) -> str:
        """
        Sanitize ORDER BY clause using strict allowlist.
        Falls back to created_at DESC on invalid input.
        """
        if not requested:
            return self._DEFAULT_ORDER

        tokens = requested.strip().split()
        column = tokens[0]
        direction = tokens[1].upper() if len(tokens) > 1 else "ASC"

        if column not in self._ALLOWED_ORDER_FIELDS:
            self.logger.warning(
                "Invalid order_by column '%s'; falling back to %s",
                column,
                self._DEFAULT_ORDER,
            )
            return self._DEFAULT_ORDER

        if direction not in self._ALLOWED_ORDER_DIRECTIONS:
            self.logger.warning(
                "Invalid order_by direction '%s'; defaulting to ASC", direction
            )
            direction = "ASC"

        return f"{column} {direction}"

    async def _execute_query(
        self, sql: str, params: Dict[str, Any]
    ) -> List[WorkflowState]:
        """
        Execute SQL query and return WorkflowState objects.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            List of WorkflowState objects
        """
        async with self.state_manager._get_connection() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()

        workflows = []
        for row in rows:
            row_dict = dict(row)
            workflows.append(WorkflowState(**row_dict))

        return workflows

    async def _execute_raw_query(
        self, sql: str, params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Execute raw SQL query and return dicts.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            List of dictionaries (row data)
        """
        async with self.state_manager._get_connection() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def _execute_count_query(
        self, sql: str, params: Dict[str, Any]
    ) -> int:
        """
        Execute COUNT query and return integer count.

        Args:
            sql: SQL COUNT query
            params: Query parameters

        Returns:
            Total count of matching rows
        """
        rows = await self._execute_raw_query(sql, params)
        return rows[0]["count"] if rows else 0
