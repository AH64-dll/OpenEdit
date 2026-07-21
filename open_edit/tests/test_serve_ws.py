"""Tests for the WebSocket chat endpoint.

Uses FastAPI's ``TestClient.websocket_connect`` to verify the WS protocol
without spinning up a real server or making real LLM calls. The LLM and
tool execution are mocked the same way as in ``test_serve_agent``.
"""
from __future__ import annotations

import json
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

from open_edit.serve import agent as agent_mod  # noqa: E402
from open_edit.serve import app as app_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402
from open_edit.serve.llm import StreamEvent  # noqa: E402


# ---------------------------------------------------------------------------
# Mocks (same shape as test_serve_agent, kept local for isolation)
# ---------------------------------------------------------------------------

async def _mock_stream_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None = None,
    project_path: str | None = None,
) -> AsyncIterator[StreamEvent]:
    assistant_turns = sum(1 for m in messages if m.get("role") == "assistant")
    if assistant_turns == 0:
        yield {"type": "text_delta", "text": "Checking your assets."}
        yield {
            "type": "tool_use",
            "id": "call_1",
            "name": "list_assets",
            "input": {},
        }
        yield {"type": "done", "stop_reason": "tool_use"}
    else:
        yield {"type": "text_delta", "text": "You have 1 asset: intro.mp4."}
        yield {"type": "done", "stop_reason": "end_turn"}


def _mock_execute_tool(name, args, project_path):
    return {"tool": name, "args": args, "result": {"assets": [{"hash": "h1"}]}}


@pytest.fixture
def patched_ws(monkeypatch, tmp_path):
    """Patch the agent loop's I/O so the WS endpoint works without a real
    project on disk or a real LLM."""
    fake_state = projects_mod.ProjectState(
        id="wstest",
        name="wstest",
        path=str(tmp_path),
        assets=[projects_mod.AssetInfo(hash="h1", filename="intro.mp4", duration_s=10.0)],
        ops=[],
        timeline=projects_mod.TimelineSummary(),
        pending_notes_count=0,
    )

    async def fake_get_state(project_id):
        if project_id != "wstest":
            raise KeyError(project_id)
        return fake_state

    def fake_resolve(project_id):
        if project_id != "wstest":
            return None
        return tmp_path

    monkeypatch.setattr(agent_mod, "stream_chat", _mock_stream_chat)
    monkeypatch.setattr(agent_mod, "_execute_tool", _mock_execute_tool)
    monkeypatch.setattr(projects_mod, "get_project_state", fake_get_state)
    monkeypatch.setattr(projects_mod, "_resolve_project_by_id", fake_resolve)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ws_ready_on_connect(patched_ws):
    """Server sends a `ready` event right after accepting the WS."""
    client = TestClient(app_mod.app)
    with client.websocket_connect("/api/chat/wstest") as ws:
        ready = json.loads(ws.receive_text())
        assert ready["type"] == "ready"
        assert ready["project_id"] == "wstest"


def test_ws_chat_streams_full_turn(patched_ws):
    """A full agent turn streams text → tool_start → tool_result → text → done."""
    client = TestClient(app_mod.app)
    with client.websocket_connect("/api/chat/wstest") as ws:
        # consume the ready event
        ready = json.loads(ws.receive_text())
        assert ready["type"] == "ready"

        ws.send_text(json.dumps({"message": "list my assets"}))

        events = []
        while True:
            ev = json.loads(ws.receive_text())
            events.append(ev)
            if ev.get("type") == "done":
                break

    types = [e["type"] for e in events]
    assert types == [
        "text",
        "tool_start",
        "tool_result",
        "text",
        "done",
    ]
    assert events[0]["text"] == "Checking your assets."
    assert events[1]["name"] == "list_assets"
    assert events[2]["name"] == "list_assets"
    assert events[3]["text"] == "You have 1 asset: intro.mp4."
    assert events[4]["stop_reason"] == "end_turn"


def test_ws_chat_unknown_project(patched_ws):
    """Connecting to an unknown project sends an error and closes."""
    client = TestClient(app_mod.app)
    with client.websocket_connect("/api/chat/does-not-exist") as ws:
        ev = json.loads(ws.receive_text())
        assert ev["type"] == "error"
        assert "not found" in ev["message"]


def test_ws_chat_invalid_json(patched_ws):
    """Invalid JSON on the WS yields an error event, doesn't crash."""
    client = TestClient(app_mod.app)
    with client.websocket_connect("/api/chat/wstest") as ws:
        _ = ws.receive_text()  # ready
        ws.send_text("not-json")
        ev = json.loads(ws.receive_text())
        assert ev["type"] == "error"
        assert "invalid JSON" in ev["message"]


def test_ws_chat_missing_message_field(patched_ws):
    """JSON without a 'message' field yields an error."""
    client = TestClient(app_mod.app)
    with client.websocket_connect("/api/chat/wstest") as ws:
        _ = ws.receive_text()  # ready
        ws.send_text(json.dumps({"foo": "bar"}))
        ev = json.loads(ws.receive_text())
        assert ev["type"] == "error"
        assert "missing 'message'" in ev["message"]


def test_ws_chat_conv_id_echoed(patched_ws):
    """If the client passes a conv_id, the server uses it (and persists)."""
    client = TestClient(app_mod.app)
    with client.websocket_connect("/api/chat/wstest") as ws:
        _ = ws.receive_text()  # ready
        ws.send_text(json.dumps({"message": "hello", "conv_id": "my-conv"}))
        # Drain until done.
        seen_done = False
        while True:
            ev = json.loads(ws.receive_text())
            if ev.get("type") == "done":
                seen_done = True
                break
        assert seen_done

    # The conversation file should now exist on disk (path comes from patched_ws).
    conv_file = patched_ws / ".open_edit" / "conversations" / "my-conv.jsonl"
    assert conv_file.exists()
    lines = conv_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 2  # at least the user msg + first assistant msg
    first = json.loads(lines[0])
    assert first["role"] == "user"
    assert first["content"] == "hello"
