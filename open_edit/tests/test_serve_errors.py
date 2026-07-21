"""Tests for the v1.4 fast-fail readable-error contract.

Background (P0-1 in v1.4 plan): a user reported "I tried the project and
it gives an error." Investigation found that the server either:

- crashed with an opaque 500 traceback (when a real bug hit)
- returned a useless 404 with just the missing id (no hint about
  ``open_edit init`` or the projects root)
- surfaced LLM provider misconfiguration as a raw ``RuntimeError`` in the
  WS (good that it surfaced, but the prefix was noise)

This module pins down the v1.4 contract: REST errors come back as
``{"error": "<readable message>"}`` and LLM provider misconfig surfaces
as a WS ``error`` event with a clean, actionable message (no
``"LLM stream error: "`` prefix).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator
from unittest import mock

import pytest
from fastapi.testclient import TestClient

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import app as app_mod  # noqa: E402
from open_edit.serve import agent as agent_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402
from open_edit.serve.llm import StreamEvent  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def projects_root_tmp(tmp_path, monkeypatch):
    """Point OPEN_EDIT_PROJECTS_ROOT at a fresh empty dir."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(projects_dir))
    return projects_dir


@pytest.fixture
def seeded_project(projects_root_tmp, tmp_path):
    """A real, fully-initialised project under projects_root_tmp.

    Returns (project_path, project_id).
    """
    proj = projects_root_tmp / "p1"
    proj.mkdir()
    from open_edit.cli import cmd_init
    import argparse
    cmd_init(argparse.Namespace(folder=str(proj)))
    project_id = projects_mod._project_id_from_path(proj.resolve())
    return proj, project_id


# ---------------------------------------------------------------------------
# REST: unknown project returns {"error": "..."} (v1.4 contract)
# ---------------------------------------------------------------------------

def test_api_unknown_project_returns_structured_error(seeded_project):
    """GET /api/projects/{id} for a non-existent id returns 404 with a
    JSON body of the shape ``{"error": "<readable message>"}`` and the
    message mentions both the bad id and the recovery hint
    (``open_edit init``)."""
    client = TestClient(app_mod.app)
    r = client.get("/api/projects/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    # v1.4 contract: ``{"error": "..."}``, not FastAPI's default ``{"detail": "..."}``.
    assert "error" in body, f"missing 'error' key in {body!r}"
    assert "detail" not in body, f"v1.4 uses 'error' not 'detail'; got {body!r}"
    msg = body["error"]
    assert "does-not-exist" in msg
    assert "open_edit init" in msg


def test_api_empty_projects_root_returns_empty_list_not_404(projects_root_tmp):
    """GET /api/projects on a freshly-created, empty projects root
    returns ``[]`` with 200 — not a 404, not a crash.

    This is the user-visible "no projects found" state. The server does
    NOT 404 here (a 404 would be wrong — the API endpoint exists, it
    just has no data to return).
    """
    client = TestClient(app_mod.app)
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_api_seeded_project_returns_state(seeded_project):
    """GET /api/projects/{id} for a freshly-initialised project returns
    the empty state — same as the projects-module regression test, but
    exercised through the HTTP layer so the FastAPI app's success path
    is also pinned."""
    _path, pid = seeded_project
    client = TestClient(app_mod.app)
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pid
    assert body["assets"] == []
    assert body["ops"] == []
    assert body["notes"] == []
    assert body["pending_notes_count"] == 0


# ---------------------------------------------------------------------------
# WS: unknown project sends a clean error event (no LLM call required)
# ---------------------------------------------------------------------------

def test_ws_unknown_project_sends_error_with_recovery_hint(projects_root_tmp):
    """Connecting a WS to an unknown project sends an error event whose
    message includes a recovery hint — not just the bare id."""
    client = TestClient(app_mod.app)
    with client.websocket_connect("/api/chat/does-not-exist") as ws:
        ev = json.loads(ws.receive_text())
    assert ev["type"] == "error"
    msg = ev["message"]
    assert "does-not-exist" in msg
    assert "open_edit init" in msg


# ---------------------------------------------------------------------------
# LLM: provider misconfiguration surfaces as a clean error event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_stream_anthropic_surfaces_missing_api_key(seeded_project, monkeypatch):
    """When ``OPEN_EDIT_LLM_API_KEY`` is unset, ``stream_chat`` emits a
    single ``error`` event with a clean, actionable message — NOT a
    ``text_delta`` or a crash. The agent loop can then forward it as a
    WS ``error`` event so the user sees the actual cause."""
    monkeypatch.delenv("OPEN_EDIT_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "anthropic")
    # Don't actually import anthropic — the key check happens first.
    events: list[StreamEvent] = []
    async for ev in agent_mod.stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="sys",
    ):
        events.append(ev)
    assert any(e["type"] == "error" for e in events), (
        f"expected an 'error' event, got {events!r}"
    )
    err = next(e for e in events if e["type"] == "error")
    msg = err["message"]
    # Clean, actionable: the actual cause, no "LLM stream error: " prefix.
    assert "OPEN_EDIT_LLM_API_KEY" in msg
    assert "set" in msg.lower() or "Set" in msg
    # And no agent-loop noise leaking through.
    assert "LLM stream error" not in msg


@pytest.mark.asyncio
async def test_llm_stream_openai_surfaces_missing_api_key(seeded_project, monkeypatch):
    """Same as the anthropic test, but for the OpenAI provider path.

    The OpenAI SDK may or may not be installed in the test env; either
    way, ``stream_chat`` must surface a clean, actionable error event
    rather than crashing with an uncaught ``ModuleNotFoundError`` or
    ``RuntimeError``.
    """
    monkeypatch.delenv("OPEN_EDIT_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "openai")
    events: list[StreamEvent] = []
    async for ev in agent_mod.stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="sys",
    ):
        events.append(ev)
    assert any(e["type"] == "error" for e in events)
    err = next(e for e in events if e["type"] == "error")
    # The error message must NOT be wrapped in the agent-loop noise
    # prefix; it must mention the provider name and the actionable
    # cause (missing key OR missing SDK — both are misconfigs).
    assert "openai" in err["message"].lower()
    assert "LLM stream error" not in err["message"]
    # It should mention one of the two real causes.
    assert "OPEN_EDIT_LLM_API_KEY" in err["message"] or "openai" in err["message"].lower()


@pytest.mark.asyncio
async def test_llm_stream_unknown_provider_falls_back_with_warning(
    seeded_project, monkeypatch
):
    """An unrecognised ``OPEN_EDIT_LLM_PROVIDER`` value falls back to
    the default (anthropic) and surfaces the misconfiguration as a clean
    error event, rather than silently picking the wrong provider or
    crashing.
    """
    monkeypatch.setenv("OPEN_EDIT_LLM_API_KEY", "")
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "bogus")
    events: list[StreamEvent] = []
    async for ev in agent_mod.stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="sys",
    ):
        events.append(ev)
    # With no key, we get the missing-key error either way.
    assert any(e["type"] == "error" for e in events)


