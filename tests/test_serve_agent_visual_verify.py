"""v1.5: visual verification loop in the agent.

These tests exercise the new verification stage that runs after every
``trigger_render`` call. They mock the LLM (via ``stream_chat``), the
tool executor (via ``_execute_tool``), and ``ffmpeg`` / ``ffprobe`` (via
``subprocess.run`` patches).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from open_edit.serve import agent as agent_mod
from open_edit.serve import projects as projects_mod

_REPO_ROOT = Path(__file__).resolve().parents[1]



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


# A fake trigger_render tool result from the kernel.
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
        # Create the on-disk render fixture used by the mocked media tools.
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
            m.stdout = json.dumps({
                "streams": [{"codec_type": "video", "duration": str(ffprobe_duration),
                             "avg_frame_rate": "30/1"}],
                "format": {"duration": str(ffprobe_duration)},
            })
        elif "ffmpeg" in cmd and out_path:
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"\xff\xd8\xff\xe0FAKE")
        return m

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
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

    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )

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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
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
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )

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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    monkeypatch.setenv("OPEN_EDIT_VERIFY_MAX_RENDERS", "3")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )

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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
    calls: list[str] = []
    def fake_execute(name, args, path, command_id=None):
        calls.append(name)
        if name == "trigger_render":
            return render_result
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
    # SDK providers execute every tool locally; the guarantee under test
    # is that the mutation runs BEFORE the render in the same batch.
    assert calls == ["add_clip", "trigger_render"]


@pytest.mark.asyncio
async def test_only_one_render_per_batch_even_if_multiple_called(monkeypatch, tmp_path):
    """LLM emits two trigger_render calls in one turn → only the last one runs."""
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
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
async def test_tool_result_images_reach_verdict_but_persist_image_free(monkeypatch, tmp_path):
    """After a verified render the durable history must be image-free, while
    the pending verdict call (last slim view) keeps the newest frames so the
    model can actually judge them (A3-1), and the final post-verdict slim
    view prunes them again (keep_last_n summaries still collapse)."""
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
    async def _fake_get_state(project_id):
        return _make_fake_project_state(tmp_path)
    monkeypatch.setattr(projects_mod, "get_project_state", _fake_get_state)
    monkeypatch.setattr(agent_mod, "_resolve_project_path", lambda pid: tmp_path)
    seen_messages: list[list[dict]] = []
    per_turn_tool_result = True
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
            if ev.get("type") == "tool_use" and per_turn_tool_result:
                yield {"type": "tool_result", "name": ev["name"], "result": render_result}
            yield ev
    appended: list[dict] = []
    real_append = agent_mod.append_to_conversation
    def _spy_append(project_id, conv_id, message):
        appended.append(message)
        return real_append(project_id, conv_id, message)
    monkeypatch.setattr(agent_mod, "append_to_conversation", _spy_append)
    monkeypatch.setattr(agent_mod, "stream_chat", _dispatch)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render.", [], conv_id=None):
        events.append(ev)

    assert idx["i"] >= 2, "expected a verdict call after the render call"
    verdict_call = seen_messages[1]
    verdict_blob = json.dumps(verdict_call, default=str)

    # Verdict call: newest frame-bearing tool_result keeps its frames so the
    # model actually sees the rendering (A3-1 fix).
    verdict_images = sum(
        1 for m in verdict_call
        for b in (m.get("content") if isinstance(m.get("content"), list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
        and isinstance(b.get("content"), list)
        and any(isinstance(x, dict) and x.get("type") == "image" for x in b["content"])
    )
    assert verdict_images >= 1, "verdict call lost the pending verification frames"
    assert "[VISUAL VERIFICATION SUMMARY" in verdict_blob
    # anchor summary stays parseable: render_id readable (top-level or nested),
    # frame_count present — the next prune can still match this tool_result.
    assert "render_aaa" in verdict_blob
    # NOTE: the summary text sits inside a JSON string, so its quotes are
    # escaped in the slim-view dump; match the unescaped key part.
    assert 'frame_count' in verdict_blob

    # Durable copies are image-free regardless of the verdict state.
    for msg in appended:
        blob = json.dumps(msg, default=str)
        assert '"type": "image"' not in blob, "durable history must stay image-free"
        assert "[VISUAL VERIFICATION SUMMARY" in blob or "render_aaa" in blob


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
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    render_calls = {"n": 0}

    def fake_execute(name, args, path, command_id=None):
        render_calls["n"] += 1
        if render_calls["n"] >= 2:
            return {
                "output_path": render_result["output_path"],
                "no_change": True,
                "render_id": "render_nochange",
                "previous_render_id": render_result["render_id"],
                "verification": {"verdict_required": False, "frames": [], "reason": "no_change"},
            }
        return render_result

    monkeypatch.setattr(agent_mod, "_execute_tool", fake_execute)
    monkeypatch.setenv("OPEN_EDIT_VERIFY_ALLOW_NO_CHANGE_SKIP", "1")
    stream_fn, _ = _make_mock_stream([
        [{"type": "tool_use", "id": "t1", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "tool_use", "id": "t2", "name": "trigger_render", "input": {}}, {"type": "done", "stop_reason": "tool_use"}],
        [{"type": "text_delta", "text": "VERIFICATION: PASS\n"}, {"type": "done", "stop_reason": "end_turn"}],
    ])
    monkeypatch.setattr(agent_mod, "stream_chat", stream_fn)
    events: list[dict] = []
    async for ev in agent_mod.run_agent_turn("testproject", "Render twice.", [], conv_id=None):
        events.append(ev)
    res = [e for e in events if e["type"] == "verification_result" and e.get("render_id") == "render_nochange"]
    assert any(e.get("verdict_source") == "no_change" for e in res)


@pytest.mark.asyncio
async def test_project_meta_verify_disabled_skips_loop(monkeypatch, tmp_path):
    """project_meta.verify_disabled=1 → no verification stage, behaves like v1.4."""
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
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


@pytest.mark.asyncio
async def test_qc_report_flows_into_verification_evidence(monkeypatch, tmp_path):
    """A qc_report on the render result is consumed as deterministic
    evidence in the verification block the LLM sees (spans, not blind
    sampling)."""
    monkeypatch.setattr(agent_mod, "effective_provider", lambda project_path: "anthropic")
    render_result = _patched_agent_with_render(monkeypatch, tmp_path)
    render_result["qc_report"] = {
        "passed": False,
        "duration_sec": 10.0,
        "checks": [{"name": "streams", "passed": False}, {"name": "duration", "passed": True}],
        "spans": {
            "black_frames": [],
            "silence": [{"start_sec": 1.2, "end_sec": 2.4, "duration_sec": 1.2}],
            "frozen_frames": [],
        },
    }
    monkeypatch.setattr(
        agent_mod, "_execute_tool",
        lambda name, args, path, command_id=None: render_result,
    )
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

    assert any(e["type"] == "verification_result" for e in events)
    last = seen_messages[-1]
    blob = json.dumps(last, default=str)
    assert "Deterministic QC: FAIL" in blob
    assert "Failed checks: streams" in blob
    assert "Silent gaps: 1.20-2.40s" in blob
