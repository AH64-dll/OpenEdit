"""Tests for the ``pi`` provider in ``open_edit.serve.llm``.

We don't actually spawn the real ``pi`` binary in unit tests (it would
require a real model and a real opencode-go API key). Instead, we
substitute a fake ``pi`` script that emits a canned JSON-line stream
on stdout. This exercises the same parsing / event-mapping code path
that production uses.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import AsyncIterator

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve.llm import (  # noqa: E402
    StreamEvent,
    _pi_binary,
    _pi_extension_path,
    _pi_normalize_event,
    stream_chat,
)


# ---------------------------------------------------------------------------
# Fake `pi` binary that emits a canned JSON event stream on stdout
# ---------------------------------------------------------------------------

FAKE_PI_SCRIPT = """\
#!/usr/bin/env python3
import json, sys

# Canned events: text, toolCall, toolResult, done.
EVENTS = [
    {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "Hello "}},
    {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "world"}},
    {"type": "message_end", "message": {
        "role": "assistant",
        "content": [
            {"type": "toolCall", "id": "call_abc", "name": "add_marker",
             "arguments": {"t_start": 1.0, "text": "hi"}},
        ],
    }},
    {"type": "message_end", "message": {
        "role": "toolResult", "toolCallId": "call_abc", "toolName": "add_marker",
        "content": [{"type": "text", "text": json.dumps({"status": "ok", "note_id": "n1"})}],
        "isError": False,
    }},
    {"type": "agent_end", "messages": []},
    {"type": "agent_settled"},
]

# Echo any extra args (for visibility / debugging).
import os
sys.stderr.write("fake-pi args: " + " ".join(repr(a) for a in sys.argv[1:]) + "\\n")

for ev in EVENTS:
    sys.stdout.write(json.dumps(ev) + "\\n")
    sys.stdout.flush()

