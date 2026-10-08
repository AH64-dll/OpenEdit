"""Regression tests for the v1.9 agent-loop stability fixes.

Covers the root causes behind the "agent gets stuck in a loop" report:

1. Optional CLI chat does not execute editing tools; MCP owns external edits.
2. Circuit breaker: identical failing tool calls abort the turn after
   3 attempts instead of burning all MAX_AGENT_ITERATIONS.
3. Every tool_use in a batch gets a tool_result — skipped trigger_renders
   get a synthesized "skipped" result (no orphaned tool_use blocks).
4. ``_db_path`` resolves the canonical ``.open_edit/edit_graph.db``
   layout (with legacy fallback) — the split-brain DB bug.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from open_edit.agent.tools import _helpers
from open_edit.serve import agent as agent_mod
from open_edit.serve.llm import StreamEvent

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]


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
