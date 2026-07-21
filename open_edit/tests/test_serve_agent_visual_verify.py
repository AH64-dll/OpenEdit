"""v1.5: visual verification loop in the agent.

These tests exercise the new verification stage that runs after every
``trigger_render`` call. They mock the LLM (via ``stream_chat``), the
tool executor (via ``_execute_tool``), and ``ffmpeg`` / ``ffprobe`` (via
``subprocess.run`` patches).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, AsyncIterator
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import agent as agent_mod  # noqa: E402
from open_edit.serve import projects as projects_mod  # noqa: E402


def _fake_mp4(path: Path, duration_s: float = 10.0) -> None:
    """Create a fake MP4 with the magic bytes and the given duration string.
    Real ffprobe is patched in each test, so this is just bytes on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)


def _make_fake_project_state(tmp_path: Path) -> projects_mod.ProjectState:
    """Build a ProjectState that matches the current Pydantic schema."""
    return projects_mod.ProjectState(
        id="testproject",
        name="testproject",
        path=str(tmp_path),
        assets=[],
        ops=[],
        timeline=projects_mod.TimelineSummary(
            total_duration_s=0.0,
            num_clips=0,
            num_effects=0,
            num_markers=0,
        ),
        pending_notes_count=0,
    )


def _make_mock_stream(turns: list[list[dict[str, Any]]]):
    """Return an async generator that plays back a different canned LLM
    response for each turn. ``turns[0]`` is the first response, etc.

    Each turn is a list of stream events, e.g.::

        [
            {"type": "text_delta", "text": "Let me render."},
            {"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}},
            {"type": "done", "stop_reason": "tool_use"},
        ]
    """
    state = {"turn": 0}

    async def _gen(*args, **kwargs):
        idx = min(state["turn"], len(turns) - 1)
        state["turn"] += 1
        for ev in turns[idx]:
            yield ev

    return _gen, state


# A "fake" trigger_render tool result (what pi's extension would return).
# Agent loop in v1.5 reshapes this into a verification block.
_FAKE_RENDER_OK = {
    "output_path": "/tmp/render/r.mp4",
    "mode": "proxy",
    "duration_s": 10.0,
    "render_id": "render_aaa",
}


def _patched_agent_with_render(monkeypatch, tmp_path, *, render_result=None, ffprobe_duration=10.0):
    """Fixture-style helper: patch the agent loop's I/O dependencies and
    return a ``run_agent_turn`` function ready to be awaited."""
    if render_result is None:
        # Create a real MP4 on disk so the verify stage's ffprobe + ffmpeg
        # mock can find it.
        mp4_path = tmp_path / "renders" / "r.mp4"
        mp4_path.parent.mkdir(parents=True, exist_ok=True)
        mp4_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)
        render_result = {
            "output_path": str(mp4_path),
            "mode": "proxy",
            "duration_s": float(ffprobe_duration),
            "render_id": "render_aaa",
        }
    fake_state = _make_fake_project_state(tmp_path)

    async def _fake_get_state(project_id):
        return fake_state

    monkeypatch.setattr(projects_mod, "get_project_state", _fake_get_state)
    monkeypatch.setattr(agent_mod, "_resolve_project_path", lambda pid: tmp_path)

    def fake_subprocess_run(argv, **kwargs):
        cmd = argv[0] if argv else ""
        out_path = None
        if "ffmpeg" in cmd:
            # Output path is the last positional arg (not the arg
            # after -y, which is -i followed by the input path).
            for a in reversed(argv):
                if not a.startswith("-"):
                    out_path = a
                    break
        m = mock.Mock(returncode=0, stdout="", stderr="")
        if "ffprobe" in cmd:
            m.stdout = f"{ffprobe_duration}\n"
        elif "ffmpeg" in cmd and out_path:
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"\xff\xd8\xff\xe0FAKE")
        return m

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)
    return render_result


# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_loop_runs_after_trigger_render(monkeypatch, tmp_path):
    """1 render → verification_started + frames in tool result + verification_result: pass + done."""
    stream_fn, _state = _make_mock_stream([
        [
            {"type": "text_delta", "text": "Let me render."},
            {"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}},
            {"type": "done", "stop_reason": "tool_use"},
        ],
        [
            {"type": "text_delta", "text": "Looks good.\nVERIFICATION: PASS\n"},
            {"type": "done", "stop_reason": "end_turn"},
        ],
    ])

    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)

    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)

    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render please.", [], conv_id=None):
        events.append(ev)

    types = [e["type"] for e in events]
    assert "verification_started" in types
    assert "verification_result" in types
    res = next(e for e in events if e["type"] == "verification_result")
    assert res["outcome"] == "pass"
    assert res["verdict_source"] == "model_explicit_pass"
    assert "done" in types


