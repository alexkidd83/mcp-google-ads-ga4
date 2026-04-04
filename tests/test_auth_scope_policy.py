"""Tests for adloop auth scope policy and token migration behavior."""

from __future__ import annotations

import json

import pytest

from adloop.auth import (
    _ga4_scopes,
    _oauth_flow,
    _oauth_scopes,
)
from adloop.config import AdLoopConfig, GoogleConfig


def _config_with_paths(token_path: str, credentials_path: str) -> AdLoopConfig:
    return AdLoopConfig(
        google=GoogleConfig(
            credentials_path=credentials_path,
            token_path=token_path,
        )
    )


def test_ga4_scopes_default_readonly(monkeypatch):
    monkeypatch.delenv("ADLOOP_GA4_SCOPE_MODE", raising=False)
    scopes = _ga4_scopes()
    assert "https://www.googleapis.com/auth/analytics.readonly" in scopes
    assert "https://www.googleapis.com/auth/analytics.edit" not in scopes


def test_ga4_scopes_edit_mode(monkeypatch):
    monkeypatch.setenv("ADLOOP_GA4_SCOPE_MODE", "edit")
    scopes = _ga4_scopes()
    assert "https://www.googleapis.com/auth/analytics.readonly" in scopes
    assert "https://www.googleapis.com/auth/analytics.edit" in scopes


def test_ga4_scopes_invalid_mode(monkeypatch):
    monkeypatch.setenv("ADLOOP_GA4_SCOPE_MODE", "invalid")
    with pytest.raises(ValueError, match="Invalid ADLOOP_GA4_SCOPE_MODE"):
        _ga4_scopes()


def test_oauth_scopes_always_include_adwords(monkeypatch):
    monkeypatch.setenv("ADLOOP_GA4_SCOPE_MODE", "readonly")
    assert "https://www.googleapis.com/auth/adwords" in _oauth_scopes()
    monkeypatch.setenv("ADLOOP_GA4_SCOPE_MODE", "edit")
    assert "https://www.googleapis.com/auth/adwords" in _oauth_scopes()


def test_oauth_flow_archives_token_when_scope_upgrade_required(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    creds_path = tmp_path / "credentials.json"

    # Existing token has readonly GA4 + Ads scopes.
    token_path.write_text(
        json.dumps(
            {
                "scopes": [
                    "https://www.googleapis.com/auth/analytics.readonly",
                    "https://www.googleapis.com/auth/adwords",
                ]
            }
        )
    )
    creds_path.write_text(json.dumps({"installed": {}}))

    cfg = _config_with_paths(str(token_path), str(creds_path))
    monkeypatch.setenv("ADLOOP_GA4_SCOPE_MODE", "edit")

    class DummyCreds:
        valid = True
        expired = False
        refresh_token = None

        def to_json(self):
            return json.dumps(
                {
                    "scopes": [
                        "https://www.googleapis.com/auth/analytics.readonly",
                        "https://www.googleapis.com/auth/analytics.edit",
                        "https://www.googleapis.com/auth/adwords",
                    ]
                }
            )

    class DummyFlow:
        def run_local_server(self, port: int = 0):  # noqa: ARG002
            return DummyCreds()

    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        lambda _path, _scopes: DummyFlow(),
    )

    creds = _oauth_flow(cfg)
    assert isinstance(creds, DummyCreds)
    assert token_path.exists()
    backups = list(tmp_path.glob("token.json.bak.*"))
    assert len(backups) == 1
