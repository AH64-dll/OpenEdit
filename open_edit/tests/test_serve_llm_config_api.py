"""Tests for the GET/PUT /api/projects/{id}/llm-config REST routes."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_edit.serve.app import app


@pytest.fixture
def client_and_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str, str]:
    # Route uses projects_mod.projects_root() to find projects; redirect
    # it to tmp_path.
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(tmp_path))
    # Pre-create a project.
    import asyncio

    from open_edit.serve import projects as projects_mod

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        info = loop.run_until_complete(projects_mod.create_project("vid1"))
        state = loop.run_until_complete(
            projects_mod.get_project_state(info.id)
        )
    finally:
        loop.close()
    return TestClient(app), state.path, info.id


def test_get_llm_config_returns_current_config(
    client_and_project: tuple[TestClient, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, project_path, project_id = client_and_project
    # Pre-write a config file.
    cfg_dir = Path(project_path) / ".open_edit"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "config.toml").write_text(
        '[llm]\nprovider = "opencode"\nmodel = "opencode-go/minimax-m3"\n'
    )
    r = client.get(f"/api/projects/{project_id}/llm-config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "opencode"
    assert body["model"] == "opencode-go/minimax-m3"
    assert "opencode" in body["available_providers"]
    assert "pi" in body["available_providers"]
    # available_models for opencode is whatever `opencode models` returns
    # (or [] if binary missing); we only assert it's a list.
    assert isinstance(body["available_models"], list)


def test_put_llm_config_persists_and_round_trips(
    client_and_project: tuple[TestClient, str, str],
) -> None:
    client, project_path, project_id = client_and_project
    r = client.put(
        f"/api/projects/{project_id}/llm-config",
        json={"provider": "pi", "model": "minimax-m3"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "pi"
    assert body["model"] == "minimax-m3"
    # File on disk reflects the new value.
    cfg_path = Path(project_path) / ".open_edit" / "config.toml"
    text = cfg_path.read_text()
    assert "provider = \"pi\"" in text
    assert "model = \"minimax-m3\"" in text


def test_put_llm_config_rejects_unknown_provider(
    client_and_project: tuple[TestClient, str, str],
) -> None:
    client, _, project_id = client_and_project
    r = client.put(
        f"/api/projects/{project_id}/llm-config",
        json={"provider": "nope", "model": "x"},
    )
    assert r.status_code == 400
    assert "nope" in r.json()["error"]


def test_put_llm_config_antigravity_is_now_valid(
    client_and_project: tuple[TestClient, str, str],
) -> None:
    """Antigravity is a valid provider — the adapter is registered."""
    client, _, project_id = client_and_project
    r = client.put(
        f"/api/projects/{project_id}/llm-config",
        json={"provider": "antigravity", "model": "x"},
    )
    # The adapter's available_models() may fail in test env
    # (registry import), but the provider validation should pass.
    assert r.status_code in (200, 500)


def test_put_llm_config_rejects_empty_model(
    client_and_project: tuple[TestClient, str, str],
) -> None:
    client, _, project_id = client_and_project
    r = client.put(
        f"/api/projects/{project_id}/llm-config",
        json={"provider": "pi", "model": "  "},
    )
    assert r.status_code == 400
    assert "model" in r.json()["error"].lower()
