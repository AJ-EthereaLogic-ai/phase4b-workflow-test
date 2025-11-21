"""
Cost Tracking

Tracks LLM API costs across providers and workflows.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from collections import defaultdict


class CostRecord(BaseModel):
    """
    Record of a single LLM API call cost.

    Attributes:
        timestamp: When the call was made (UTC)
        adw_id: Workflow identifier
        provider: Provider name (e.g., 'claude', 'openai')
        model: Model identifier
        cost_usd: Cost in USD
        input_tokens: Input tokens used
        output_tokens: Output tokens generated
        total_tokens: Total tokens (input + output)
        slash_command: Slash command that triggered the call
        success: Whether the call succeeded

    Example:
        >>> record = CostRecord(
        ...     adw_id="adw_123",
        ...     provider="claude",
        ...     model="claude-sonnet-4",
        ...     cost_usd=0.05,
        ...     input_tokens=1000,
        ...     output_tokens=2000,
        ...     slash_command="/implement"
        ... )
    """

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp (UTC)"
    )
    adw_id: str = Field(..., description="Workflow ID")
    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model identifier")
    cost_usd: float = Field(..., description="Cost in USD", ge=0.0)
    input_tokens: int = Field(..., description="Input tokens", ge=0)
    output_tokens: int = Field(..., description="Output tokens", ge=0)
    total_tokens: int = Field(..., description="Total tokens", ge=0)
    slash_command: str = Field(..., description="Slash command")
    success: bool = Field(True, description="Whether call succeeded")


class CostReport(BaseModel):
    """
    Cost report for a workflow or time period.

    Attributes:
        total_cost: Total cost in USD
        total_tokens: Total tokens used
        call_count: Number of API calls
        success_count: Number of successful calls
        failure_count: Number of failed calls
        by_provider: Cost breakdown by provider
        by_model: Cost breakdown by model
        records: Individual cost records

    Example:
        >>> report = tracker.get_report("adw_123")
        >>> print(f"Total: ${report.total_cost:.4f}")
        >>> print(f"Calls: {report.call_count}")
    """

    total_cost: float = Field(0.0, description="Total cost USD", ge=0.0)
    total_tokens: int = Field(0, description="Total tokens", ge=0)
    call_count: int = Field(0, description="Number of calls", ge=0)
    success_count: int = Field(0, description="Successful calls", ge=0)
    failure_count: int = Field(0, description="Failed calls", ge=0)
    by_provider: Dict[str, float] = Field(
        default_factory=dict,
        description="Cost by provider"
    )
    by_model: Dict[str, float] = Field(
        default_factory=dict,
        description="Cost by model"
    )
    records: List[CostRecord] = Field(
        default_factory=list,
        description="Individual records"
    )


class CostTracker:
    """
    Track LLM API costs across providers and workflows.

    Maintains in-memory records of all API calls and their costs.
    Provides reporting and analysis capabilities.

    Thread-safe: This implementation is not thread-safe. If used in
    multi-threaded contexts, external synchronization is required.

    Example:
        >>> tracker = CostTracker()
        >>> tracker.record_cost(
        ...     adw_id="adw_123",
        ...     provider="claude",
        ...     model="claude-sonnet-4",
        ...     cost_usd=0.05,
        ...     input_tokens=1000,
        ...     output_tokens=2000,
        ...     slash_command="/implement",
        ...     success=True
        ... )
        >>> report = tracker.get_report("adw_123")
        >>> print(f"Total cost: ${report.total_cost:.4f}")
    """

    def __init__(self):
        """Initialize cost tracker"""
        self._records: List[CostRecord] = []
        self._by_workflow: Dict[str, List[CostRecord]] = defaultdict(list)

    def record_cost(
        self,
        adw_id: str,
        provider: str,
        model: str,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        slash_command: str,
        success: bool = True,
    ) -> CostRecord:
        """
        Record a cost entry.

        Args:
            adw_id: Workflow identifier
            provider: Provider name
            model: Model identifier
            cost_usd: Cost in USD
            input_tokens: Input tokens used
            output_tokens: Output tokens generated
            slash_command: Slash command
            success: Whether call succeeded

        Returns:
            Created CostRecord

        Example:
            >>> record = tracker.record_cost(
            ...     adw_id="adw_123",
            ...     provider="claude",
            ...     model="claude-sonnet-4",
            ...     cost_usd=0.05,
            ...     input_tokens=1000,
            ...     output_tokens=2000,
            ...     slash_command="/implement"
            ... )
        """
        record = CostRecord(
            adw_id=adw_id,
            provider=provider,
            model=model,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            slash_command=slash_command,
            success=success,
        )

        self._records.append(record)
        self._by_workflow[adw_id].append(record)

        return record

    def get_report(self, adw_id: Optional[str] = None) -> CostReport:
        """
        Get cost report.

        Args:
            adw_id: Workflow ID (None for all workflows)

        Returns:
            CostReport with aggregated data

        Example:
            >>> # Get report for specific workflow
            >>> report = tracker.get_report("adw_123")
            >>> print(f"Cost: ${report.total_cost:.4f}")
            >>>
            >>> # Get report for all workflows
            >>> total_report = tracker.get_report()
        """
        # Select records
        if adw_id:
            records = self._by_workflow.get(adw_id, [])
        else:
            records = self._records

        if not records:
            return CostReport()

        # Calculate aggregates
        total_cost = sum(r.cost_usd for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        call_count = len(records)
        success_count = sum(1 for r in records if r.success)
        failure_count = call_count - success_count

        # Group by provider
        by_provider: Dict[str, float] = defaultdict(float)
        for record in records:
            by_provider[record.provider] += record.cost_usd

        # Group by model
        by_model: Dict[str, float] = defaultdict(float)
        for record in records:
            by_model[record.model] += record.cost_usd

        return CostReport(
            total_cost=total_cost,
            total_tokens=total_tokens,
            call_count=call_count,
            success_count=success_count,
            failure_count=failure_count,
            by_provider=dict(by_provider),
            by_model=dict(by_model),
            records=records.copy(),
        )

    def get_workflow_cost(self, adw_id: str) -> float:
        """
        Get total cost for a workflow.

        Args:
            adw_id: Workflow identifier

        Returns:
            Total cost in USD

        Example:
            >>> cost = tracker.get_workflow_cost("adw_123")
            >>> print(f"Workflow cost: ${cost:.4f}")
        """
        records = self._by_workflow.get(adw_id, [])
        return sum(r.cost_usd for r in records)

    def get_workflow_tokens(self, adw_id: str) -> int:
        """
        Get total tokens for a workflow.

        Args:
            adw_id: Workflow identifier

        Returns:
            Total token count

        Example:
            >>> tokens = tracker.get_workflow_tokens("adw_123")
            >>> print(f"Tokens used: {tokens:,}")
        """
        records = self._by_workflow.get(adw_id, [])
        return sum(r.total_tokens for r in records)

    def clear(self) -> None:
        """
        Clear all records.

        Example:
            >>> tracker.clear()
        """
        self._records.clear()
        self._by_workflow.clear()

    def clear_workflow(self, adw_id: str) -> None:
        """
        Clear records for a specific workflow.

        Args:
            adw_id: Workflow identifier

        Example:
            >>> tracker.clear_workflow("adw_123")
        """
        if adw_id in self._by_workflow:
            # Remove from workflow index
            workflow_records = self._by_workflow[adw_id]
            del self._by_workflow[adw_id]

            # Remove from main records list
            self._records = [r for r in self._records if r.adw_id != adw_id]


# Global cost tracker singleton
_global_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """
    Get the global cost tracker.

    Returns:
        Global CostTracker instance

    Example:
        >>> tracker = get_cost_tracker()
        >>> tracker.record_cost(...)
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker()
    return _global_tracker
