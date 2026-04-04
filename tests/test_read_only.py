"""Tests for read-only mode enforcement."""

import adloop
from adloop.server import _check_read_only, _write_guards


class TestCheckReadOnly:
    def test_returns_none_when_not_read_only(self, monkeypatch):
        monkeypatch.setattr(adloop, "_read_only", False)
        assert _check_read_only() is None

    def test_returns_error_dict_when_read_only(self, monkeypatch):
        monkeypatch.setattr(adloop, "_read_only", True)
        result = _check_read_only()
        assert result is not None
        assert "error" in result
        assert "read-only" in result["error"].lower()

    def test_error_message_mentions_restart(self, monkeypatch):
        monkeypatch.setattr(adloop, "_read_only", True)
        result = _check_read_only()
        assert "--read-only" in result["error"]


class TestWriteGuards:
    def test_read_only_blocks_before_allowlist(self, monkeypatch):
        """Read-only should short-circuit before allowlist is even checked."""
        monkeypatch.setattr(adloop, "_read_only", True)
        # Pass a customer_id that would fail allowlist — but read-only fires first
        result = _write_guards(customer_id="bogus-id")
        assert result is not None
        assert "read-only" in result["error"].lower()

    def test_passes_when_not_read_only_and_no_customer(self, monkeypatch):
        monkeypatch.setattr(adloop, "_read_only", False)
        assert _write_guards(customer_id="") is None

    def test_passes_when_not_read_only_with_empty_allowlist(self, monkeypatch):
        """Empty allowlist + not read-only → no guard errors."""
        monkeypatch.setattr(adloop, "_read_only", False)
        assert _write_guards(customer_id="any-id") is None
