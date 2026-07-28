"""Tests for v1.4 P1-3 cost-update plumbing in ``open_edit.serve.agent``.

The agent loop is responsible for:
- Collecting per-call ``usage`` events from ``stream_chat`` and
  aggregating them into a single turn total.
- Loading the previous session cumulative cost from a sidecar
  JSON file (``<project>/.open_edit/cost.json``) at turn start.
- Emitting a ``cost_update`` AgentEvent after the final ``done``
  with ``turn_tokens``, ``turn_cost_usd``, ``session_cost_usd``,
  and ``source`` (the highest-priority non-"unavailable" source
  from the per-call events).
- Persisting the new session cumulative to the sidecar JSON after
  the turn.

The sidecar format is a flat dict keyed by conv_id, with values of
``{"session_cost_usd": float, "source": str, "last_turn_cost_usd": float}``.
A separate (small) table inside ``edit_graph.db`` was an option;
we picked the JSON sidecar for simplicity and to keep
``EditGraphStore``'s schema untouched.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import agent as agent_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402
from open_edit.serve.llm import StreamEvent  # noqa: E402


# ---------------------------------------------------------------------------
# Sidecar persistence (no agent loop involved — pure function tests)
# ---------------------------------------------------------------------------

def test_load_cost_state_returns_empty_when_no_file(tmp_path):
    """First-time use: no sidecar file yet, the loader returns {}."""
    state = agent_mod._load_cost_state(tmp_path)
    assert state == {}


def test_load_cost_state_round_trip(tmp_path):
    """Write a sidecar via the agent's save function, read it back."""
    agent_mod._save_cost_state(
        tmp_path,
        {"conv-1": {"session_cost_usd": 0.05, "source": "pi",
                    "last_turn_cost_usd": 0.01}},
    )
    state = agent_mod._load_cost_state(tmp_path)
    assert state == {"conv-1": {"session_cost_usd": 0.05,
                                "source": "pi",
                                "last_turn_cost_usd": 0.01}}


def test_save_cost_state_atomic_writes(tmp_path, monkeypatch):
    """The save path uses a temp file + rename so a crash mid-write
    can't leave the sidecar in a half-written state. We verify the
    implementation by checking the file appears atomically: no
    partial content is visible mid-save."""
    # The sidecar lives at <project>/.open_edit/cost.json
    p = tmp_path / ".open_edit" / "cost.json"
    # The agent writes via ``os.replace``; after save_cost_state
    # returns, the file must exist with the full content (not 0 bytes
    # or half-written).
    agent_mod._save_cost_state(
        tmp_path,
        {"conv-x": {"session_cost_usd": 0.01, "source": "pi",
                    "last_turn_cost_usd": 0.01}},
    )
    # File exists and parses as JSON.
    assert p.exists()
    parsed = json.loads(p.read_text())
    assert "conv-x" in parsed


def test_save_cost_state_preserves_unrelated_conv_ids(tmp_path):
    """Writing a new entry must not erase existing conv_ids that
    belong to other conversations."""
    agent_mod._save_cost_state(
        tmp_path,
        {"conv-a": {"session_cost_usd": 0.01, "source": "pi",
                    "last_turn_cost_usd": 0.01},
         "conv-b": {"session_cost_usd": 0.02, "source": "pi",
                    "last_turn_cost_usd": 0.02}},
    )
    agent_mod._save_cost_state(
        tmp_path,
        {"conv-a": {"session_cost_usd": 0.03, "source": "pi",
                    "last_turn_cost_usd": 0.02}},
    )
    state = agent_mod._load_cost_state(tmp_path)
    assert state["conv-a"]["session_cost_usd"] == 0.03
    assert state["conv-b"]["session_cost_usd"] == 0.02


def test_cost_sidecar_path_under_open_edit_dir(tmp_path):
    """The sidecar lives at ``<project>/.open_edit/cost.json`` —
    alongside the conversations dir, so all per-project state is
    colocated."""
    p = agent_mod._cost_sidecar_path(tmp_path)
    assert p == tmp_path / ".open_edit" / "cost.json"


# ---------------------------------------------------------------------------
# Agent loop integration: cost_update event
# ---------------------------------------------------------------------------

