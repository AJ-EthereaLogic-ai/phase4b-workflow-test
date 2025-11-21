"""
Budget Enforcement

Enforces budget limits for LLM API usage with thread-safe ledger tracking
and period-aware automatic resets.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Module-level constant for unlimited budget representation
UNLIMITED_BUDGET = Decimal("999999999999")


def _convert_to_decimal(v) -> Decimal:
    """
    Helper function to convert various types to Decimal.

    Handles int, float, str, and Decimal types.
    Special handling for infinity values.

    Args:
        v: Value to convert to Decimal

    Returns:
        Decimal representation of the value
    """
    if isinstance(v, (int, float)):
        if v == float('inf'):
            return UNLIMITED_BUDGET
        return Decimal(str(v))
    elif isinstance(v, str):
        if v in ("inf", "Infinity"):
            return UNLIMITED_BUDGET
        return Decimal(v)
    elif isinstance(v, Decimal):
        if v == Decimal("inf") or not v.is_finite():
            return UNLIMITED_BUDGET
        return v
    else:
        return Decimal(str(v))


class BudgetPeriod(str, Enum):
    """
    Budget period types.

    Attributes:
        PER_WORKFLOW: Budget applies to entire workflow
        HOURLY: Budget resets every hour
        DAILY: Budget resets daily
        WEEKLY: Budget resets weekly
        MONTHLY: Budget resets monthly
        TOTAL: Total budget (no reset)
    """

    PER_WORKFLOW = "per_workflow"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TOTAL = "total"


class Budget(BaseModel):
    """
    Budget configuration with Decimal precision for currency math.

    Attributes:
        max_cost_usd: Maximum cost in USD (uses Decimal for precision)
        period: Budget period
        enabled: Whether budget is enforced
        warning_threshold: Threshold for warnings (0-1, e.g., 0.8 = 80%)

    Example:
        >>> budget = Budget(
        ...     max_cost_usd=10.0,
        ...     period=BudgetPeriod.DAILY,
        ...     enabled=True,
        ...     warning_threshold=0.8
        ... )
    """

    max_cost_usd: Decimal = Field(..., description="Max cost USD")
    period: BudgetPeriod = Field(..., description="Budget period")
    enabled: bool = Field(True, description="Whether enforced")
    warning_threshold: Decimal = Field(
        default=Decimal("0.8"),
        description="Warning threshold (0-1)",
    )

    @field_validator("max_cost_usd", mode="before")
    @classmethod
    def validate_max_cost(cls, v):
        """Convert to Decimal and validate > 0."""
        v = _convert_to_decimal(v)
        if v <= 0:
            raise ValueError("max_cost_usd must be greater than 0")
        # Quantize to 6 decimal places for currency precision
        return v.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    @field_validator("warning_threshold", mode="before")
    @classmethod
    def validate_warning_threshold(cls, v):
        """Convert to Decimal and validate 0-1 range."""
        if v is None:
            return Decimal("0.8")
        v = _convert_to_decimal(v)
        if v < 0 or v > 1:
            raise ValueError("warning_threshold must be between 0 and 1")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class BudgetStatus(BaseModel):
    """
    Budget status information with Decimal precision.

    Attributes:
        current_cost: Current cost in period (Decimal)
        max_cost: Maximum allowed cost (Decimal, may be very large for unlimited)
        remaining: Remaining budget (Decimal)
        percent_used: Percentage of budget used (0-100, Decimal)
        exceeded: Whether budget is exceeded
        warning: Whether warning threshold reached

    Example:
        >>> status = enforcer.get_status("adw_123")
        >>> if status.warning:
        ...     print(f"Warning: {status.percent_used:.1f}% of budget used")
        >>> if status.exceeded:
        ...     print("Budget exceeded!")
    """

    model_config = {"arbitrary_types_allowed": True}

    current_cost: Decimal = Field(..., description="Current cost")
    max_cost: Decimal = Field(..., description="Max cost")
    remaining: Decimal = Field(..., description="Remaining budget")
    percent_used: Decimal = Field(..., description="Percent used")
    exceeded: bool = Field(..., description="Whether exceeded")
    warning: bool = Field(..., description="Whether warning threshold reached")

    @field_validator("current_cost", "max_cost", "remaining", "percent_used", mode="before")
    @classmethod
    def validate_decimal_fields(cls, v):
        """Convert to Decimal if needed."""
        return _convert_to_decimal(v)


class BudgetExceededError(Exception):
    """
    Raised when budget is exceeded.

    Attributes:
        budget_status: Budget status when exceeded
    """

    def __init__(self, message: str, budget_status: BudgetStatus):
        super().__init__(message)
        self.budget_status = budget_status


class _LedgerEntry:
    """
    Internal ledger entry for tracking workflow budget usage.

    Attributes:
        current_cost: Accumulated cost for this workflow/period
        last_reset_at: Timestamp of last reset (for period-based budgets)
        warned: Whether warning threshold has been logged
        exceeded: Whether budget has been exceeded for this workflow/period
    """

    def __init__(self):
        self.current_cost: Decimal = Decimal("0")
        self.last_reset_at: datetime = datetime.now(UTC)
        self.warned: bool = False
        self.exceeded: bool = False

    def reset(self):
        """Reset ledger entry for new period."""
        self.current_cost = Decimal("0")
        self.last_reset_at = datetime.now(UTC)
        self.warned = False
        self.exceeded = False


class BudgetEnforcer:
    """
    Thread-safe budget enforcer with stateful ledger tracking.

    Maintains per-workflow cost ledger with automatic period-based resets.
    Uses Decimal for precise currency math. Thread-safe for concurrent access.

    Thread-safe: This implementation IS thread-safe using threading.RLock().
    Multiple threads can safely call enforce_budget() concurrently.

    Example:
        >>> from adws.cost import Budget, BudgetPeriod
        >>> budget = Budget(
        ...     max_cost_usd=10.0,
        ...     period=BudgetPeriod.DAILY,
        ...     enabled=True
        ... )
        >>> enforcer = BudgetEnforcer(budget)
        >>>
        >>> # Enforce with cost increment (thread-safe)
        >>> enforcer.enforce_budget("adw_123", cost_increment=0.5)
        >>>
        >>> # Check current status
        >>> status = enforcer.get_status("adw_123")
        >>> print(f"Used: ${status.current_cost} / ${status.max_cost}")
    """

    def __init__(self, budget: Optional[Budget] = None):
        """
        Initialize budget enforcer with ledger and thread safety.

        Args:
            budget: Budget configuration (None = no enforcement)

        Example:
            >>> budget = Budget(max_cost_usd=10.0, period=BudgetPeriod.DAILY)
            >>> enforcer = BudgetEnforcer(budget)
        """
        self.budget = budget
        self._lock = threading.RLock()
        self._ledger: Dict[str, _LedgerEntry] = {}

    def _should_reset(self, period: BudgetPeriod, last_reset: datetime) -> bool:
        """
        Check if budget period should reset based on time elapsed.

        Args:
            period: Budget period type
            last_reset: Last reset timestamp

        Returns:
            True if period should reset
        """
        if period in (BudgetPeriod.PER_WORKFLOW, BudgetPeriod.TOTAL):
            return False

        now = datetime.now(UTC)
        delta = now - last_reset

        if period == BudgetPeriod.HOURLY:
            return delta >= timedelta(hours=1)
        elif period == BudgetPeriod.DAILY:
            return delta >= timedelta(days=1)
        elif period == BudgetPeriod.WEEKLY:
            return delta >= timedelta(weeks=1)
        elif period == BudgetPeriod.MONTHLY:
            # Approximate month as 30 days
            return delta >= timedelta(days=30)

        return False

    def _get_or_create_entry(self, adw_id: str) -> _LedgerEntry:
        """
        Get or create ledger entry for workflow (must be called with lock held).

        Args:
            adw_id: Workflow identifier

        Returns:
            Ledger entry for this workflow
        """
        if adw_id not in self._ledger:
            self._ledger[adw_id] = _LedgerEntry()

        entry = self._ledger[adw_id]

        # Check if period reset is needed
        if self.budget and self._should_reset(self.budget.period, entry.last_reset_at):
            logger.info(f"Resetting budget for {adw_id} (period: {self.budget.period})")
            entry.reset()

        return entry

    def check_budget(
        self,
        adw_id: str,
        current_cost: Optional[float] = None
    ) -> BudgetStatus:
        """
        Check budget status (DEPRECATED: use get_status instead).

        This method is kept for backward compatibility. New code should use
        get_status() which relies on the internal ledger.

        Args:
            adw_id: Workflow identifier
            current_cost: Current cost (deprecated - uses ledger if not provided)

        Returns:
            Budget status

        Example:
            >>> status = enforcer.check_budget("adw_123")
            >>> print(f"Used: {status.percent_used:.1f}%")
        """
        with self._lock:
            if not self.budget or not self.budget.enabled:
                # No budget enforcement
                cost = Decimal(str(current_cost)) if current_cost is not None else Decimal("0")
                return BudgetStatus(
                    current_cost=cost,
                    max_cost=UNLIMITED_BUDGET,
                    remaining=UNLIMITED_BUDGET,
                    percent_used=Decimal("0"),
                    exceeded=False,
                    warning=False,
                )

            # Use ledger if current_cost not provided (new behavior)
            if current_cost is None:
                entry = self._get_or_create_entry(adw_id)
                cost = entry.current_cost
            else:
                # Backward compatibility: use provided current_cost
                cost = Decimal(str(current_cost))

            max_cost = self.budget.max_cost_usd
            remaining = max(Decimal("0"), max_cost - cost)
            percent_used = (cost / max_cost) * Decimal("100")
            exceeded = cost > max_cost
            warning = (cost / max_cost) >= self.budget.warning_threshold

            return BudgetStatus(
                current_cost=cost,
                max_cost=max_cost,
                remaining=remaining,
                percent_used=percent_used,
                exceeded=exceeded,
                warning=warning,
            )

    def enforce_budget(
        self,
        adw_id: str,
        cost_increment: Optional[float] = None,
        current_cost: Optional[float] = None
    ) -> BudgetStatus:
        """
        Enforce budget limit with automatic ledger tracking.

        Args:
            adw_id: Workflow identifier
            cost_increment: Cost to add to ledger (recommended, thread-safe)
            current_cost: DEPRECATED - for backward compatibility only

        Returns:
            Budget status after applying increment

        Raises:
            BudgetExceededError: If budget would be exceeded

        Example:
            >>> # Recommended: use cost_increment
            >>> try:
            ...     enforcer.enforce_budget("adw_123", cost_increment=0.5)
            ... except BudgetExceededError as e:
            ...     print(f"Budget exceeded: {e.budget_status.percent_used:.1f}%")
        """
        with self._lock:
            if not self.budget or not self.budget.enabled:
                # No budget enforcement - return dummy status
                cost = Decimal("0")
                if cost_increment is not None:
                    cost = Decimal(str(cost_increment))
                elif current_cost is not None:
                    cost = Decimal(str(current_cost))

                return BudgetStatus(
                    current_cost=cost,
                    max_cost=UNLIMITED_BUDGET,
                    remaining=UNLIMITED_BUDGET,
                    percent_used=Decimal("0"),
                    exceeded=False,
                    warning=False,
                )

            entry = self._get_or_create_entry(adw_id)

            # Determine projected cost without mutating ledger yet
            cost = entry.current_cost
            projected_cost = cost
            if cost_increment is not None:
                if cost_increment < 0:
                    raise ValueError("cost_increment must be non-negative")
                increment = Decimal(str(cost_increment))
                projected_cost = cost + increment
            elif current_cost is not None:
                # Backward compatibility: treat as absolute current_cost
                projected_cost = Decimal(str(current_cost))

            # Calculate status based on projected cost
            max_cost = self.budget.max_cost_usd
            cost = projected_cost
            remaining = max(Decimal("0"), max_cost - cost)
            percent_used = (cost / max_cost) * Decimal("100")
            exceeded = cost > max_cost
            warning = (cost / max_cost) >= self.budget.warning_threshold

            status = BudgetStatus(
                current_cost=cost,
                max_cost=max_cost,
                remaining=remaining,
                percent_used=percent_used,
                exceeded=exceeded,
                warning=warning,
            )

            # Emit warnings
            if warning and not entry.warned:
                logger.warning(
                    f"Budget warning for {adw_id}: "
                    f"{float(status.percent_used):.1f}% of budget used "
                    f"(${float(cost):.2f} / ${float(max_cost):.2f})"
                )
                entry.warned = True

            # Raise if exceeded
            if exceeded:
                logger.error(
                    f"Budget exceeded for {adw_id}: "
                    f"${float(cost):.2f} / ${float(max_cost):.2f} "
                    f"({float(percent_used):.1f}%)"
                )
                raise BudgetExceededError(
                    f"Budget exceeded for {adw_id}: "
                    f"${float(status.current_cost):.2f} / ${float(status.max_cost):.2f} "
                    f"({float(status.percent_used):.1f}%)",
                    budget_status=status,
                )

            # Safe to commit projected cost to ledger
            if cost_increment is not None or current_cost is not None:
                entry.current_cost = cost
                if entry.current_cost >= max_cost:
                    entry.exceeded = True

            return status

    def get_status(self, adw_id: str) -> BudgetStatus:
        """
        Get current budget status from ledger.

        Args:
            adw_id: Workflow identifier

        Returns:
            Current budget status

        Example:
            >>> status = enforcer.get_status("adw_123")
            >>> print(f"Current cost: ${status.current_cost}")
        """
        with self._lock:
            if not self.budget or not self.budget.enabled:
                return BudgetStatus(
                    current_cost=Decimal("0"),
                    max_cost=UNLIMITED_BUDGET,
                    remaining=UNLIMITED_BUDGET,
                    percent_used=Decimal("0"),
                    exceeded=False,
                    warning=False,
                )

            entry = self._get_or_create_entry(adw_id)
            max_cost = self.budget.max_cost_usd
            cost = entry.current_cost
            remaining = max(Decimal("0"), max_cost - cost)
            percent_used = (cost / max_cost) * Decimal("100")
            # Use persisted exceeded flag (set during concurrent access) or check current state
            exceeded = entry.exceeded or cost > max_cost
            warning = (cost / max_cost) >= self.budget.warning_threshold

            return BudgetStatus(
                current_cost=cost,
                max_cost=max_cost,
                remaining=remaining,
                percent_used=percent_used,
                exceeded=exceeded,
                warning=warning,
            )

    def can_afford(
        self,
        adw_id: str,
        current_cost: Optional[float] = None,
        additional_cost: float = 0.0
    ) -> bool:
        """
        Check if additional cost can be afforded.

        Args:
            adw_id: Workflow identifier
            current_cost: DEPRECATED - uses ledger if not provided
            additional_cost: Additional cost to check

        Returns:
            True if affordable

        Example:
            >>> # Recommended: check against ledger
            >>> if enforcer.can_afford("adw_123", additional_cost=1.0):
            ...     enforcer.enforce_budget("adw_123", cost_increment=1.0)
        """
        with self._lock:
            if not self.budget or not self.budget.enabled:
                return True

            if current_cost is None:
                # Use ledger
                entry = self._get_or_create_entry(adw_id)
                cost = entry.current_cost
            else:
                # Backward compatibility
                cost = Decimal(str(current_cost))

            additional = Decimal(str(additional_cost))
            projected_cost = cost + additional
            return projected_cost <= self.budget.max_cost_usd

    def set_budget(self, budget: Optional[Budget]) -> None:
        """
        Update budget configuration.

        Args:
            budget: New budget (None = disable enforcement)

        Example:
            >>> new_budget = Budget(max_cost_usd=20.0, period=BudgetPeriod.DAILY)
            >>> enforcer.set_budget(new_budget)
        """
        self.budget = budget

    def is_enabled(self) -> bool:
        """
        Check if budget enforcement is enabled.

        Returns:
            True if enabled

        Example:
            >>> if enforcer.is_enabled():
            ...     print("Budget enforcement is active")
        """
        return self.budget is not None and self.budget.enabled