@pytest.mark.asyncio
async def test_verify_skipped_for_text_only_model(monkeypatch, tmp_path):
    """A text-only model (minimax-m2.7) → no frames in result, outcome=skipped, source=text_only_model."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "minimax-m2.7")
    store = tmp_path / "models-store.json"
    store.write_text(json.dumps({"opencode-go": {"models": [
        {"id": "minimax-m2.7", "input": ["text"]},
        {"id": "minimax-m3", "input": ["text", "image"]},
    ]}}))
    monkeypatch.setenv("HOME", str(tmp_path))

    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "Done."}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)

    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)

    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)
    res = next(e for e in events if e["type"] == "verification_result")
    assert res["outcome"] == "skipped"
    assert res["verdict_source"] == "text_only_model"


@pytest.mark.asyncio
async def test_render_count_capped_at_three(monkeypatch, tmp_path):
    """4 trigger_render calls in 4 turns → 4th returns render_capped tool result."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    monkeypatch.setenv("OPEN_EDIT_VERIFY_MAX_RENDERS", "3")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)

    turns = []
    for i in range(4):
        turns.append([
            {"type": "text_delta", "text": f"Try {i}."},
            {"type": "tool_use", "id": f"t{i}", "name": "trigger_render", "input": {}},
            {"type": "done", "stop_reason": "tool_use"},
        ])
    turns.append([{"type": "text_delta", "text": "VERIFICATION: FAIL"}, {"type": "done", "stop_reason": "end_turn"}])
    stream_fn, _ = _make_mock_stream(turns)

    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)

    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Iterate.", [], conv_id=None):
        events.append(ev)
    res = next(e for e in events if e["type"] == "verification_result" and e.get("verdict_source") == "cap_reached")
    assert res["outcome"] == "capped"
    assert res["verdict_source"] == "cap_reached"
    assert res["render_count"] >= 4
    assert res["max_renders"] == 3


