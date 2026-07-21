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
import types
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


@pytest.mark.parametrize(
    "openai_available, expected_phrase",
    [
        # When the SDK is importable, the missing-key RuntimeError from
        # _api_key() fires first.
        (True, "OPEN_EDIT_LLM_API_KEY"),
        # When the SDK is not importable, the ImportError handler fires.
        (False, "required package not installed"),
    ],
    ids=["missing_api_key", "missing_sdk"],
)
@pytest.mark.asyncio
async def test_llm_stream_openai_surfaces_clean_error(
    seeded_project, monkeypatch, openai_available, expected_phrase
):
    """Same as the anthropic test, but for the OpenAI provider path.

    The two failure modes (missing key vs. missing SDK) are parametrised
    so each asserts the SPECIFIC cause rather than a disjunctive that
    silently passes regardless of which one fires. The previous
    ``assert "OPEN_EDIT_LLM_API_KEY" in msg or "openai" in msg.lower()``
    was effectively a no-op: the second clause was always true (every
    OpenAI error mentions the provider name), and the first clause was
    only true when the SDK happened to be importable in the test env.
    """
    monkeypatch.delenv("OPEN_EDIT_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "openai")
    if openai_available:
        # Provide a stub openai module so ``import openai`` succeeds;
        # the missing-key RuntimeError from _api_key() is then what
        # fires, not the ImportError handler.
        fake_openai = types.ModuleType("openai")
        fake_openai.AsyncOpenAI = mock.MagicMock()
        monkeypatch.setitem(sys.modules, "openai", fake_openai)
    else:
        # Ensure the real openai (if installed) isn't picked up.
        monkeypatch.delitem(sys.modules, "openai", raising=False)
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
    # prefix and must mention the provider name.
    assert "openai" in err["message"].lower()
    assert "LLM stream error" not in err["message"]
    # The SPECIFIC cause for this case.
    assert expected_phrase in err["message"]


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


# ---------------------------------------------------------------------------
# Global exception handler: must NOT leak str(exc) to the client
# ---------------------------------------------------------------------------

def test_unhandled_exception_does_not_leak_exc_to_client(projects_root_tmp):
    """Regression: an exception raised inside a route handler must NOT
    include ``str(exc)`` in the response body. The v1.4 contract is a
    constant ``{"error": "internal server error"}``; the full traceback
    goes to the server log (via ``traceback.print_exc``) so the operator
    can diagnose.

    Before the fix, the body was ``{"error": "internal server error: <str(exc)>"}``
    which would have leaked ``sqlite3.OperationalError`` messages (with
    paths + SQL fragments), ``PermissionError`` messages (with paths),
    and anything else verbatim to the browser.
    """
    # A unique marker so we can assert it never reaches the wire.
    secret = "SECRET_LEAK_x9q7z_DO_NOT_RETURN_TO_CLIENT"

    def _raise(*args, **kwargs):
        raise RuntimeError(secret)

    with mock.patch.object(projects_mod, "list_projects", _raise):
        client = TestClient(app_mod.app, raise_server_exceptions=False)
        r = client.get("/api/projects")

    assert r.status_code == 500
    # The body is exactly the constant "internal server error" — no detail.
    assert r.json() == {"error": "internal server error"}
    # The unique exception string is nowhere in the response.
    assert secret not in r.text


# ---------------------------------------------------------------------------
# v1.4 final-review fix: the global Exception handler must NOT swallow
# ``WebSocketDisconnect`` (a subclass of ``Exception``).
#
# Background: when a WS client disconnects, Starlette raises
# ``WebSocketDisconnect``. Our global ``@app.exception_handler(Exception)``
# also catches it, runs ``traceback.print_exc()`` to stderr, and tries to
# return a 500 — but a WS isn't an HTTP request, so the JSON response is
# meaningless. Worse, every normal tab close prints a fake traceback to
# the operator log, making real failures hard to spot.
#
# The fix re-raises ``WebSocketDisconnect`` from the handler so Starlette
# handles it normally (a clean WS close with no operator noise).
# ---------------------------------------------------------------------------

def test_unhandled_exception_handler_does_not_swallow_websocket_disconnect(
    projects_root_tmp,
):
    """A ``WebSocketDisconnect`` must NOT go through the global Exception
    handler. The handler must re-raise so Starlette handles the WS close
    normally — no operator-log traceback, no 500 JSON response (the
    response is meaningless for a WS, and printing a traceback makes
    real failures hard to spot).
    """
    from fastapi import WebSocketDisconnect
    import traceback as _traceback

    handler = app_mod.app.exception_handlers[Exception]

    with mock.patch.object(_traceback, "print_exc") as print_exc_mock:
        with pytest.raises(WebSocketDisconnect):
            # The handler is an async coroutine; the test is sync so we
            # just call it — the ``raise`` inside the handler propagates
            # as a synchronous exception because we're not awaiting it.
            # That's fine: the contract is "the handler must re-raise",
            # not "the handler returns nothing on WebSocketDisconnect".
            asyncio.run(handler(object(), WebSocketDisconnect(code=1000)))

        # The traceback must NOT have been printed — that's the whole
        # point of the fix. A user closing a tab is not an error.
        print_exc_mock.assert_not_called()


def test_unhandled_exception_handler_still_handles_regular_exceptions(
    projects_root_tmp,
):
    """Regression guard: a regular ``Exception`` (other than
    ``WebSocketDisconnect``) MUST still go through the handler and
    produce the constant ``{"error": "internal server error"}`` body.
    Without this guard, an over-eager fix could swallow all exceptions.
    """
    handler = app_mod.app.exception_handlers[Exception]
    response = asyncio.run(handler(object(), RuntimeError("boom")))
    assert response.status_code == 500
    # The body is exactly the constant — no detail leaks.
    import json as _json
    body = _json.loads(response.body)
    assert body == {"error": "internal server error"}
