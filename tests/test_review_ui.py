"""Tests for review-only UI mode and UI config API."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_edit.serve import app as app_mod
from open_edit.serve.review_mode import auto_proxy_enabled, is_review_only


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OPEN_EDIT_REVIEW_ONLY", raising=False)
    monkeypatch.delenv("OPEN_EDIT_AUTO_PROXY", raising=False)
    return TestClient(app_mod.app)


def test_review_mode_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_REVIEW_ONLY", raising=False)
    assert is_review_only() is False
    monkeypatch.setenv("OPEN_EDIT_REVIEW_ONLY", "1")
    assert is_review_only() is True
    monkeypatch.delenv("OPEN_EDIT_AUTO_PROXY", raising=False)
    assert auto_proxy_enabled() is False
    monkeypatch.setenv("OPEN_EDIT_AUTO_PROXY", "true")
    assert auto_proxy_enabled() is True


def test_ui_config_full_mode(client: TestClient) -> None:
    resp = client.get("/api/ui-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "full"
    assert data["review_only"] is False


def test_ui_config_review_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_REVIEW_ONLY", "1")
    client = TestClient(app_mod.app)
    resp = client.get("/api/ui-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "review"
    assert data["review_only"] is True


def test_llm_config_blocked_in_review_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_REVIEW_ONLY", "1")
    client = TestClient(app_mod.app)
    resp = client.get("/api/projects/any/llm-config")
    assert resp.status_code == 404


def test_review_ui_uses_actual_profile_and_separate_source_copy() -> None:
    app = Path("open_edit/serve/static/app.js").read_text(encoding="utf-8")
    html = Path("open_edit/serve/static/index.html").read_text(encoding="utf-8")
    docs = Path("docs/MCP.md").read_text(encoding="utf-8")

    assert "Review artifact · 640×360" in app
    assert "Proxy 720p" not in app
    assert "540p" not in app
    assert "Source media" in app or "Source media" in html
    assert "timeline preview chunks" in docs.lower()
