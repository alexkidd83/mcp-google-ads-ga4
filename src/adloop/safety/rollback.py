"""Rollback plan generation — reverse a previously applied mutation.

Reversible operations:
  - update_campaign  (budget, bidding, geo targets, language targets, status)
  - update_ad_group  (name, CPC bid)
  - pause_entity     (restore previous status)
  - enable_entity    (restore previous status)

Irreversible operations (returns None):
  - remove_entity    (removed entities cannot be re-enabled)
  - create_*         (rollback = pause + remove, not automated here)
"""

from __future__ import annotations

from typing import Any


# Operations that can be meaningfully reversed when previous_state exists
_REVERSIBLE_OPERATIONS = frozenset({
    "update_campaign",
    "update_ad_group",
    "pause_entity",
    "enable_entity",
})

# Operations that cannot be reversed
_IRREVERSIBLE_OPERATIONS = frozenset({
    "remove_entity",
    "create_campaign",
    "create_ad_group",
    "create_responsive_search_ad",
    "add_keywords",
    "add_negative_keywords",
    "create_callouts",
    "create_structured_snippets",
    "create_image_assets",
    "create_sitelinks",
})


def generate_rollback_plan(audit_entry: dict[str, Any]) -> dict[str, Any] | None:
    """Generate a ChangePlan dict that reverses the given audit entry.

    Returns ``None`` for irreversible operations (remove, create) or when
    the audit entry lacks the ``previous_state`` needed to build the rollback.

    The returned dict has the shape expected by the draft tools so the
    rollback goes through the normal draft -> confirm flow.
    """
    operation = audit_entry.get("operation", "")

    if operation in _IRREVERSIBLE_OPERATIONS:
        return None

    if operation not in _REVERSIBLE_OPERATIONS:
        return None

    previous_state = audit_entry.get("previous_state")
    if not previous_state:
        return None

    if operation in ("pause_entity", "enable_entity"):
        return _rollback_status_change(audit_entry, previous_state)

    if operation == "update_campaign":
        return _rollback_update_campaign(audit_entry, previous_state)

    if operation == "update_ad_group":
        return _rollback_update_ad_group(audit_entry, previous_state)

    return None


def _rollback_status_change(
    entry: dict[str, Any],
    previous_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Generate a status-change rollback plan."""
    prev_status = previous_state.get("status")
    if not prev_status:
        return None

    # Determine which draft operation to use based on previous status
    if prev_status == "ENABLED":
        rollback_operation = "enable_entity"
    elif prev_status == "PAUSED":
        rollback_operation = "pause_entity"
    else:
        return None

    return {
        "operation": rollback_operation,
        "entity_type": entry.get("entity_type", ""),
        "entity_id": entry.get("entity_id", ""),
        "customer_id": entry.get("customer_id", ""),
        "changes": {"target_status": prev_status},
        "rollback_of": entry.get("entry_id", ""),
        "reason": f"Rollback: restore {entry.get('entity_type', '')} "
                  f"{entry.get('entity_id', '')} to {prev_status}",
    }


def _rollback_update_campaign(
    entry: dict[str, Any],
    previous_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Generate a campaign-update rollback plan using previous_state values."""
    campaign_id = entry.get("entity_id", "")
    if not campaign_id:
        return None

    changes: dict[str, Any] = {"campaign_id": campaign_id}
    applied_changes = entry.get("changes", {})

    # Restore only the fields that were changed
    if "daily_budget" in applied_changes and "daily_budget" in previous_state:
        changes["daily_budget"] = previous_state["daily_budget"]

    if "bidding_strategy" in applied_changes and "bidding_strategy" in previous_state:
        changes["bidding_strategy"] = previous_state["bidding_strategy"]
        if "target_cpa" in previous_state:
            changes["target_cpa"] = previous_state["target_cpa"]
        if "target_roas" in previous_state:
            changes["target_roas"] = previous_state["target_roas"]

    if "geo_target_ids" in applied_changes and "geo_target_ids" in previous_state:
        changes["geo_target_ids"] = previous_state["geo_target_ids"]

    if "language_ids" in applied_changes and "language_ids" in previous_state:
        changes["language_ids"] = previous_state["language_ids"]

    if "max_cpc" in applied_changes and "max_cpc" in previous_state:
        changes["max_cpc"] = previous_state["max_cpc"]

    if "search_partners_enabled" in applied_changes and "search_partners_enabled" in previous_state:
        changes["search_partners_enabled"] = previous_state["search_partners_enabled"]

    if "display_network_enabled" in applied_changes and "display_network_enabled" in previous_state:
        changes["display_network_enabled"] = previous_state["display_network_enabled"]

    # Only the campaign_id means nothing actually changed to roll back
    if len(changes) <= 1:
        return None

    return {
        "operation": "update_campaign",
        "entity_type": "campaign",
        "entity_id": campaign_id,
        "customer_id": entry.get("customer_id", ""),
        "changes": changes,
        "rollback_of": entry.get("entry_id", ""),
        "reason": f"Rollback: restore campaign {campaign_id} to previous state",
    }


def _rollback_update_ad_group(
    entry: dict[str, Any],
    previous_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Generate an ad-group-update rollback plan."""
    ad_group_id = entry.get("entity_id", "")
    if not ad_group_id:
        return None

    changes: dict[str, Any] = {"ad_group_id": ad_group_id}
    applied_changes = entry.get("changes", {})

    if "ad_group_name" in applied_changes and "ad_group_name" in previous_state:
        changes["ad_group_name"] = previous_state["ad_group_name"]

    if "max_cpc" in applied_changes and "max_cpc" in previous_state:
        changes["max_cpc"] = previous_state["max_cpc"]

    if len(changes) <= 1:
        return None

    return {
        "operation": "update_ad_group",
        "entity_type": "ad_group",
        "entity_id": ad_group_id,
        "customer_id": entry.get("customer_id", ""),
        "changes": changes,
        "rollback_of": entry.get("entry_id", ""),
        "reason": f"Rollback: restore ad group {ad_group_id} to previous state",
    }
