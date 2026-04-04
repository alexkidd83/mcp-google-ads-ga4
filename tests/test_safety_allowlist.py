"""Tests for per-account customer ID allowlist enforcement."""

import pytest

from adloop.config import SafetyConfig
from adloop.safety.guards import SafetyViolation, check_customer_id_allowed


@pytest.fixture
def allowlist_config():
    return SafetyConfig(
        allowed_customer_ids=["111-222-3333", "444-555-6666"],
    )


@pytest.fixture
def empty_allowlist_config():
    return SafetyConfig(allowed_customer_ids=[])


class TestCheckCustomerIdAllowed:
    def test_empty_allowlist_permits_any_id(self, empty_allowlist_config):
        """Backwards compat: no allowlist configured means all IDs allowed."""
        check_customer_id_allowed("999-999-9999", empty_allowlist_config)

    def test_id_present_in_allowlist_passes(self, allowlist_config):
        check_customer_id_allowed("111-222-3333", allowlist_config)

    def test_second_id_also_passes(self, allowlist_config):
        check_customer_id_allowed("444-555-6666", allowlist_config)

    def test_id_absent_raises_safety_violation(self, allowlist_config):
        with pytest.raises(SafetyViolation, match="not in the allowed list"):
            check_customer_id_allowed("999-000-0000", allowlist_config)

    def test_error_message_includes_rejected_id(self, allowlist_config):
        with pytest.raises(SafetyViolation, match="999-000-0000"):
            check_customer_id_allowed("999-000-0000", allowlist_config)

    def test_error_message_includes_config_hint(self, allowlist_config):
        with pytest.raises(SafetyViolation, match="config.yaml"):
            check_customer_id_allowed("999-000-0000", allowlist_config)

    @pytest.mark.parametrize(
        "customer_id",
        ["", "  ", "000-000-0000"],
        ids=["empty", "whitespace", "unlisted-id"],
    )
    def test_non_listed_ids_rejected(self, allowlist_config, customer_id):
        with pytest.raises(SafetyViolation):
            check_customer_id_allowed(customer_id, allowlist_config)
