"""Task 5 UI tests — verifies the /api/apps contract and static app.js wiring.

No browser is used. The DOM-level checks read the static file and assert the
literal element IDs / WS message types the brief requires.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from fastapi.testclient import TestClient


_REPO_ROOT = Path(__file__).resolve().parents[1]
_APP_JS = _REPO_ROOT / "phase4_chat_ui" / "static" / "app.js"


def _make_client():
    import importlib
    from phase4_chat_ui.app import create_app

    app = create_app(project="/tmp/pyagent_task5_test.kdenlive")
    return TestClient(app)


def test_api_apps_contract():
    client = _make_client()
    resp = client.get("/api/apps")
    assert resp.status_code == 200
    data = resp.json()
    assert "apps" in data
    apps = data["apps"]
    assert isinstance(apps, list)
    assert len(apps) > 0

    ids = {a["id"] for a in apps}
    assert "piagent" in ids
    assert "antigravity" in ids

    for a in apps:
        assert "id" in a
        assert "name" in a
        assert "available" in a
        assert "models" in a
        assert isinstance(a["models"], list)

    # Available apps must expose non-empty models with id/name.
    for a in apps:
        if a["available"]:
            assert len(a["models"]) > 0, f"available app {a['id']} has no models"
            for m in a["models"]:
                assert "id" in m and "name" in m

    # Anti-gravity is shown but disabled.
    anti = next(a for a in apps if a["id"] == "antigravity")
    assert anti["available"] is False


def test_app_js_references_expected_ids_and_types():
    assert _APP_JS.exists(), f"static/app.js not found at {_APP_JS}"
    js = _APP_JS.read_text(encoding="utf-8")

    required = [
        "agent-select",
        "model-select",
        "set_app",
        "set_model",
        "app_changed",
        "model_changed",
        "loadApps",
    ]
    for token in required:
        assert token in js, f"expected {token!r} to appear in app.js"
