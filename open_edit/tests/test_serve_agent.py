"""Tests for ``open_edit.serve.agent``.

Mocks the LLM (``stream_chat``) and the tool execution dispatcher so the
agent loop can be tested without a real API key or the ``open_edit``
tool modules.

The mocked LLM plays back a canned 2-turn conversation:
  Turn 1: text("Let me check.") + tool_use(list_assets) + done(tool_use)
  Turn 2: text("You have 2 assets.") + done(end_turn)

Expected AgentEvent sequence:
  text "Let me check."
  tool_start list_assets
  tool_result list_assets {...}
  text "You have 2 assets."
  done end_turn
"""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path
from typing import Any, AsyncIterator
from unittest import mock

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import agent as agent_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402
from open_edit.serve.llm import StreamEvent  # noqa: E402


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

async def _mock_stream_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None = None,
    project_path: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Play back a canned 2-turn conversation based on how many assistant
    messages are already in ``messages``."""
    # Count how many assistant messages are in history so far.
    assistant_turns = sum(1 for m in messages if m.get("role") == "assistant")

    if assistant_turns == 0:
        # Turn 1: lead-in text + a tool call.
        yield {"type": "text_delta", "text": "Let me check."}
        yield {
            "type": "tool_use",
            "id": "tool_call_1",
            "name": "list_assets",
            "input": {},
        }
        yield {"type": "done", "stop_reason": "tool_use"}
    else:
        # Turn 2: final answer.
        yield {"type": "text_delta", "text": "You have 2 assets."}
        yield {"type": "done", "stop_reason": "end_turn"}


def _mock_execute_tool(name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Return a canned result for any tool."""
    return {
        "tool": name,
        "args": args,
        "result": {
            "assets": [
                {"hash": "h1", "filename": "intro.mp4", "duration": 12.5},
                {"hash": "h2", "filename": "outro.mp4", "duration": 8.0},
            ],
        },
    }


@pytest.fixture
def patched_agent(monkeypatch, tmp_path):
    """Patch all I/O dependencies of the agent loop.

    - ``stream_chat`` → canned 2-turn conversation
    - ``_execute_tool`` → canned result
    - ``projects.get_project_state`` → fake state (no DB needed)
    - ``projects._resolve_project_by_id`` → temp dir path
    """
    # Fake project state
    fake_state = projects_mod.ProjectState(
        id="testproject",
        name="testproject",
        path=str(tmp_path),
        assets=[
            projects_mod.AssetInfo(hash="h1", filename="intro.mp4", duration_s=12.5),
            projects_mod.AssetInfo(hash="h2", filename="outro.mp4", duration_s=8.0),
        ],
        ops=[],
        timeline=projects_mod.TimelineSummary(
            total_duration_s=20.5,
            num_clips=0,
            num_effects=0,
            num_markers=0,
        ),
        pending_notes_count=0,
    )

    async def fake_get_state(project_id):
        if project_id != "testproject":
            raise KeyError(project_id)
        return fake_state

    def fake_resolve(project_id):
        if project_id != "testproject":
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

@pytest.mark.asyncio
async def test_agent_loop_two_turn_with_tool_call(patched_agent):
    """Full 2-turn conversation: user → tool → final text."""
    history: list[dict[str, Any]] = []
    events = []

    async for ev in agent_mod.run_agent_turn(
        project_id="testproject",
        user_message="what do I have?",
        conversation_history=history,
    ):
        events.append(ev)

    # Verify event sequence
    types = [e["type"] for e in events]
    assert types == [
        "text",         # "Let me check."
        "tool_start",   # list_assets
        "tool_result",  # list_assets
        "text",         # "You have 2 assets."
        "done",         # turn end
        "cost_update",  # v1.4 P1-3 — cost summary after done
    ]

    # Verify text content
    assert events[0]["text"] == "Let me check."
    assert events[3]["text"] == "You have 2 assets."

    # Verify tool_start / tool_result
    assert events[1]["name"] == "list_assets"
    assert events[1]["input"] == {}
    assert events[2]["name"] == "list_assets"
    assert "result" in events[2]
    assert events[2]["result"]["result"]["assets"][0]["hash"] == "h1"

    # Verify done
    assert events[4]["stop_reason"] == "end_turn"

    # Verify conversation history was updated correctly:
    # 1 user msg + 1 assistant msg (text + tool_use) + 1 tool_result msg + 1 assistant msg (text)
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "what do I have?"
    assert history[1]["role"] == "assistant"
    assert any(b["type"] == "tool_use" for b in history[1]["content"])
    assert history[2]["role"] == "user"
    assert history[2]["content"][0]["type"] == "tool_result"
    assert history[2]["content"][0]["tool_use_id"] == "tool_call_1"
    assert history[3]["role"] == "assistant"
    assert any(b["type"] == "text" for b in history[3]["content"])


