"""Regression tests for the _stream_pi → _stream_cli refactor (Phase 1).

These tests pin down the contract that the refactor must preserve: a
fake ``pi`` binary on PATH emits the same JSON-line stream as before,
and the same StreamEvent shape is yielded. After the refactor, the
``pi`` provider path is just ``_stream_cli(PiAdapter(), ...)``.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from open_edit.serve.cli_adapter import get_adapter
from open_edit.serve.llm import stream_chat

_FAKE_PI = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

# Handle --session <path> flag: write fake usage data to the session file
session_path_arg = ""
for i, a in enumerate(sys.argv):
    if a == "--session" and i + 1 < len(sys.argv):
        session_path_arg = sys.argv[i + 1]
        break
    if a == "--session-id" and i + 1 < len(sys.argv):
        session_id = sys.argv[i + 1]
        sessions_dir = os.environ.get("OPEN_EDIT_PI_SESSIONS_DIR", "")
        if sessions_dir:
            cwd = os.getcwd()
            encoded = "-" + cwd.replace("/", "-") + "-"
            sess_dir = Path(sessions_dir) / encoded
            suffix = "_" + session_id + ".jsonl"
            if sess_dir.exists():
                for entry in sess_dir.iterdir():
                    if entry.is_file() and entry.name.endswith(suffix):
                        session_path_arg = str(entry)
                        break

if session_path_arg:
    target = Path(session_path_arg)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "type": "message",
            "id": "m-fake-1",
            "timestamp": "2026-07-21T00:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello back"}],
                "model": "minimax-m3",
                "usage": {
                    "input": 10, "output": 5,
                    "cacheRead": 0, "cacheWrite": 0,
                    "totalTokens": 15,
                    "cost": {
                        "input": 0.001, "output": 0.002,
                        "cacheRead": 0, "cacheWrite": 0,
                        "total": 0.003,
                    },
                },
            },
        }) + "\\n")

print(json.dumps({"type":"session","version":3,"id":"$SID","timestamp":"2026-01-01T00:00:00.000Z","cwd":"/tmp"}))
print(json.dumps({"type":"agent_start"}))
print(json.dumps({"type":"turn_start"}))
print(json.dumps({"type":"message_start","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}))
print(json.dumps({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"Hello back"}}))
print(json.dumps({"type":"message_start","message":{"role":"assistant","content":[],"api":"anthropic-messages","provider":"opencode-go","model":"x","usage":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"totalTokens":0,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}},"stopReason":"stop","timestamp":1}}))
print(json.dumps({"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"Hello back"}],"api":"anthropic-messages","provider":"opencode-go","model":"x","usage":{"input":10,"output":5,"cacheRead":0,"cacheWrite":0,"totalTokens":15,"cost":{"input":0.001,"output":0.002,"cacheRead":0,"cacheWrite":0,"total":0.003}},"stopReason":"stop","timestamp":2}}))
print(json.dumps({"type":"turn_end","message":{"role":"assistant","content":[{"type":"text","text":"Hello back"}],"stopReason":"stop","timestamp":2},"toolResults":[]}))
print(json.dumps({"type":"agent_end","messages":[],"willRetry":False}))
print(json.dumps({"type":"agent_settled"}))
sys.exit(0)
"""


@pytest.fixture
def fake_pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a fake ``pi`` on PATH and force the pi provider."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pi = bin_dir / "pi"
    sid = "oe-test"
    pi.write_text(_FAKE_PI.replace("$SID", sid))
    pi.chmod(stat.S_IRWXU)
    # Force pi provider and point PATH at our shim.
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "pi")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    return pi


@pytest.mark.asyncio
async def test_pi_provider_still_works_after_refactor(fake_pi: Path) -> None:
    events: list[dict] = []
    async for ev in stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="be helpful",
        session_id="oe-test",
    ):
        events.append(ev)
    types = [e["type"] for e in events]
    assert "text_delta" in types
    assert "done" in types
    # The assistant text was streamed as a delta.
    text = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert "Hello back" in text
    # Done has a stop_reason.
    done = next(e for e in events if e["type"] == "done")
    assert done["stop_reason"] in ("end_turn", "stop")


@pytest.mark.asyncio
async def test_pi_adapter_lookup_works(fake_pi: Path) -> None:
    """The pi adapter from cli_adapter.py has the same name + timeout."""
    a = get_adapter("pi")
    assert a.name == "pi"
    assert a.default_timeout_s == 3600
    cmd = a.build_command(
        model="minimax-m3",
        user_text="hi",
        session_id="sess-1",
        extension_path=None,
        system_prompt="be brief",
    )
    assert Path(cmd[0]).name == "pi"
    assert "--mode" in cmd
    assert "json" in cmd
    assert "--session-id" in cmd
    assert "sess-1" in cmd
    assert "minimax-m3" in cmd


# ---------------------------------------------------------------------------
# Per-project LLM config (v1.7 finding A1)
#
# Bug: ``stream_chat`` read the provider + model from env vars only, so
# the chat UI's provider-selection bar was non-functional — clicking
# "OpenCode" or "Antigravity" wrote the new value to
# ``<project>/.open_edit/config.toml`` but the next chat turn still
# used the env-var provider. This test pins down the fix: when a
# per-project config exists and the env-var provider is ``anthropic``
# (with no API key set), ``stream_chat`` must honor the per-project
# config (opencode) and complete the stream.
# ---------------------------------------------------------------------------