@pytest.mark.asyncio
async def test_iteration_within_cap(monkeypatch, tmp_path):
    """2 renders, both verified, LLM says PASS after 2nd → outcome=pass."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "tool_use", "id": "t2", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "Better now.\nVERIFICATION: PASS\n"}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Iterate.", [], conv_id=None):
        events.append(ev)
    pass_results = [e for e in events if e["type"] == "verification_result" and e["outcome"] == "pass"]
    assert len(pass_results) == 1


@pytest.mark.asyncio
async def test_mutation_tools_executed_before_render_in_batch(monkeypatch, tmp_path):
    """add_clip + trigger_render in one LLM turn → add_clip runs first, render is fresh."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    calls: list[str] = []
    def fake_execute(name, args, path):
        calls.append(name)
        return {"ok": True}
    monkeypatch.setattr(agent_mod, "_execute_tool", fake_execute)
    stream_fn, _ = _make_mock_stream([
        [
            {"type": "tool_use", "id": "a1", "name": "add_clip", "input": {}},
            {"type": "tool_use", "id": "r1", "name": "trigger_render", "input": {}},
            {"type": "done", "stop_reason": "tool_use"},
        ],
        [{"type": "text_delta", "text": "VERIFICATION: PASS\n"}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use" and ev.get("name") == "trigger_render":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Add and render.", [], conv_id=None):
        events.append(ev)
    assert calls == ["add_clip"]


@pytest.mark.asyncio
async def test_only_one_render_per_batch_even_if_multiple_called(monkeypatch, tmp_path):
    """LLM emits two trigger_render calls in one turn → only the last one runs."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    stream_fn, _ = _make_mock_stream([
        [
            {"type": "tool_use", "id": "r1", "name": "trigger_render", "input": {}},
            {"type": "tool_use", "id": "r2", "name": "trigger_render", "input": {}},
            {"type": "done", "stop_reason": "tool_use"},
        ],
        [{"type": "text_delta", "text": "VERIFICATION: PASS\n"}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render twice.", [], conv_id=None):
        events.append(ev)
    # The verify stage emits three ``verification_started`` events per
    # invocation (sampling, encoding, ready). Only the LAST render
    # in the batch should run, so exactly one "ready" stage is emitted.
    ready_starts = [e for e in events if e["type"] == "verification_started" and e.get("stage") == "ready"]
    assert len(ready_starts) == 1


@pytest.mark.asyncio
async def test_pass_line_drives_pass_outcome(monkeypatch, tmp_path):
    """VERIFICATION: PASS → outcome=pass, source=model_explicit_pass."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "VERIFICATION: PASS"}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)
    res = next(e for e in events if e["type"] == "verification_result")
    assert res["outcome"] == "pass"
    assert res["verdict_source"] == "model_explicit_pass"


@pytest.mark.asyncio
async def test_fail_no_tool_calls_emits_uncertain(monkeypatch, tmp_path):
    """VERIFICATION: FAIL with no tool calls → outcome=uncertain, source=model_explicit_fail."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "The overlay is still there.\nVERIFICATION: FAIL"}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)
    res = next(e for e in events if e["type"] == "verification_result")
    assert res["outcome"] == "uncertain"
    assert res["verdict_source"] == "model_explicit_fail"


@pytest.mark.asyncio
async def test_no_verdict_line_emits_no_verdict_line_verdict_source(monkeypatch, tmp_path):
    """LLM says nothing parseable → outcome=uncertain, source=model_no_verdict_line."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "All done."}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)
    res = next(e for e in events if e["type"] == "verification_result")
    assert res["verdict_source"] == "model_no_verdict_line"


@pytest.mark.asyncio
async def test_tool_result_with_images_does_not_bloat_persistent_history(monkeypatch, tmp_path):
    """After a verified render, the slim view sent to the next LLM call has no image blocks."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    seen_messages: list[list[dict]] = []
    async def _spy_stream(messages, **kwargs):
        seen_messages.append(list(messages))
        for ev in [
            {"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}},
            {"type": "done", "stop_reason": "tool_use"},
        ]:
            yield ev
    async def _spy_stream2(messages, **kwargs):
        seen_messages.append(list(messages))
        for ev in [
            {"type": "text_delta", "text": "VERIFICATION: PASS\n"},
            {"type": "done", "stop_reason": "end_turn"},
        ]:
            yield ev
    streams = [_spy_stream, _spy_stream2]
    idx = {"i": 0}
    async def _dispatch(messages, **kwargs):
        s = streams[min(idx["i"], len(streams) - 1)]
        idx["i"] += 1
        async for ev in s(messages, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _dispatch)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)
    last = seen_messages[-1]
    blob = json.dumps(last, default=str)
    assert '"type": "image"' not in blob
    assert "[VISUAL VERIFICATION SUMMARY" in blob


@pytest.mark.asyncio
async def test_cancel_during_ffmpeg_aborts_cleanly(monkeypatch, tmp_path):
    """WebSocketDisconnect mid-ffmpeg → subprocess killed, tmpdir cleaned, no verification_result."""
    from starlette.websockets import WebSocketDisconnect

    async def _raise(*a, **kw):
        raise WebSocketDisconnect(code=1006)
        yield  # pragma: no cover

    monkeypatch.setattr(agent_mod, "stream_chat", _raise)
    _patched_agent_with_render(monkeypatch, tmp_path)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)
    res = [e for e in events if e["type"] == "verification_result"]
    assert res == []


@pytest.mark.asyncio
async def test_no_change_render_returns_no_change_tool_result(monkeypatch, tmp_path):
    """A 2nd trigger_render with the same project state → no ffmpeg, no frames."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setenv("OPEN_EDIT_VERIFY_ALLOW_NO_CHANGE_SKIP", "1")
    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "tool_use", "id": "t2", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "VERIFICATION: PASS\n"}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": {
                    "output_path": render_result["output_path"],
                    "no_change": True,
                    "render_id": "render_nochange",
                    "previous_render_id": render_result["render_id"],
                    "verification": {"verdict_required": False, "frames": [], "reason": "no_change"},
                } if ev["id"] == "t2" else render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render twice.", [], conv_id=None):
        events.append(ev)
    res = [e for e in events if e["type"] == "verification_result" and e.get("render_id") == "render_nochange"]
    assert any(e.get("verdict_source") == "no_change" for e in res)


@pytest.mark.asyncio
async def test_project_meta_verify_disabled_skips_loop(monkeypatch, tmp_path):
    """project_meta.verify_disabled=1 → no verification stage, behaves like v1.4."""
    monkeypatch.setattr(agent_mod, "_llm_provider", lambda: "pi")
    # Create the edit_graph.db with verify_disabled=1 so is_verify_disabled returns True.
    from open_edit.storage.edit_graph import EditGraphStore
    db_path = tmp_path / ".open_edit" / "edit_graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = EditGraphStore(db_path)
    store.set_project_meta_field("verify_disabled", 1)
    fake_state = _make_fake_project_state(tmp_path)

    async def _fake_get_state(project_id):
        return fake_state

    monkeypatch.setattr(projects_mod, "get_project_state", _fake_get_state)
    monkeypatch.setattr(agent_mod, "_resolve_project_path", lambda pid: tmp_path)
    render_result = _patched_agent_with_render(monkeypatch, tmp_path, render_result=_FAKE_RENDER_OK)
    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "Done."}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    async def _stream_with_tool_result(*args, **kwargs):
        async for ev in stream_fn(*args, **kwargs):
            if ev.get("type") == "tool_use":
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    monkeypatch.setattr(agent_mod, "stream_chat", _stream_with_tool_result)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)
    assert not any(e["type"] == "verification_started" for e in events)
    assert not any(e["type"] == "verification_result" for e in events)
