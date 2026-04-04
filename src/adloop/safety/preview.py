"""Change preview formatting — structured output for proposed mutations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ChangePlan:
    """A proposed change that must be confirmed before execution."""

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    operation: str = ""
    entity_type: str = ""
    entity_id: str = ""
    customer_id: str = ""
    changes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    requires_double_confirm: bool = False
    dry_run_result: dict[str, Any] | None = None

    def to_preview(self) -> dict[str, Any]:
        """Format as a human-readable preview dict for the AI to present."""
        return {
            "plan_id": self.plan_id,
            "operation": self.operation,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "customer_id": self.customer_id,
            "changes": self.changes,
            "requires_double_confirm": self.requires_double_confirm,
            "status": "PENDING_CONFIRMATION",
            "instructions": (
                "Review the changes above. To apply, call confirm_and_apply "
                f"with plan_id='{self.plan_id}' and dry_run=false."
            ),
        }


_pending_plans: dict[str, ChangePlan] = {}


def store_plan(plan: ChangePlan) -> None:
    """Store a plan for later retrieval by confirm_and_apply."""
    _purge_expired_plans()
    _pending_plans[plan.plan_id] = plan


def get_plan(plan_id: str) -> ChangePlan | None:
    """Retrieve a stored plan by ID."""
    return _pending_plans.get(plan_id)


def remove_plan(plan_id: str) -> None:
    """Remove a plan after execution."""
    _pending_plans.pop(plan_id, None)


def plan_age_minutes(plan: ChangePlan) -> float:
    """Return the age of a plan in minutes."""
    created = datetime.fromisoformat(plan.created_at)
    now = datetime.now(timezone.utc)
    return (now - created).total_seconds() / 60


def check_plan_ttl(plan: ChangePlan, ttl_minutes: int) -> str | None:
    """Return an error message if the plan has expired, else None."""
    age = plan_age_minutes(plan)
    if age > ttl_minutes:
        return (
            f"Plan {plan.plan_id} expired ({age:.0f} minutes old, "
            f"TTL is {ttl_minutes} minutes). Re-draft to create a fresh plan."
        )
    return None


def _purge_expired_plans(ttl_minutes: int = 60) -> None:
    """Remove plans older than ``ttl_minutes`` from the pending store.

    Uses a generous default (60 min) so cleanup catches clearly stale
    plans without racing the configured TTL checked at confirm time.
    """
    expired = [
        pid
        for pid, plan in _pending_plans.items()
        if plan_age_minutes(plan) > ttl_minutes
    ]
    for pid in expired:
        _pending_plans.pop(pid, None)
