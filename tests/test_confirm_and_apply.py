"""Tests for confirm_and_apply double-confirmation wiring and TTL enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from adloop.ads.write import confirm_and_apply
from adloop.config import AdLoopConfig, AdsConfig, SafetyConfig
from adloop.safety.preview import (
    ChangePlan,
    _pending_plans,
    get_plan,
    store_plan,
)


@pytest.fixture(autouse=True)
def clear_plans():
    _pending_plans.clear()
    yield
    _pending_plans.clear()


@pytest.fixture
def config():
    return AdLoopConfig(
        ads=AdsConfig(customer_id="123-456-7890", developer_token="test"),
        safety=SafetyConfig(
            max_daily_budget=50.0,
            require_dry_run=True,
            plan_ttl_minutes=30,
        ),
    )


def _store_plan(
    *,
    operation: str = "create_ad_group",
    plan_id: str = "abc123",
    minutes_ago: float = 0,
    changes: dict | None = None,
) -> ChangePlan:
    """Factory: create and store a ChangePlan."""
    created = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    plan = ChangePlan(
        plan_id=plan_id,
        operation=operation,
        entity_type="ad_group",
        customer_id="123-456-7890",
        changes=changes or {"ad_group_name": "Test"},
        created_at=created.isoformat(),
    )
    store_plan(plan)
    return plan


class TestDoubleConfirmationDelete:
    def test_delete_without_confirmed_returns_error(self, config):
        _store_plan(operation="remove_entity", plan_id="del-01")
        result = confirm_and_apply(config, plan_id="del-01", confirmed=False)

        assert "error" in result
        assert result["requires_double_confirm"] is True
        assert "confirmed=true" in result["error"]

    def test_delete_with_confirmed_proceeds(self, config):
        """With confirmed=True, the delete should reach dry-run (not be blocked)."""
        _store_plan(operation="remove_entity", plan_id="del-02")
        result = confirm_and_apply(config, plan_id="del-02", confirmed=True)

        # require_dry_run=True, so it should succeed as dry run
        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["plan_id"] == "del-02"


class TestDoubleConfirmationBudget:
    def test_large_budget_increase_without_confirmed_returns_error(self, config):
        _store_plan(
            operation="update_campaign",
            plan_id="bud-01",
            changes={"current_budget": 10.0, "daily_budget": 20.0},
        )
        result = confirm_and_apply(config, plan_id="bud-01", confirmed=False)

        assert "error" in result
        assert result["requires_double_confirm"] is True

    def test_small_budget_increase_proceeds_without_confirmed(self, config):
        """Budget increase <50% should not require double confirmation."""
        _store_plan(
            operation="update_campaign",
            plan_id="bud-02",
            changes={"current_budget": 10.0, "daily_budget": 14.0},
        )
        result = confirm_and_apply(config, plan_id="bud-02", confirmed=False)

        assert result["status"] == "DRY_RUN_SUCCESS"


class TestNormalOperationNoConfirmNeeded:
    def test_create_proceeds_without_confirmed(self, config):
        _store_plan(operation="create_ad_group", plan_id="norm-01")
        result = confirm_and_apply(config, plan_id="norm-01", confirmed=False)

        assert result["status"] == "DRY_RUN_SUCCESS"

    def test_pause_proceeds_without_confirmed(self, config):
        _store_plan(operation="pause_campaign", plan_id="norm-02")
        result = confirm_and_apply(config, plan_id="norm-02", confirmed=False)

        assert result["status"] == "DRY_RUN_SUCCESS"


class TestPlanTTLEnforcement:
    def test_expired_plan_returns_error(self, config):
        _store_plan(plan_id="exp-01", minutes_ago=45)  # TTL is 30
        result = confirm_and_apply(config, plan_id="exp-01")

        assert "error" in result
        assert "expired" in result["error"].lower()

    def test_expired_plan_is_removed_from_store(self, config):
        _store_plan(plan_id="exp-02", minutes_ago=45)
        confirm_and_apply(config, plan_id="exp-02")

        assert get_plan("exp-02") is None

    def test_fresh_plan_passes_ttl(self, config):
        _store_plan(plan_id="fresh-01", minutes_ago=5)
        result = confirm_and_apply(config, plan_id="fresh-01")

        assert result["status"] == "DRY_RUN_SUCCESS"


class TestMissingPlan:
    def test_nonexistent_plan_returns_error(self, config):
        result = confirm_and_apply(config, plan_id="does-not-exist")

        assert "error" in result
        assert "does-not-exist" in result["error"]