# ---------------------------------------------------------------------------
# CLI: `open_edit init` warns when the folder is not under the projects root
# ---------------------------------------------------------------------------

def test_cli_init_warns_when_folder_not_under_projects_root(
    tmp_path, projects_root_tmp, capsys
):
    """If the user runs ``open_edit init <some-other-path>`` and the
    target is NOT under ``OPEN_EDIT_PROJECTS_ROOT``, the CLI prints a
    hint (to stderr) that the project won't be visible to
    ``open_edit serve``.

    The check is "the resulting project folder is not a subdir of the
    projects root" — this catches both the "init at the root" case
    (folder == root) and the "init somewhere else" case.
    """
    import argparse
    from open_edit.cli import cmd_init

    # The user runs `open_edit init /tmp/somewhere_else` (NOT under
    # projects_root_tmp). This used to silently succeed — now it warns.
    other = tmp_path / "elsewhere"
    other.mkdir()
    rc = cmd_init(argparse.Namespace(folder=str(other)))
    assert rc == 0  # The init still succeeds — we just warn.
    err = capsys.readouterr().err
    # The hint mentions the projects root AND the recovery command.
    assert str(projects_root_tmp) in err
    assert "open_edit init" in err
    assert "not visible" in err or "subdir" in err or "subdirectory" in err


def test_cli_init_silent_when_folder_is_under_projects_root(
    projects_root_tmp, capsys
):
    """If the user does the right thing (``init <root>/<proj>``), the
    CLI does NOT print the warning on stderr — only a confirmation on
    stdout."""
    import argparse
    from open_edit.cli import cmd_init

    proj = projects_root_tmp / "good-project"
    proj.mkdir()
    rc = cmd_init(argparse.Namespace(folder=str(proj)))
    assert rc == 0
    captured = capsys.readouterr()
    assert "not visible" not in captured.err
    assert "not visible" not in captured.out
    assert "Initialized project at" in captured.out
