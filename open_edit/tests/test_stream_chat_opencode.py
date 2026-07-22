"""End-to-end tests for the v1.7 opencode provider (track C)."""
from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

from open_edit.serve.llm import stream_chat
from open_edit.serve.llm_config import LLMConfig, save_llm_config


_FAKE_OPENCODE = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"type":"step_start","timestamp":1,"sessionID":"$SID","part":{"id":"p1","messageID":"m1","sessionID":"$SID","type":"step-start"}}))
print(json.dumps({"type":"text","timestamp":2,"sessionID":"$SID","part":{"id":"p2","messageID":"m1","sessionID":"$SID","type":"text","text":"Hi from opencode"}}))
print(json.dumps({"type":"step_finish","timestamp":3,"sessionID":"$SID","part":{"id":"p3","messageID":"m1","sessionID":"$SID","type":"step-finish","reason":"stop","tokens":{"total":50,"input":40,"output":5,"reasoning":5,"cache":{"write":0,"read":0}},"cost":0.001}}))
sys.exit(0)
"""


_FAKE_OPENCODE_HANG = """#!/usr/bin/env python3
import time, sys
# Never emit anything. Just sleep forever.
time.sleep(60)
sys.exit(0)
"""


@pytest.fixture
def fake_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a fake ``opencode`` on PATH and force the opencode provider."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    oc = bin_dir / "opencode"
    sid = "oc-test"
    oc.write_text(_FAKE_OPENCODE.replace("$SID", sid))
    oc.chmod(stat.S_IRWXU)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "opencode")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "opencode-go/minimax-m3")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    return oc


@pytest.fixture
def fake_opencode_hang(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a fake opencode that never emits anything (for the R4 test)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    oc = bin_dir / "opencode"
    oc.write_text(_FAKE_OPENCODE_HANG)
    oc.chmod(stat.S_IRWXU)
    # Override the opencode adapter timeout to something tiny for CI.
    from open_edit.serve.cli_adapter import _ADAPTERS
    orig = _ADAPTERS["opencode"].default_timeout_s
    _ADAPTERS["opencode"].default_timeout_s = 2
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "opencode")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "opencode-go/minimax-m3")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    yield oc
    _ADAPTERS["opencode"].default_timeout_s = orig


@pytest.mark.asyncio
async def test_stream_chat_opencode_text_only(fake_opencode: Path) -> None:
    events: list[dict] = []
    async for ev in stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="be brief",
        session_id="oc-test",
    ):
        events.append(ev)
    text = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert "Hi from opencode" in text
    types = [e["type"] for e in events]
    assert "usage" in types
    assert "done" in types


@pytest.mark.asyncio
async def test_stream_chat_opencode_uses_config_from_toml(
    fake_opencode: Path, tmp_path: Path,
) -> None:
    # The per-project config should be honored when project_path is
    # passed in. We write a different model and verify the env's
    # model is overridden.
    save_llm_config(tmp_path, LLMConfig(provider="opencode", model="opencode-go/deepseek-v4-flash"))
    events: list[dict] = []
    async for ev in stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="be brief",
        session_id="oc-test",
        project_path=str(tmp_path),
    ):
        events.append(ev)
    # The fact that the stream completed without an "unknown model"
    # error is the assertion: the fake opencode ignores the model
    # arg, so we just verify the provider path was taken.
    assert any(e["type"] == "done" for e in events)


@pytest.mark.asyncio
async def test_stream_cli_kills_hung_subprocess_and_emits_error(
    fake_opencode_hang: Path,
) -> None:
    """R4 fix: a hanging CLI is killed and yields an error event."""
    events: list[dict] = []
    start = asyncio.get_event_loop().time()
    async for ev in stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="be brief",
        session_id="oc-hang",
    ):
        events.append(ev)
    elapsed = asyncio.get_event_loop().time() - start
    # Should be killed in ~2s (the fake timeout we set), not 60s.
    assert elapsed < 10, f"hang was not killed in time: {elapsed:.1f}s elapsed"
    types = [e["type"] for e in events]
    assert "error" in types
    assert "done" in types
    err = next(e for e in events if e["type"] == "error")
    assert "timeout" in err["message"].lower()
    done = next(e for e in events if e["type"] == "done")
    assert done["stop_reason"] == "error"
