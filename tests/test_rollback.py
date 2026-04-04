"""Tests for rollback mechanism — plan generation, audit log readers, integration."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest

from adloop.safety.audit import (
    get_mutation_by_id,
    log_mutation,
    read_recent_mutations,
)
from adloop.safety.rollback import generate_rollback_plan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def log_file(tmp_path: Path) -> str:
    """Return a temporary audit log file path."""
    return str(tmp_path / "test_audit.log")


def _make_entry(
    *,
    operation: str = "pause_entity",
    entity_type: str = "campaign",
    entity_id: str = "12345",
    customer_id: str = "111-222-3333",
    changes: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    entry_id: str = "",
    dry_run: bool = False,
    result: str = "success",
) -> dict[str, Any]:
    """Build a synthetic audit entry dict for testing."""
    return {
        "entry_id": entry_id or str(uuid.uuid4()),
        "timestamp": "2026-03-31T12:00:00+00:00",
        "operation": operation,
        "customer_id": customer_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "changes": changes or {},
        "dry_run": dry_run,
        "result": result,
        "previous_state": previous_state,
    }


# ---------------------------------------------------------------------------
# generate_rollback_plan tests
# ---------------------------------------------------------------------------


class TestGenerateRollbackPlanStatusChange:
    """Rollback for pause_entity / enable_entity should produce opposite status."""

    def test_pause_generates_enable(self):
        entry = _make_entry(
            operation="pause_entity",
            entity_type="campaign",
            entity_id="99",
            changes={"target_status": "PAUSED"},
            previous_state={"status": "ENABLED"},
        )
        plan = generate_rollback_plan(entry)

        assert plan is not None
        assert plan["operation"] == "enable_entity"
        assert plan["changes"]["target_status"] == "ENABLED"
        assert plan["entity_id"] == "99"
        assert plan["entity_type"] == "campaign"

    def test_enable_generates_pause(self):
        entry = _make_entry(
            operation="enable_entity",
            entity_type="ad_group",
            entity_id="42",
            changes={"target_status": "ENABLED"},
            previous_state={"status": "PAUSED"},
        )
        plan = generate_rollback_plan(entry)

        assert plan is not None
        assert plan["operation"] == "pause_entity"
        assert plan["changes"]["target_status"] == "PAUSED"

    def test_status_change_without_previous_state_returns_none(self):
        entry = _make_entry(
            operation="pause_entity",
            changes={"target_status": "PAUSED"},
            previous_state=None,
        )
        assert generate_rollback_plan(entry) is None


class TestGenerateRollbackPlanBudgetUpdate:
    """Rollback for update_campaign should produce update with previous values."""

    def test_budget_rollback(self):
        entry = _make_entry(
            operation="update_campaign",
            entity_type="campaign",
            entity_id="555",
            changes={"campaign_id": "555", "daily_budget": 50.0},
            previous_state={"daily_budget": 25.0, "status": "ENABLED"},
        )
        plan = generate_rollback_plan(entry)

        assert plan is not None
        assert plan["operation"] == "update_campaign"
        assert plan["changes"]["daily_budget"] == 25.0
        assert plan["changes"]["campaign_id"] == "555"

    def test_bidding_strategy_rollback(self):
        entry = _make_entry(
            operation="update_campaign",
            entity_type="campaign",
            entity_id="555",
            changes={
                "campaign_id": "555",
                "bidding_strategy": "TARGET_CPA",
                "target_cpa": 10.0,
            },
            previous_state={
                "bidding_strategy": "MAXIMIZE_CONVERSIONS",
                "target_cpa": 0,
            },
        )
        plan = generate_rollback_plan(entry)

        assert plan is not None
        assert plan["changes"]["bidding_strategy"] == "MAXIMIZE_CONVERSIONS"
        assert plan["changes"]["target_cpa"] == 0

    def test_geo_targets_rollback(self):
        entry = _make_entry(
            operation="update_campaign",
            entity_type="campaign",
            entity_id="555",
            changes={"campaign_id": "555", "geo_target_ids": ["2840"]},
            previous_state={"geo_target_ids": ["2276", "2040"]},
        )
        plan = generate_rollback_plan(entry)

        assert plan is not None
        assert plan["changes"]["geo_target_ids"] == ["2276", "2040"]


class TestGenerateRollbackPlanAdGroup:
    """Rollback for update_ad_group restores name and CPC."""

    def test_name_rollback(self):
        entry = _make_entry(
            operation="update_ad_group",
            entity_type="ad_group",
            entity_id="77",
            changes={"ad_group_id": "77", "ad_group_name": "New Name"},
            previous_state={"ad_group_name": "Old Name", "max_cpc": 1.5},
        )
        plan = generate_rollback_plan(entry)

        assert plan is not None
        assert plan["changes"]["ad_group_name"] == "Old Name"

    def test_cpc_rollback(self):
        entry = _make_entry(
            operation="update_ad_group",
            entity_type="ad_group",
            entity_id="77",
            changes={"ad_group_id": "77", "max_cpc": 3.0},
            previous_state={"ad_group_name": "My Group", "max_cpc": 1.5},
        )
        plan = generate_rollback_plan(entry)

        assert plan is not None
        assert plan["changes"]["max_cpc"] == 1.5


class TestGenerateRollbackPlanIrreversible:
    """Irreversible operations must return None."""

    def test_remove_entity_returns_none(self):
        entry = _make_entry(
            operation="remove_entity",
            changes={"action": "REMOVE"},
            previous_state={"status": "ENABLED"},
        )
        assert generate_rollback_plan(entry) is None

    def test_create_campaign_returns_none(self):
        entry = _make_entry(
            operation="create_campaign",
            changes={"campaign_name": "Test"},
        )
        assert generate_rollback_plan(entry) is None

    def test_add_keywords_returns_none(self):
        entry = _make_entry(
            operation="add_keywords",
            changes={"keywords": [{"text": "test", "match_type": "EXACT"}]},
        )
        assert generate_rollback_plan(entry) is None

    def test_unknown_operation_returns_none(self):
        entry = _make_entry(operation="something_new")
        assert generate_rollback_plan(entry) is None


class TestGenerateRollbackPlanEdgeCases:
    """Edge cases: missing fields, empty previous_state."""

    def test_empty_previous_state_returns_none(self):
        entry = _make_entry(
            operation="update_campaign",
            changes={"campaign_id": "1", "daily_budget": 10.0},
            previous_state={},
        )
        assert generate_rollback_plan(entry) is None

    def test_rollback_includes_entry_id_reference(self):
        entry = _make_entry(
            operation="pause_entity",
            entry_id="abc-123",
            changes={"target_status": "PAUSED"},
            previous_state={"status": "ENABLED"},
        )
        plan = generate_rollback_plan(entry)
        assert plan is not None
        assert plan["rollback_of"] == "abc-123"

    def test_update_campaign_no_matching_fields_returns_none(self):
        """If previous_state has no fields matching the changes, return None."""
        entry = _make_entry(
            operation="update_campaign",
            entity_id="1",
            changes={"campaign_id": "1", "daily_budget": 10.0},
            previous_state={"status": "ENABLED"},  # no daily_budget
        )
        assert generate_rollback_plan(entry) is None


# ---------------------------------------------------------------------------
# Audit log reader tests
# ---------------------------------------------------------------------------


class TestReadRecentMutations:
    """read_recent_mutations reads JSONL correctly."""

    def test_reads_jsonl(self, log_file: str):
        # Write 3 real mutations and 1 dry-run
        log_mutation(log_file, operation="op1", dry_run=False, result="success")
        log_mutation(log_file, operation="op2", dry_run=True, result="dry_run_success")
        log_mutation(log_file, operation="op3", dry_run=False, result="success")
        log_mutation(log_file, operation="op4", dry_run=False, result="success")

        entries = read_recent_mutations(log_file, limit=10)

        # Should skip dry-run, return 3 entries newest-first
        assert len(entries) == 3
        assert entries[0]["operation"] == "op4"
        assert entries[1]["operation"] == "op3"
        assert entries[2]["operation"] == "op1"

    def test_respects_limit(self, log_file: str):
        for i in range(10):
            log_mutation(log_file, operation=f"op{i}", dry_run=False)

        entries = read_recent_mutations(log_file, limit=3)
        assert len(entries) == 3
        # Should be the 3 most recent
        assert entries[0]["operation"] == "op9"

    def test_empty_file_returns_empty(self, log_file: str):
        Path(log_file).touch()
        assert read_recent_mutations(log_file) == []

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert read_recent_mutations(str(tmp_path / "nonexistent.log")) == []

    def test_entries_have_entry_id(self, log_file: str):
        log_mutation(log_file, operation="test_op", dry_run=False)
        entries = read_recent_mutations(log_file, limit=1)
        assert len(entries) == 1
        assert "entry_id" in entries[0]
        # Validate it looks like a UUID
        uuid.UUID(entries[0]["entry_id"])


class TestGetMutationById:
    """get_mutation_by_id finds specific entries."""

    def test_finds_entry(self, log_file: str):
        entry_id1 = log_mutation(log_file, operation="first", dry_run=False)
        entry_id2 = log_mutation(log_file, operation="second", dry_run=False)

        found = get_mutation_by_id(log_file, entry_id2)
        assert found is not None
        assert found["operation"] == "second"
        assert found["entry_id"] == entry_id2

    def test_returns_none_for_missing_id(self, log_file: str):
        log_mutation(log_file, operation="test", dry_run=False)
        assert get_mutation_by_id(log_file, "nonexistent-id") is None

    def test_returns_none_for_missing_file(self, tmp_path: Path):
        assert get_mutation_by_id(str(tmp_path / "nope.log"), "any-id") is None

    def test_finds_entry_with_previous_state(self, log_file: str):
        entry_id = log_mutation(
            log_file,
            operation="pause_entity",
            dry_run=False,
            previous_state={"status": "ENABLED"},
        )
        found = get_mutation_by_id(log_file, entry_id)
        assert found is not None
        assert found["previous_state"] == {"status": "ENABLED"}


class TestLogMutationReturnsEntryId:
    """log_mutation must return a valid entry_id string."""

    def test_returns_uuid_string(self, log_file: str):
        entry_id = log_mutation(log_file, operation="test", dry_run=False)
        assert isinstance(entry_id, str)
        uuid.UUID(entry_id)  # Validates format

    def test_entry_id_in_written_record(self, log_file: str):
        entry_id = log_mutation(log_file, operation="test", dry_run=False)
        with open(log_file) as f:
            record = json.loads(f.readline())
        assert record["entry_id"] == entry_id


class TestLogMutationPreviousState:
    """log_mutation correctly includes previous_state when provided."""

    def test_previous_state_included(self, log_file: str):
        log_mutation(
            log_file,
            operation="pause_entity",
            dry_run=False,
            previous_state={"status": "ENABLED"},
        )
        with open(log_file) as f:
            record = json.loads(f.readline())
        assert record["previous_state"] == {"status": "ENABLED"}

    def test_previous_state_absent_when_not_provided(self, log_file: str):
        log_mutation(log_file, operation="create_campaign", dry_run=False)
        with open(log_file) as f:
            record = json.loads(f.readline())
        assert "previous_state" not in record

    def test_backwards_compatible_no_previous_state(self, log_file: str):
        """Old-style entries without previous_state still work."""
        # Write a legacy-format entry directly
        legacy = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "operation": "pause_entity",
            "customer_id": "111",
            "entity_type": "campaign",
            "entity_id": "1",
            "changes": {},
            "dry_run": False,
            "result": "success",
            "error": "",
        }
        with open(log_file, "w") as f:
            f.write(json.dumps(legacy) + "\n")

        entries = read_recent_mutations(log_file)
        assert len(entries) == 1
        assert "previous_state" not in entries[0]
        assert "entry_id" not in entries[0]  # Legacy entries lack entry_id