# Read whatever stdin is there (we send DEVNULL so this is a no-op)
sys.exit(0)
"""


@pytest.fixture
def fake_pi(tmp_path, monkeypatch):
    """Drop a fake `pi` script in tmp_path and point OPEN_EDIT_PI_BINARY at it."""
    script = tmp_path / "fake-pi"
    script.write_text(FAKE_PI_SCRIPT)
    script.chmod(0o755)
    monkeypatch.setenv("OPEN_EDIT_PI_BINARY", str(script))
    # Force the pi provider regardless of OPEN_EDIT_LLM_PROVIDER.
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "pi")
    # Use a tiny model name (the fake pi ignores it).
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "fake-model")
    # Make sure PYTHONPATH includes the open_edit package for the bridge
    # invocation (the fake pi doesn't run it, but the real one does).
    pkg_root = str(_REPO_ROOT)
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", pkg_root + (os.pathsep + existing if existing else ""))
    return script


# ---------------------------------------------------------------------------
# Event-mapping tests (no subprocess at all)
# ---------------------------------------------------------------------------

def test_normalize_text_delta():
    """message_update with text_delta → text_delta event with the delta text."""
    obj = {
        "type": "message_update",
        "assistantMessageEvent": {"type": "text_delta", "delta": "hi"},
    }
    evs = _pi_normalize_event(obj)
    assert evs == [{"type": "text_delta", "text": "hi"}]


def test_normalize_tool_call_assistant_message():
    """message_end with assistant role + toolCall → tool_use event with parsed args."""
    obj = {
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "toolCall", "id": "call_x", "name": "add_marker",
                 "arguments": {"t_start": 1.0, "text": "x"}},
            ],
        },
    }
    evs = _pi_normalize_event(obj)
    assert len(evs) == 1
    assert evs[0]["type"] == "tool_use"
    assert evs[0]["name"] == "add_marker"
    assert evs[0]["input"] == {"t_start": 1.0, "text": "x"}


def test_normalize_tool_call_with_string_args():
    """toolCall.arguments may be a JSON string; we parse defensively."""
    obj = {
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "toolCall", "id": "call_x", "name": "add_marker",
                 "arguments": json.dumps({"t_start": 2.0, "text": "y"})},
            ],
        },
    }
    evs = _pi_normalize_event(obj)
    assert evs[0]["input"] == {"t_start": 2.0, "text": "y"}


def test_normalize_tool_result_success():
    """message_end with toolResult role + success → tool_result event with parsed JSON."""
    obj = {
        "type": "message_end",
        "message": {
            "role": "toolResult",
            "toolCallId": "call_x",
            "toolName": "add_marker",
            "content": [{"type": "text", "text": json.dumps({"status": "ok"})}],
            "isError": False,
        },
    }
    evs = _pi_normalize_event(obj)
    assert len(evs) == 1
    assert evs[0]["type"] == "tool_result"
    assert evs[0]["name"] == "add_marker"
    assert evs[0]["result"] == {"status": "ok"}


def test_normalize_tool_result_error():
    """message_end with isError=True → tool_result event with is_error flag and message."""
    obj = {
        "type": "message_end",
        "message": {
            "role": "toolResult",
            "toolCallId": "call_x",
            "toolName": "bad",
            "content": [{"type": "text", "text": json.dumps({"error": "boom"})}],
            "isError": True,
        },
    }
    evs = _pi_normalize_event(obj)
    assert evs[0]["type"] == "tool_result"
    assert evs[0]["is_error"] is True
    assert evs[0]["error_message"] == "boom"


def test_normalize_error_event():
    evs = _pi_normalize_event({"type": "error", "error": "something broke"})
    assert evs == [{"type": "error", "message": "something broke"}]


def test_normalize_unknown_event_returns_empty():
    evs = _pi_normalize_event({"type": "agent_settled"})
    assert evs == []


# ---------------------------------------------------------------------------
# End-to-end test using the fake `pi` script
# ---------------------------------------------------------------------------

async def _collect(stream: AsyncIterator[StreamEvent]) -> list[StreamEvent]:
    out = []
    async for ev in stream:
        out.append(ev)
    return out


def test_stream_chat_uses_fake_pi(monkeypatch, fake_pi):
    """stream_chat with the pi provider spawns fake-pi, parses its JSON, yields events."""
    messages = [{"role": "user", "content": "hi"}]

    # We need to also ensure the extension path exists (or pi will fail).
    # fake-pi ignores it, but the code still checks for it.
    ext_path = _pi_extension_path()
    if not Path(ext_path).is_file():
        # Write a stub .ts so the exists check passes.
        Path(ext_path).parent.mkdir(parents=True, exist_ok=True)
        Path(ext_path).write_text("// stub for test\n")

    events = asyncio.run(_collect(stream_chat(
        messages=messages,
        tools=[],
        system="",
        session_id="sess-1",
        project_path="/tmp",
    )))

    types = [e["type"] for e in events]
    assert types == [
        "text_delta", "text_delta",  # "Hello " + "world"
        "tool_use",                    # add_marker call
        "tool_result",                 # tool result from pi
        "usage",                       # cost data (v1.4 P1-3)
        "done",                        # final
    ]

    # Verify the text was assembled correctly
    text_deltas = [e["text"] for e in events if e["type"] == "text_delta"]
    assert "".join(text_deltas) == "Hello world"

    # Verify the tool_use
    tool_use = next(e for e in events if e["type"] == "tool_use")
    assert tool_use["name"] == "add_marker"
    assert tool_use["input"] == {"t_start": 1.0, "text": "hi"}

    # Verify the tool_result
    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert tool_result["name"] == "add_marker"
    assert tool_result["result"] == {"status": "ok", "note_id": "n1"}


def test_stream_chat_pi_provider_routes_correctly(monkeypatch, fake_pi):
    """The provider dispatch picks `pi` when OPEN_EDIT_LLM_PROVIDER=pi."""
    # Fake pi emits 2 text_deltas + 1 tool_use + 1 tool_result + done.
    ext_path = _pi_extension_path()
    if not Path(ext_path).is_file():
        Path(ext_path).parent.mkdir(parents=True, exist_ok=True)
        Path(ext_path).write_text("// stub for test\n")

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "x"}],
        tools=[],
        system="",
        session_id="s",
        project_path="/tmp",
    )))
    # If we routed to the right provider, we got pi's events; if we
    # routed to anthropic/openai, we'd get a "no API key" error or empty.
    assert any(e["type"] == "text_delta" for e in events)
    assert any(e["type"] == "tool_result" for e in events)


def test_pi_binary_resolved_from_env(monkeypatch, tmp_path):
    """OPEN_EDIT_PI_BINARY overrides auto-detection."""
    fake = tmp_path / "my-pi"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("OPEN_EDIT_PI_BINARY", str(fake))
    assert _pi_binary() == str(fake)