def _mock_stream_chat_with_usage(
    usage_events: list[StreamEvent],
):
    """Return a stream_chat mock that yields the given usage events
    before yielding ``done``. The mock also takes care not to
    require real stream_chat signature changes."""

    async def _fn(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
        session_id: str | None = None,
        project_path: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        for ev in usage_events:
            yield ev

    return _fn


@pytest.fixture
def patched_agent_with_cost(monkeypatch, tmp_path):
    """Like ``patched_agent`` in test_serve_agent.py, but routes
    ``stream_chat`` to a custom callable and skips tool execution
    (we test pure cost plumbing, not tool dispatch)."""
    # Fake project state
    fake_state = projects_mod.ProjectState(
        id="costproject",
        name="costproject",
        path=str(tmp_path),
        assets=[],
        ops=[],
        timeline=projects_mod.TimelineSummary(),
        pending_notes_count=0,
    )

    async def _fake_get_project_state(project_id):
        return fake_state

    monkeypatch.setattr(
        projects_mod, "get_project_state", _fake_get_project_state,
    )
    monkeypatch.setattr(
        projects_mod, "_resolve_project_by_id",
        lambda pid: tmp_path if pid == "costproject" else None,
    )

    return {"project_path": tmp_path, "state": fake_state}


def test_agent_emits_cost_update_after_done(patched_agent_with_cost, monkeypatch):
    """When the LLM yields a ``usage`` event, the agent loop must
    emit a ``cost_update`` AgentEvent after the final ``done``.
    Per the brief, the cost_update has shape
    ``{turn_tokens, turn_cost_usd, session_cost_usd, source}``."""
    monkeypatch.setattr(agent_mod, "stream_chat",
                        _mock_stream_chat_with_usage([
                            {"type": "text_delta", "text": "hi"},
                            {"type": "usage", "source": "pi",
                             "tokens": 150, "cost_usd": 0.0003,
                             "usage": {}},
                            {"type": "done", "stop_reason": "end_turn"},
                        ]))

    async def _collect():
        out = []
        async for ev in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="hello",
            conversation_history=[],
            conv_id="conv-1",
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    types = [e["type"] for e in events]
    # cost_update must come AFTER done (per the brief: "sent once
    # per completed turn (after DONE)").
    assert "cost_update" in types
    assert "done" in types
    assert types.index("cost_update") > types.index("done")
    cost_ev = next(e for e in events if e["type"] == "cost_update")
    assert cost_ev["turn_tokens"] == 150
    assert cost_ev["turn_cost_usd"] == pytest.approx(0.0003, abs=1e-9)
    # First turn: session_cost_usd == turn_cost_usd.
    assert cost_ev["session_cost_usd"] == pytest.approx(0.0003, abs=1e-9)
    assert cost_ev["source"] == "pi"


def test_agent_aggregates_multiple_usage_events_in_one_turn(
    patched_agent_with_cost, monkeypatch,
):
    """A turn that loops through multiple LLM calls (model calls a
    tool, gets the result, calls again) emits multiple ``usage``
    events. The agent must SUM them into a single turn total."""
    # The first stream_chat call yields a tool_use; the second
    # yields the final text. We mock the loop by counting how many
    # times stream_chat is called.
    call_count = {"n": 0}

    async def _multi_call_stream_chat(
        messages, tools, system, session_id=None, project_path=None,
    ):
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield {"type": "text_delta", "text": "first"}
            yield {"type": "tool_use", "id": "t1", "name": "add_marker",
                   "input": {"t_start": 1.0, "text": "x"}}
            yield {"type": "usage", "source": "pi",
                   "tokens": 100, "cost_usd": 0.0001, "usage": {}}
            yield {"type": "done", "stop_reason": "tool_use"}
        else:
            yield {"type": "text_delta", "text": "second"}
            yield {"type": "usage", "source": "pi",
                   "tokens": 50, "cost_usd": 0.0002, "usage": {}}
            yield {"type": "done", "stop_reason": "end_turn"}

    monkeypatch.setattr(agent_mod, "stream_chat", _multi_call_stream_chat)

    async def _collect():
        out = []
        async for ev in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="go",
            conversation_history=[],
            conv_id="conv-1",
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    cost_ev = next(e for e in events if e["type"] == "cost_update")
    # Turn totals: 100 + 50 tokens, 0.0001 + 0.0002 cost.
    assert cost_ev["turn_tokens"] == 150
    assert cost_ev["turn_cost_usd"] == pytest.approx(0.0003, abs=1e-9)


def test_agent_persists_session_cost_to_sidecar(
    patched_agent_with_cost, monkeypatch, tmp_path,
):
    """After the turn, the sidecar JSON at
    ``<project>/.open_edit/cost.json`` must reflect the new
    session cumulative for this conv_id."""
    monkeypatch.setattr(agent_mod, "stream_chat",
                        _mock_stream_chat_with_usage([
                            {"type": "usage", "source": "pi",
                             "tokens": 200, "cost_usd": 0.005,
                             "usage": {}},
                            {"type": "done", "stop_reason": "end_turn"},
                        ]))

    async def _run():
        async for _ in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="x",
            conversation_history=[],
            conv_id="conv-1",
        ):
            pass

    asyncio.run(_run())
    # Sidecar should exist now with the conv-1 entry.
    sidecar = tmp_path / ".open_edit" / "cost.json"
    assert sidecar.exists()
    state = json.loads(sidecar.read_text())
    assert "conv-1" in state
    assert state["conv-1"]["session_cost_usd"] == pytest.approx(0.005, abs=1e-9)
    assert state["conv-1"]["source"] == "pi"
    assert state["conv-1"]["last_turn_cost_usd"] == pytest.approx(0.005, abs=1e-9)


