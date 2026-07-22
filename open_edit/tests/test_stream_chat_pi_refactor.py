"""Regression tests for the _stream_pi → _stream_cli refactor (Phase 1).

These tests pin down the contract that the refactor must preserve: a
fake ``pi`` binary on PATH emits the same JSON-line stream as before,
and the same StreamEvent shape is yielded. After the refactor, the
``pi`` provider path is just ``_stream_cli(PiAdapter(), ...)``.
"""
from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from open_edit.serve.llm import stream_chat
from open_edit.serve.cli_adapter import get_adapter


_FAKE_PI = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"type":"session","version":3,"id":"$SID","timestamp":"2026-01-01T00:00:00.000Z","cwd":"/tmp"}))
print(json.dumps({"type":"agent_start"}))
print(json.dumps({"type":"turn_start"}))
print(json.dumps({"type":"message_start","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}))
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
    assert a.default_timeout_s == 60
    cmd = a.build_command(
        model="minimax-m3",
        user_text="hi",
        session_id="sess-1",
        extension_path=None,
        system_prompt="be brief",
    )
    assert cmd[0] == "pi"
    assert "--mode" in cmd
    assert "json" in cmd
    assert "--session-id" in cmd
    assert "sess-1" in cmd
    assert "minimax-m3" in cmd
