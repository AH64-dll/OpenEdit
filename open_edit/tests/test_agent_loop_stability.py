"""Regression tests for the v1.9 agent-loop stability fixes.

Covers the root causes behind the "agent gets stuck in a loop" report:

1. CLI providers (pi/opencode/...) own their agent loop — the Open Edit
   loop must stream exactly once, must NOT re-execute tools locally
   (double execution), and must NOT re-iterate.
2. Circuit breaker: identical failing tool calls abort the turn after
   3 attempts instead of burning all MAX_AGENT_ITERATIONS.
3. Every tool_use in a batch gets a tool_result — skipped trigger_renders
   get a synthesized "skipped" result (no orphaned tool_use blocks).
4. ``_db_path`` resolves the canonical ``.open_edit/edit_graph.db``
   layout (with legacy fallback) — the split-brain DB bug.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import agent as agent_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402
from open_edit.serve.llm import StreamEvent  # noqa: E402
from open_edit.agent.tools import _helpers  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class _FakeState:
    def model_dump(self):
        return {"project_id": "pid", "name": "fake", "timeline": {"tracks": []}}


def _patch_common(monkeypatch, tmp_path):
    async def _fake_state(pid):
        return _FakeState()

    monkeypatch.setattr(agent_mod.projects_mod, "get_project_state", _fake_state)
    monkeypatch.setattr(agent_mod, "_resolve_project_path", lambda pid: tmp_path)
    monkeypatch.setattr(agent_mod, "append_to_conversation", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# 1. CLI-owned turns: single stream, no local execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cli_owned_turn_does_not_reexecute_tools(monkeypatch, tmp_path):
    """pi-style stream (tool_use + tool_result from provider) → the local
    executor is NEVER called; the provider's result is the one surfaced."""
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_mod, "effective_provider", lambda p: "pi")

    async def pi_stream(*args, **kwargs) -> AsyncIterator[StreamEvent]:
        yield {"type": "text_delta", "text": "Adding a marker."}
        yield {"type": "tool_use", "id": "c1", "name": "add_marker",
               "input": {"t_start": 1.5, "text": "x"}}
        yield {"type": "tool_result", "name": "add_marker",
               "result": {"status": "ok", "note_id": "note_FROM_PI"},
               "tool_use_id": "c1"}
        yield {"type": "done", "stop_reason": "end_turn"}

    monkeypatch.setattr(agent_mod, "stream_chat", pi_stream)

    local_calls: list[str] = []
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: local_calls.append(name) or {},
    )

    history: list[dict[str, Any]] = []
    events = [ev async for ev in agent_mod.run_agent_turn("pid", "add a marker", history)]

    assert local_calls == [], f"local executor must not run for CLI-owned turns: {local_calls}"
    results = [e for e in events if e["type"] == "tool_result"]
    assert len(results) == 1
    assert results[0]["result"]["note_id"] == "note_FROM_PI"
    assert results[0]["id"] == "c1"
    # One done, clean stop, single iteration (exactly one assistant message).
    dones = [e for e in events if e["type"] == "done"]
    assert len(dones) == 1
    assert dones[0]["stop_reason"] == "end_turn"
    assistant_msgs = [m for m in history if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1


@pytest.mark.asyncio
async def test_cli_owned_turn_history_pairs_every_tool_use(monkeypatch, tmp_path):
    """Every tool_use in history must be followed by a tool_result with a
    matching tool_use_id (Anthropic contract), even if the provider did
    not forward a result for it."""
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_mod, "effective_provider", lambda p: "pi")

    async def pi_stream(*args, **kwargs) -> AsyncIterator[StreamEvent]:
        yield {"type": "tool_use", "id": "a", "name": "list_assets", "input": {}}
        yield {"type": "tool_use", "id": "b", "name": "get_pending_notes", "input": {}}
        # Only ONE result forwarded — "b" is unmatched.
        yield {"type": "tool_result", "name": "list_assets",
               "result": {"assets": []}, "tool_use_id": "a"}
        yield {"type": "done", "stop_reason": "end_turn"}

    monkeypatch.setattr(agent_mod, "stream_chat", pi_stream)
    monkeypatch.setattr(agent_mod, "_execute_tool", lambda *a, **k: {})

    history: list[dict[str, Any]] = []
    async for _ev in agent_mod.run_agent_turn("pid", "check stuff", history):
        pass

    tool_uses = [
        b for m in history if m.get("role") == "assistant"
        for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_use"
    ]
    tool_results = [
        b for m in history if m.get("role") == "user"
        for b in (m["content"] if isinstance(m["content"], list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    assert {b["id"] for b in tool_uses} == {b["tool_use_id"] for b in tool_results}


@pytest.mark.asyncio
async def test_cli_owned_turn_no_second_stream_call(monkeypatch, tmp_path):
    """The loop must NOT re-call stream_chat after tools complete (the old
    bug: second pi subprocess died with 'no user message found')."""
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_mod, "effective_provider", lambda p: "pi")

    stream_calls = {"n": 0}

    async def pi_stream(*args, **kwargs) -> AsyncIterator[StreamEvent]:
        stream_calls["n"] += 1
        yield {"type": "tool_use", "id": "c1", "name": "list_assets", "input": {}}
        yield {"type": "tool_result", "name": "list_assets",
               "result": {"assets": []}, "tool_use_id": "c1"}
        yield {"type": "done", "stop_reason": "end_turn"}

    monkeypatch.setattr(agent_mod, "stream_chat", pi_stream)
    monkeypatch.setattr(agent_mod, "_execute_tool", lambda *a, **k: {})

    async for _ev in agent_mod.run_agent_turn("pid", "list", []):
        pass
    assert stream_calls["n"] == 1


# ---------------------------------------------------------------------------
# 2. Circuit breaker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_aborts_identical_failures(monkeypatch, tmp_path):
    """The LLM retries the same failing call with identical args; after 3
    attempts the turn aborts with stop_reason=tool_loop_detected instead
    of consuming all iterations."""
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_mod, "effective_provider", lambda p: "anthropic")

    async def loop_stream(*args, **kwargs) -> AsyncIterator[StreamEvent]:
        # Every LLM response is the same failing tool call.
        yield {"type": "tool_use", "id": "x1", "name": "run_python",
               "input": {"code": "boom()"}}
        yield {"type": "done", "stop_reason": "tool_use"}

    monkeypatch.setattr(agent_mod, "stream_chat", loop_stream)

    def failing_execute(name, args, path, command_id=None):
        raise RuntimeError("sandbox exploded")

    monkeypatch.setattr(agent_mod, "_execute_tool", failing_execute)

    events = [ev async for ev in agent_mod.run_agent_turn("pid", "do it", [])]
    dones = [e for e in events if e["type"] == "done"]
    assert dones[-1]["stop_reason"] == "tool_loop_detected"
    # 3 attempts max (well under MAX_AGENT_ITERATIONS).
    starts = [e for e in events if e["type"] == "tool_start"]
    assert len(starts) == 3


@pytest.mark.asyncio
async def test_tool_level_error_payloads_count_toward_breaker(monkeypatch, tmp_path):
    """A tool returning {"status": "error", ...} (no exception) still
    counts as a failure for the circuit breaker."""
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_mod, "effective_provider", lambda p: "anthropic")

    async def loop_stream(*args, **kwargs) -> AsyncIterator[StreamEvent]:
        yield {"type": "tool_use", "id": "x1", "name": "run_python",
               "input": {"code": "boom()"}}
        yield {"type": "done", "stop_reason": "tool_use"}

    monkeypatch.setattr(agent_mod, "stream_chat", loop_stream)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: {"status": "error", "error": "preflight_failed"},
    )

    events = [ev async for ev in agent_mod.run_agent_turn("pid", "do it", [])]
    starts = [e for e in events if e["type"] == "tool_start"]
    # After the 3rd error payload, the NEXT identical call aborts; the
    # stream always issues the same call so we get at most 4 starts.
    assert len(starts) <= 4
    dones = [e for e in events if e["type"] == "done"]
    assert dones[-1]["stop_reason"] == "tool_loop_detected"