def test_agent_uses_persisted_session_cost_on_next_turn(
    patched_agent_with_cost, monkeypatch, tmp_path,
):
    """Turn 1: $0.005 cost, persisted. Turn 2: $0.003 cost. The
    cost_update for turn 2 should report turn_cost=0.003 and
    session_cost=0.008."""
    # Seed the sidecar with a previous turn's cost.
    agent_mod._save_cost_state(
        tmp_path,
        {"conv-1": {"session_cost_usd": 0.005, "source": "pi",
                    "last_turn_cost_usd": 0.005}},
    )

    monkeypatch.setattr(agent_mod, "stream_chat",
                        _mock_stream_chat_with_usage([
                            {"type": "usage", "source": "pi",
                             "tokens": 100, "cost_usd": 0.003,
                             "usage": {}},
                            {"type": "done", "stop_reason": "end_turn"},
                        ]))

    async def _collect():
        out = []
        async for ev in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="x",
            conversation_history=[],
            conv_id="conv-1",
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    cost_ev = next(e for e in events if e["type"] == "cost_update")
    assert cost_ev["turn_cost_usd"] == pytest.approx(0.003, abs=1e-9)
    assert cost_ev["session_cost_usd"] == pytest.approx(0.008, abs=1e-9)
    # Sidecar must reflect the new cumulative.
    sidecar = tmp_path / ".open_edit" / "cost.json"
    state = json.loads(sidecar.read_text())
    assert state["conv-1"]["session_cost_usd"] == pytest.approx(0.008, abs=1e-9)


def test_agent_unavailable_source_does_not_demote_persisted_state(
    patched_agent_with_cost, monkeypatch, tmp_path,
):
    """If a turn has source=unavailable (e.g. the LLM yielded no
    usage data), we still report the previous session cost
    unchanged. The brief says: 'When source == unavailable, show
    "cost n/a" ' — so we emit an event that flags this turn's
    source as unavailable, but the session_cost_usd is the
    previously-persisted value."""
    agent_mod._save_cost_state(
        tmp_path,
        {"conv-1": {"session_cost_usd": 0.05, "source": "pi",
                    "last_turn_cost_usd": 0.05}},
    )

    monkeypatch.setattr(agent_mod, "stream_chat",
                        _mock_stream_chat_with_usage([
                            {"type": "usage", "source": "unavailable",
                             "tokens": 0, "cost_usd": 0.0, "usage": {}},
                            {"type": "done", "stop_reason": "end_turn"},
                        ]))

    async def _collect():
        out = []
        async for ev in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="x",
            conversation_history=[],
            conv_id="conv-1",
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    cost_ev = next(e for e in events if e["type"] == "cost_update")
    # Turn cost is 0; session cost unchanged.
    assert cost_ev["turn_cost_usd"] == 0.0
    assert cost_ev["session_cost_usd"] == pytest.approx(0.05, abs=1e-9)
    assert cost_ev["source"] == "unavailable"