@pytest.mark.asyncio
async def test_agent_loop_tool_error_surfaced(patched_agent, monkeypatch):
    """When a tool raises, the loop emits an error event and continues."""
    def failing_tool(name, args, project_path):
        raise RuntimeError("boom")
    monkeypatch.setattr(agent_mod, "_execute_tool", failing_tool)

    history: list[dict[str, Any]] = []
    events = []

    async for ev in agent_mod.run_agent_turn(
        project_id="testproject",
        user_message="list my assets",
        conversation_history=history,
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    assert "error" in types
    err_event = next(e for e in events if e["type"] == "error")
    assert "boom" in err_event["message"]
    assert "list_assets" in err_event["message"]


@pytest.mark.asyncio
async def test_agent_loop_unknown_project(patched_agent):
    """Unknown project id → error + done(error)."""
    history: list[dict[str, Any]] = []
    events = []

    async for ev in agent_mod.run_agent_turn(
        project_id="does-not-exist",
        user_message="hi",
        conversation_history=history,
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    assert "error" in types
    assert types[-1] == "done"
    assert events[-1]["stop_reason"] == "error"


@pytest.mark.asyncio
async def test_conversation_persistence_roundtrip(patched_agent, tmp_path):
    """append_to_conversation + load_conversation roundtrip."""
    # Create a fake project structure for persistence.
    project_path = tmp_path / "persisttest"
    (project_path / ".open_edit" / "conversations").mkdir(parents=True)
    conv_id = "abc123"

    # Patch _resolve_project_by_id to return our fake project.
    def fake_resolve(project_id):
        if project_id == "persistproject":
            return project_path
        return None

    with mock.patch.object(projects_mod, "_resolve_project_by_id", fake_resolve):
        msg1 = {"role": "user", "content": "first message"}
        msg2 = {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}
        agent_mod.append_to_conversation("persistproject", conv_id, msg1)
        agent_mod.append_to_conversation("persistproject", conv_id, msg2)

        loaded = agent_mod.load_conversation("persistproject", conv_id)
        assert len(loaded) == 2
        assert loaded[0] == msg1
        assert loaded[1] == msg2

        # Non-existent conversation loads as []
        assert agent_mod.load_conversation("persistproject", "no-such-id") == []


@pytest.mark.asyncio
async def test_system_prompt_is_deterministic(patched_agent):
    """Same project state → same system prompt (enables prompt caching)."""
    state1 = await projects_mod.get_project_state("testproject")
    state2 = await projects_mod.get_project_state("testproject")
    prompt1 = agent_mod._build_system_prompt(state1)
    prompt2 = agent_mod._build_system_prompt(state2)
    assert prompt1 == prompt2
    # Spot-check that key sections are present.
    assert "## Project state" in prompt1
    assert "## Available tools" in prompt1
    assert "list_assets" in prompt1
    assert "trigger_render" in prompt1


# ---------------------------------------------------------------------------
# v1.6 V4 bugfix: in-process trigger_render must return the same
# structured shape as the pi subprocess path ({output_path, mode,
# duration_s, render_id}). The verification stage reads
# ``result.get("render_id", ...)``; without these fields, the in-process
# path always falls back to "render_unknown" and breaks observability.
# ---------------------------------------------------------------------------


def test_execute_trigger_render_in_process_returns_structured_shape(tmp_path):
    """V4: ``_execute_trigger_render`` (in-process agent path) must
    return a dict with ``render_id`` and ``duration_s`` for non-overlay
    modes, matching the pi subprocess path. The verification stage
    reads these fields via ``result.get('render_id', ...)``."""
    from open_edit.serve import agent

    renders = tmp_path / ".open_edit" / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    fake = renders / "project_aaa.mp4"
    fake.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    proc = mock.Mock(returncode=0, stdout=f"{fake}\n", stderr="")

    with mock.patch("subprocess.run", return_value=proc), \
         mock.patch("open_edit.serve.tool_executor._probe_duration", return_value=10.5):
        out = agent._execute_trigger_render({"mode": "proxy"}, tmp_path)

    # Required structured fields (must match pi subprocess shape)
    assert "output_path" in out
    assert out["output_path"] == str(fake)
    assert "mode" in out
    assert out["mode"] == "proxy"
    assert "render_id" in out
    assert out["render_id"].startswith("render_")
    assert "duration_s" in out
    assert out["duration_s"] == 10.5


def test_execute_trigger_render_in_process_duration_zero_on_missing_file(tmp_path):
    """V4: when the output file doesn't exist (parse fallback path),
    ``duration_s`` is 0.0 (not raised) and ``render_id`` is present.
    The verification stage must always see a render_id."""
    from open_edit.serve import agent

    # Subprocess returns stdout that doesn't look like a path → no file
    proc = mock.Mock(returncode=0, stdout="not a path\n", stderr="")
    with mock.patch("subprocess.run", return_value=proc):
        out = agent._execute_trigger_render({"mode": "final"}, tmp_path)

    assert out["mode"] == "final"
    assert out["output_path"] == ""
    assert out["render_id"].startswith("render_")
    assert out["duration_s"] == 0.0


# ---------------------------------------------------------------------------
# v1.6 polish: ``MAX_AGENT_ITERATIONS`` is module-scope and env-overridable;
# ``_llm_provider()`` is resolved once per turn (hoisted out of the loop).
# ---------------------------------------------------------------------------


def test_max_agent_iterations_module_scope_default(monkeypatch):
    """V6-1: ``MAX_AGENT_ITERATIONS`` is exposed at module scope and
    defaults to 10 when ``OPEN_EDIT_AGENT_MAX_ITERATIONS`` is unset."""
    monkeypatch.delenv("OPEN_EDIT_AGENT_MAX_ITERATIONS", raising=False)
    importlib.reload(agent_mod)
    try:
        assert hasattr(agent_mod, "MAX_AGENT_ITERATIONS")
        assert agent_mod.MAX_AGENT_ITERATIONS == 10
    finally:
        # Restore the module to its on-import state so we don't leak
        # the reloaded constant into other tests in this process.
        importlib.reload(agent_mod)


def test_max_agent_iterations_env_override(monkeypatch):
    """V6-1: ``OPEN_EDIT_AGENT_MAX_ITERATIONS`` overrides the default
    cap at import time. Operators can tune the safety cap without
    editing code."""
    monkeypatch.setenv("OPEN_EDIT_AGENT_MAX_ITERATIONS", "7")
    importlib.reload(agent_mod)
    try:
        assert agent_mod.MAX_AGENT_ITERATIONS == 7
    finally:
        importlib.reload(agent_mod)


@pytest.mark.asyncio
async def test_provider_does_tool_exec_resolved_once_per_turn(patched_agent, monkeypatch):
    """V6-2: ``_llm_provider()`` is hoisted out of the per-iteration
    loop. Provider doesn't change between iterations of the same turn,
    so resolving it once is enough. The canned ``_mock_stream_chat``
    yields a 2-turn conversation, which means the loop runs twice;
    before the fix the provider resolver was called once per iteration
    (2 times), after the fix it's called once per turn (1 time)."""
    call_count = {"n": 0}

    def counting_provider() -> str:
        call_count["n"] += 1
        return "anthropic"

    # Patch the module-scope alias (after the fix) AND the underlying
    # llm._provider (in case any code path re-imports it).
    monkeypatch.setattr(agent_mod, "_llm_provider", counting_provider)
    monkeypatch.setattr("open_edit.serve.llm._provider", counting_provider)

    history: list[dict[str, Any]] = []
    async for _ev in agent_mod.run_agent_turn(
        project_id="testproject",
        user_message="what do I have?",
        conversation_history=history,
    ):
        pass

    assert call_count["n"] == 1, (
        f"expected _llm_provider() to be called once per turn; got {call_count['n']}"
    )