_FAKE_OPENCODE_FOR_CFG = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"type":"step_start","timestamp":1,"sessionID":"$SID","part":{"id":"p1","messageID":"m1","sessionID":"$SID","type":"step-start"}}))
print(json.dumps({"type":"text","timestamp":2,"sessionID":"$SID","part":{"id":"p2","messageID":"m1","sessionID":"$SID","type":"text","text":"hello from opencode"}}))
print(json.dumps({"type":"step_finish","timestamp":3,"sessionID":"$SID","part":{"id":"p3","messageID":"m1","sessionID":"$SID","type":"step-finish","reason":"stop","tokens":{"total":10,"input":8,"output":2,"reasoning":0,"cache":{"write":0,"read":0}},"cost":0.0001}}))
sys.exit(0)
"""


@pytest.mark.asyncio
async def test_stream_chat_honors_per_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-project .open_edit/config.toml must override env vars."""
    # Force the env to anthropic with NO API key; the only way
    # stream_chat can succeed is by reading the per-project config
    # and routing to opencode instead.
    monkeypatch.delenv("OPEN_EDIT_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "claude-sonnet-4-5")

    # Write a per-project config that points to opencode.
    cfg_dir = tmp_path / ".open_edit"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        '[llm]\nprovider = "opencode"\nmodel = "opencode-go/minimax-m3"\n'
    )

    # Install a fake opencode on PATH.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    oc = bin_dir / "opencode"
    oc.write_text(_FAKE_OPENCODE_FOR_CFG.replace("$SID", "cfg-test"))
    oc.chmod(stat.S_IRWXU)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    events: list[dict] = []
    async for ev in stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="be brief",
        session_id="cfg-test",
        project_path=str(tmp_path),
    ):
        events.append(ev)

    # If the per-project config was honored, we routed to opencode and
    # the fake opencode emitted its text. If the bug were back, we'd
    # have routed to anthropic with no API key → "no API key" error.
    types = [e["type"] for e in events]
    assert "text_delta" in types, f"no text_delta in {types} — per-project config was not honored"
    assert "done" in types
    text = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert "hello from opencode" in text
    # The error event would be present if we had routed to anthropic.
    errors = [e for e in events if e["type"] == "error"]
    assert not errors, f"unexpected error events: {errors}"


@pytest.mark.asyncio
async def test_stream_chat_falls_back_to_env_when_no_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No per-project config → stream_chat uses env vars (backward compat)."""
    # No .open_edit/config.toml under tmp_path → fall back to env.
    monkeypatch.delenv("OPEN_EDIT_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "pi")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pi = bin_dir / "pi"
    pi.write_text(_FAKE_PI.replace("$SID", "fb-test"))
    pi.chmod(stat.S_IRWXU)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    events: list[dict] = []
    async for ev in stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="be brief",
        session_id="fb-test",
        project_path=str(tmp_path),  # no .open_edit/config.toml here
    ):
        events.append(ev)
    types = [e["type"] for e in events]
    assert "text_delta" in types
    assert "done" in types
    text = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert "Hello back" in text


# ---------------------------------------------------------------------------
# A4 regression: pi text duplication (v1.7 finding)
#
# Bug: the T5 refactor changed ``_pi_normalize_event`` to emit a
# ``text_delta`` for the ``text`` block inside ``message_end`` content.
# If pi emits BOTH ``message_update`` text deltas AND a ``message_end``
# with non-empty text content, the UI showed the text twice. Fix: the
# text block in ``message_end`` must be ignored (we already streamed
# the deltas).
# ---------------------------------------------------------------------------

_FAKE_PI_DUP_TEXT = """#!/usr/bin/env python3
import json, sys
# pi streams the text twice in real life: once via message_update
# deltas, then again as a single text block in the final message_end.
print(json.dumps({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"hello "}}))
print(json.dumps({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"world"}}))
print(json.dumps({"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"hello world"}]}}))
print(json.dumps({"type":"agent_end","messages":[]}))
print(json.dumps({"type":"agent_settled"}))
sys.exit(0)
"""


@pytest.mark.asyncio
async def test_pi_message_end_text_does_not_duplicate_deltas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The text block in message_end must NOT be re-emitted as a text_delta."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pi = bin_dir / "pi"
    pi.write_text(_FAKE_PI_DUP_TEXT)
    pi.chmod(stat.S_IRWXU)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "pi")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    events: list[dict] = []
    async for ev in stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="be brief",
        session_id="dup-test",
    ):
        events.append(ev)

    # Count text_delta events. We expect exactly 2 (one per message_update).
    # If the bug were back, we'd see 3 (the message_end's "hello world"
    # would also be emitted as a single text_delta, duplicating the deltas).
    text_deltas = [e for e in events if e["type"] == "text_delta"]
    assert len(text_deltas) == 2, f"expected 2 text_deltas, got {len(text_deltas)}: {text_deltas}"
    assembled = "".join(e["text"] for e in text_deltas)
    assert assembled == "hello world"
    # The text must appear exactly once in the assembled stream (no duplication).
    assert assembled.count("hello world") == 1
