"""
Cost Tracking Infrastructure

Provides token counting, cost calculation, and budget enforcement
for multi-LLM provider operations.

Key Components:
    - CostTracker: Track costs across providers and workflows
    - BudgetEnforcer: Enforce budget limits
    - CostReport: Generate cost reports and analytics

Example:
    >>> from adws.cost import CostTracker
    >>> tracker = CostTracker()
    >>> tracker.record_cost(
    ...     adw_id="adw_123",
    ...     provider="claude",
    ...     model="claude-sonnet-4",
    ...     cost_usd=0.05,
    ...     input_tokens=1000,
    ...     output_tokens=2000
    ... )
    >>> report = tracker.get_report("adw_123")
    >>> print(f"Total cost: ${report.total_cost:.4f}")
"""

from adws.cost.tracker import CostTracker, CostRecord
from adws.cost.budget import BudgetEnforcer, Budget, BudgetPeriod

__all__ = [
    "CostTracker",
    "CostRecord",
    "BudgetEnforcer",
    "Budget",
    "BudgetPeriod",
]
