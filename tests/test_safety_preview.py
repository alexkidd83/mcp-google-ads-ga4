"""Tests for plan TTL, age calculation, and expired-plan purging."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from adloop.safety.preview import (
    ChangePlan,
    _pending_plans,
    _purge_expired_plans,
    check_plan_ttl,
    get_plan,
    plan_age_minutes,
    remove_plan,
    store_plan,
)


@pytest.fixture(autouse=True)
def clear_plans():
    _pending_plans.clear()
    yield
    _pending_plans.clear()


def _make_plan(*, minutes_ago: float = 0, plan_id: str = "test-01") -> ChangePlan:
    """Factory: create a ChangePlan with created_at set N minutes in the past."""
    created = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return ChangePlan(
        plan_id=plan_id,
        operation="create_ad_group",
        entity_type="ad_group",
        customer_id="123",
        created_at=created.isoformat(),
    )


class TestPlanAgeMinutes:
    def test_fresh_plan_near_zero(self):
        plan = _make_plan(minutes_ago=0)
        assert plan_age_minutes(plan) < 0.1

    @pytest.mark.parametrize("minutes", [5, 15, 45, 90])
    def test_returns_correct_age(self, minutes):
        plan = _make_plan(minutes_ago=minutes)
        age = plan_age_minutes(plan)
        assert abs(age - minutes) < 0.1


class TestCheckPlanTTL:
    def test_fresh_plan_passes(self):
        plan = _make_plan(minutes_ago=5)
        assert check_plan_ttl(plan, ttl_minutes=30) is None

    def test_expired_plan_returns_error(self):
        plan = _make_plan(minutes_ago=45)
        error = check_plan_ttl(plan, ttl_minutes=30)
        assert error is not None
        assert plan.plan_id in error
        assert "45" in error  # age
        assert "30" in error  # TTL

    def test_boundary_plan_at_ttl_passes(self):
        """A plan exactly at TTL age should still pass (not strictly >)."""
        plan = _make_plan(minutes_ago=30)
        # Because of sub-second drift, create a plan at exactly 29.9 minutes
        plan_just_under = _make_plan(minutes_ago=29.9)
        assert check_plan_ttl(plan_just_under, ttl_minutes=30) is None

    def test_error_includes_re_draft_hint(self):
        plan = _make_plan(minutes_ago=60)
        error = check_plan_ttl(plan, ttl_minutes=30)
        assert "Re-draft" in error


class TestPurgeExpiredPlans:
    def test_removes_stale_keeps_fresh(self):
        fresh = _make_plan(minutes_ago=10, plan_id="fresh-01")
        stale = _make_plan(minutes_ago=120, plan_id="stale-01")
        _pending_plans["fresh-01"] = fresh
        _pending_plans["stale-01"] = stale

        _purge_expired_plans(ttl_minutes=60)

        assert "fresh-01" in _pending_plans
        assert "stale-01" not in _pending_plans

    def test_empty_store_no_error(self):
        _purge_expired_plans(ttl_minutes=60)
        assert len(_pending_plans) == 0

    def test_all_stale_clears_store(self):
        for i in range(5):
            plan = _make_plan(minutes_ago=120, plan_id=f"old-{i}")
            _pending_plans[plan.plan_id] = plan

        _purge_expired_plans(ttl_minutes=60)
        assert len(_pending_plans) == 0


class TestStorePlanTriggersPurge:
    def test_store_removes_expired_plans(self):
        """store_plan() calls _purge_expired_plans internally."""
        stale = _make_plan(minutes_ago=120, plan_id="stale-02")
        _pending_plans["stale-02"] = stale

        new_plan = _make_plan(minutes_ago=0, plan_id="new-01")
        store_plan(new_plan)

        assert "stale-02" not in _pending_plans
        assert get_plan("new-01") is not None

    def test_store_and_retrieve_round_trip(self):
        plan = _make_plan(minutes_ago=0, plan_id="rt-01")
        store_plan(plan)
        retrieved = get_plan("rt-01")
        assert retrieved is not None
        assert retrieved.plan_id == "rt-01"
        assert retrieved.operation == "create_ad_group"

    def test_remove_plan_deletes(self):
        plan = _make_plan(minutes_ago=0, plan_id="rm-01")
        store_plan(plan)
        remove_plan("rm-01")
        assert get_plan("rm-01") is None