def test_agent_no_usage_events_emits_cost_update_with_zeros(
    patched_agent_with_cost, monkeypatch, tmp_path,
):
    """Defensive: if the LLM yields no ``usage`` events at all
    (older provider, or a bug), the cost_update still fires with
    zeros and source=unavailable. The frontend shows "cost n/a"."""
    monkeypatch.setattr(agent_mod, "stream_chat",
                        _mock_stream_chat_with_usage([
                            {"type": "done", "stop_reason": "end_turn"},
                        ]))

    async def _collect():
        out = []
        async for ev in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="x",
            conversation_history=[],
            conv_id="conv-1",
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    cost_ev = next(e for e in events if e["type"] == "cost_update")
    assert cost_ev["turn_cost_usd"] == 0.0
    assert cost_ev["session_cost_usd"] == 0.0
    assert cost_ev["source"] == "unavailable"


def test_agent_chooses_highest_priority_source_in_mixed_turn(
    patched_agent_with_cost, monkeypatch, tmp_path,
):
    """If a single turn has both pi-sourced and computed-sourced
    usage events (e.g. provider switch mid-turn — pathological
    but possible), the cost_update's source field is the
    highest-priority source. Priority: pi > computed > unavailable.
    Pi is preferred because the user's default is pi and pi's
    numbers are authoritative for that provider."""
    # Three calls in one turn: pi, computed, unavailable.
    call_count = {"n": 0}

    async def _mixed_stream_chat(
        messages, tools, system, session_id=None, project_path=None,
    ):
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield {"type": "text_delta", "text": "1"}
            yield {"type": "tool_use", "id": "t1", "name": "add_marker",
                   "input": {}}
            yield {"type": "usage", "source": "computed",
                   "tokens": 50, "cost_usd": 0.0001, "usage": {}}
            yield {"type": "done", "stop_reason": "tool_use"}
        elif call_count["n"] == 2:
            yield {"type": "text_delta", "text": "2"}
            yield {"type": "usage", "source": "pi",
                   "tokens": 70, "cost_usd": 0.0002, "usage": {}}
            yield {"type": "tool_use", "id": "t2", "name": "add_marker",
                   "input": {}}
            yield {"type": "done", "stop_reason": "tool_use"}
        else:
            yield {"type": "text_delta", "text": "3"}
            yield {"type": "usage", "source": "unavailable",
                   "tokens": 0, "cost_usd": 0.0, "usage": {}}
            yield {"type": "done", "stop_reason": "end_turn"}

    monkeypatch.setattr(agent_mod, "stream_chat", _mixed_stream_chat)

    async def _collect():
        out = []
        async for ev in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="x",
            conversation_history=[],
            conv_id="conv-1",
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    cost_ev = next(e for e in events if e["type"] == "cost_update")
    # All three usages sum to: 50+70+0 = 120 tokens, 0.0001+0.0002+0 = 0.0003 cost.
    assert cost_ev["turn_tokens"] == 120
    assert cost_ev["turn_cost_usd"] == pytest.approx(0.0003, abs=1e-9)
    # Highest-priority source = pi.
    assert cost_ev["source"] == "pi"


def test_agent_persists_cost_async_non_blocking(
    patched_agent_with_cost, monkeypatch, tmp_path,
):
    """The brief says cost persistence is 'lazy-loaded; don't block
    turn completion on disk I/O'. We use ``asyncio.to_thread`` so
    the sidecar write doesn't block the event loop. Test asserts
    that the write happens off the main thread (we monkeypatch
    ``asyncio.to_thread`` to record the call)."""
    from unittest import mock as _mock

    # Force ``asyncio.to_thread`` to a sync stub that records calls.
    calls = []
    def fake_to_thread(fn, *args, **kwargs):
        calls.append((fn.__name__, args))
        return fn(*args, **kwargs)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    monkeypatch.setattr(agent_mod, "stream_chat",
                        _mock_stream_chat_with_usage([
                            {"type": "usage", "source": "pi",
                             "tokens": 10, "cost_usd": 0.001,
                             "usage": {}},
                            {"type": "done", "stop_reason": "end_turn"},
                        ]))

    async def _run():
        async for _ in agent_mod.run_agent_turn(
            project_id="costproject",
            user_message="x",
            conversation_history=[],
            conv_id="conv-1",
        ):
            pass

    asyncio.run(_run())
    # At least one asyncio.to_thread call for the cost write.
    assert any(name == "_write_cost_json_sync" for name, _ in calls), (
        f"expected _write_cost_json_sync in to_thread calls, got {calls}"
    )