# ---------------------------------------------------------------------------
# 3. Orphaned tool_use blocks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skipped_trigger_renders_get_tool_results(monkeypatch, tmp_path):
    """Two trigger_renders in one batch: only the last executes, but the
    first still gets a synthesized 'skipped' tool_result in history."""
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_mod, "effective_provider", lambda p: "anthropic")

    turns = {"n": 0}

    async def two_render_stream(*args, **kwargs) -> AsyncIterator[StreamEvent]:
        turns["n"] += 1
        if turns["n"] == 1:
            yield {"type": "tool_use", "id": "r1", "name": "trigger_render", "input": {}}
            yield {"type": "tool_use", "id": "r2", "name": "trigger_render", "input": {}}
            yield {"type": "done", "stop_reason": "tool_use"}
        else:
            yield {"type": "text_delta", "text": "done"}
            yield {"type": "done", "stop_reason": "end_turn"}

    monkeypatch.setattr(agent_mod, "stream_chat", two_render_stream)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: {"output_path": "", "mode": "proxy", "render_id": "x"},
    )
    # Disable verification to keep the test focused on history shape.
    monkeypatch.setattr(agent_mod, "is_verify_disabled", lambda p: True)

    history: list[dict[str, Any]] = []
    async for _ev in agent_mod.run_agent_turn("pid", "render", history):
        pass

    tool_results = [
        b for m in history if m.get("role") == "user"
        for b in (m["content"] if isinstance(m["content"], list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    result_ids = {b["tool_use_id"] for b in tool_results}
    assert {"r1", "r2"} <= result_ids
    skipped = [b for b in tool_results if b["tool_use_id"] == "r1"]
    assert json.loads(skipped[0]["content"])["status"] == "skipped"


# ---------------------------------------------------------------------------
# 4. _db_path canonical layout
# ---------------------------------------------------------------------------

def test_db_path_prefers_canonical_open_edit_layout(tmp_path):
    canonical = tmp_path / ".open_edit" / "edit_graph.db"
    canonical.parent.mkdir(parents=True)
    canonical.touch()
    # A legacy root-level db also exists (phantom); canonical must win.
    (tmp_path / "edit_graph.db").touch()
    assert _helpers._db_path(tmp_path) == canonical


def test_db_path_legacy_fallback(tmp_path):
    legacy = tmp_path / "edit_graph.db"
    legacy.touch()
    assert _helpers._db_path(tmp_path) == legacy


def test_db_path_defaults_to_canonical_for_creation(tmp_path):
    # Nothing on disk; .open_edit dir exists → canonical path chosen so
    # make_ir() creates the db where the server looks for it.
    (tmp_path / ".open_edit").mkdir()
    assert _helpers._db_path(tmp_path) == tmp_path / ".open_edit" / "edit_graph.db"


def test_notes_db_path_is_project_root(tmp_path):
    (tmp_path / ".open_edit").mkdir()
    assert _helpers._notes_db_path(tmp_path) == tmp_path / "notes.db"
