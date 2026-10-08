"""Regression coverage for MCP cleanup, atomic edits, and bounded responses."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from open_edit.agent.tools import get_transcript_packed, list_assets
from open_edit.ir.types import AddClipOp, Asset, RemoveClipOp, TrimClipOp, WordAlignment
from open_edit.ir.validate import OpValidationError
from open_edit.kernel.pillar_tools import dispatch_edit
from open_edit.kernel.schema_validator import SchemaValidationError, validate_tool_args
from open_edit.mcp.adapters import dispatch_mcp_tool
from open_edit.serve.agent.cost_sidecar import _load_cost_state, _save_cost_state_async
from open_edit.serve.visual_verify import model_capability
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


def test_generated_batch_failure_leaves_graph_and_revision_unchanged(tmp_path):
    store = EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")
    first = AddClipOp(author="ai", clip_id="c1", asset_hash="h1", track_id="v1", position_sec=0, out_point_sec=1)
    invalid = RemoveClipOp(author="ai", clip_id="missing")
    result = dispatch_edit(
        "apply_generated_ops", {"ops": [first.model_dump(), invalid.model_dump()]}, tmp_path,
    )
    assert result["status"] == "error"
    assert store.load_all() == []
    assert store.graph_revision() == 0
    with store._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM edit_status_events").fetchone()[0] == 0


def test_batch_can_reference_an_earlier_operation_and_rolls_back_duplicates(tmp_path):
    store = EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")
    clip = AddClipOp(author="ai", clip_id="c1", asset_hash="h1", track_id="v1", position_sec=0, out_point_sec=1)
    trim = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=0, new_out_point_sec=0.5)
    assert store.append_many([clip, trim]) == [0, 1]
    before = store.graph_revision()
    duplicate = clip.model_copy(update={"clip_id": "c2"})
    with pytest.raises((OpValidationError, sqlite3.IntegrityError)):
        store.append_many([duplicate])
    assert store.graph_revision() == before
    assert len(store.load_all()) == 2


def test_project_id_is_stable_under_concurrent_first_access(tmp_path):
    store = EditGraphStore(tmp_path / "edits.db")
    barrier = threading.Barrier(12)

    def first_access(_):
        barrier.wait(timeout=3)
        return store.project_id

    with ThreadPoolExecutor(max_workers=12) as pool:
        ids = list(pool.map(first_access, range(12)))
    assert len(set(ids)) == 1
    assert EditGraphStore(store.db_path).project_id == ids[0]


def test_invalid_status_updates_leave_revision_and_events_unchanged(tmp_path):
    store = EditGraphStore(tmp_path / "edits.db")
    with pytest.raises(LookupError, match="not found"):
        store.update_status("missing", "reverted")
    with pytest.raises(ValueError, match="invalid operation status"):
        store.update_status("missing", "invalid")
    assert store.graph_revision() == 0
    with store._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM edit_status_events").fetchone()[0] == 0
    # Reordering an empty, uninitialized project must not deadlock while
    # creating its ID from a second connection under the write lock.
    assert store.reorder_all([]) == 1


@pytest.mark.parametrize("args", [{}, {"operation": "add_clip", "generate": "music"}])
def test_edit_request_requires_one_mode(args):
    with pytest.raises(SchemaValidationError, match="exactly one"):
        validate_tool_args("edit_project", args)


@pytest.mark.parametrize("args", [
    {"crf": True},
    {"crf": "20"},
    {"ranges": [{"start_sec": True, "end_sec": 2}]},
    {"ranges": [{"start_sec": 0, "end_sec": float("inf")}]},
    {"ranges": [{"start_sec": 4, "end_sec": 2}]},
])
def test_render_validation_rejects_coerced_or_invalid_numbers(args):
    with pytest.raises(SchemaValidationError):
        validate_tool_args("trigger_render", args)


def test_asset_pages_are_bounded_and_can_be_followed(tmp_path):
    root = tmp_path / ".open_edit" / "assets" / "00"
    root.mkdir(parents=True)
    for number in range(123):
        key = f"{number:064x}"
        (root / f"{key}.meta.json").write_text(json.dumps({"asset_hash": key, "duration_sec": 1}))
    seen = []
    offset = 0
    while offset is not None:
        page = list_assets({"offset": offset}, str(tmp_path))
        assert page["total"] == 123
        assert len(page["assets"]) <= 50
        seen.extend(asset["hash"] for asset in page["assets"])
        offset = page["next_offset"]
    assert len(seen) == len(set(seen)) == 123
    assert list_assets({"limit": True}, str(tmp_path))["status"] == "error"


def test_transcript_pages_keep_all_words_without_duplicate_representations(tmp_path):
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    key = "a" * 64
    media = store._cas_path(key)
    media.parent.mkdir(parents=True)
    media.touch()
    asset = Asset(
        asset_hash=key, original_path="audio.wav", stored_path=str(media), type="audio",
        duration_sec=120, has_audio=True,
        alignment=[WordAlignment(word=f"w{i}", t_start=i / 10, t_end=(i + 1) / 10) for i in range(1200)],
    )
    store._sidecar_path(key).write_text(asset.model_dump_json())
    offset = 0
    words = []
    while offset is not None:
        page = get_transcript_packed({"asset_hash": key, "offset": offset}, tmp_path)
        chunk = re.findall(r"\bw\d+\b", page["transcript_packed"])
        assert len(chunk) <= 500
        words.extend(chunk)
        assert "alignment" not in page and "transcript" not in page
        offset = page["next_offset"]
    assert words == [f"w{i}" for i in range(1200)]


@pytest.mark.asyncio
async def test_concurrent_cost_saves_preserve_other_conversations(tmp_path):
    await asyncio.gather(*(
        _save_cost_state_async(tmp_path, {str(i): {"session_cost_usd": i / 100}})
        for i in range(25)
    ))
    assert len(_load_cost_state(tmp_path)) == 25


def test_model_capability_uses_registry_and_survives_corrupt_overrides(tmp_path):
    path = tmp_path / "models.json"
    path.write_text('["bad shape"]')
    assert model_capability("claude-sonnet-4-5", path)["supports_images"] is True
    assert model_capability("o3-mini", path)["supports_images"] is False
    assert model_capability("unknown", path)["supports_images"] is False


@pytest.mark.asyncio
async def test_blocking_mcp_tool_does_not_block_other_tasks(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocking_tool(*args):
        started.set()
        release.wait(timeout=2)
        return {"ok": True}

    monkeypatch.setattr("open_edit.mcp.adapters.execute_tool", blocking_tool)
    task = asyncio.create_task(dispatch_mcp_tool("query_project", {"query": "list_assets"}, tmp_path))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        assert not task.done()
    finally:
        release.set()
        assert (await task)["ok"] is True


@pytest.mark.asyncio
async def test_real_stdio_mcp_round_trip_and_error_flag(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "open_edit.mcp.server", "--project", str(tmp_path)],
    )
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        initialized = await session.initialize()
        assert len(initialized.instructions.encode("utf-8")) < 2000
        assert len((await session.list_tools()).tools) == 6
        result = await session.call_tool("query_project", {"query": "list_assets"})
        assert result.isError is False
        assert json.loads(result.content[0].text)["assets"] == []
        invalid = await session.call_tool("edit_project", {})
        assert invalid.isError is True
        scripted = await session.call_tool("run_script", {"code": "print('MCP script works')"})
        assert scripted.isError is False
        assert json.loads(scripted.content[0].text)["status"] == "ok"
        failed = await session.call_tool("run_script", {"code": "raise RuntimeError('boom')"})
        assert failed.isError is True


def test_context_budget_preserves_current_request_and_complete_exchange():
    from open_edit.serve.context_budget import ContextBudget

    call = {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "edit_project", "input": {"n": 4}}]}
    result = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "complete"}]}
    history = [
        {"role": "user", "content": "opening request"},
        {"role": "assistant", "content": "old" * 1000},
        {"role": "user", "content": "latest correction"},
        call, result,
    ]
    compacted = ContextBudget(max_tokens=200, reserve_tokens=20).truncate(history)
    assert history[2] in compacted
    assert call in compacted and result in compacted
    assert compacted.index(result) == compacted.index(call) + 1
    assert history[1] not in compacted


@pytest.mark.parametrize("identifier", ["../escape", "/tmp/escape", "a/b", "a\\b", ["invalid"], "a" * 129])
def test_conversation_paths_reject_invalid_ids(tmp_path, monkeypatch, identifier):
    from open_edit.serve.agent import append_to_conversation, load_conversation

    monkeypatch.setattr("open_edit.serve.agent._resolve_project_path", lambda _: tmp_path)
    with pytest.raises(ValueError, match="conv_id"):
        append_to_conversation("project", identifier, {"role": "user", "content": "unsafe"})
    with pytest.raises(ValueError, match="conv_id"):
        load_conversation("project", identifier)
    assert not (tmp_path / ".open_edit").exists()


def test_concurrent_history_appends_survive_compaction(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from open_edit.serve.agent import append_to_conversation, load_conversation

    monkeypatch.setattr("open_edit.serve.agent._resolve_project_path", lambda _: tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: append_to_conversation(
            "project", "conversation", {"role": "assistant", "content": str(i)},
        ), range(200)))
    history = load_conversation("project", "conversation")
    assert sorted(int(msg["content"]) for msg in history) == list(range(200))


def test_script_batch_rolls_back_on_late_reference_failure(tmp_path, monkeypatch):
    from open_edit.agent.exceptions import FreeFormResult
    from open_edit.agent.tools import run_python

    store = EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")
    clip = AddClipOp(author="ai", clip_id="c", asset_hash="h", track_id="v1", position_sec=0, out_point_sec=1)
    result = FreeFormResult.ok([clip, RemoveClipOp(author="ai", clip_id="missing")], 0)
    monkeypatch.setattr("open_edit.agent.tools.pyagent_run_python.run_free_form", lambda **_: result)
    assert run_python({"code": "pass"}, str(tmp_path))["status"] == "error"
    assert store.load_all() == [] and store.graph_revision() == 0


def test_free_form_cli_resolves_the_current_project_layout(tmp_path, monkeypatch):
    from open_edit.agent.exceptions import FreeFormResult
    from open_edit.cli import main

    store = EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")
    script = tmp_path / "edit.py"
    script.write_text("pass")
    seen = []

    def run(code, workdir, **kwargs):
        seen.append(workdir)
        return FreeFormResult.ok([], 0)

    monkeypatch.setattr("open_edit.agent.script_runner.run_free_form", run)
    assert main(["free-form", str(script), str(tmp_path)]) == 0
    assert seen == [store.db_path.parent]
    assert not (tmp_path / "edit_graph.db").exists()


@pytest.mark.parametrize("codec,expected", [("hevc_nvenc", "libx265"), ("av1_nvenc", "libsvtav1")])
def test_encoder_fallback_preserves_the_requested_codec(monkeypatch, codec, expected):
    from open_edit.render import encoder

    monkeypatch.setattr(encoder, "_probe_encoder", lambda *args: False)
    assert encoder.apply_profile_vcodec(codec, "gpu") == expected


@pytest.mark.asyncio
async def test_render_coalescing_includes_quality_and_encoder(tmp_path, monkeypatch):
    from open_edit.kernel.render_jobs import RenderJobService

    service = RenderJobService()
    EditGraphStore(tmp_path / ".open_edit" / "edit_graph.db")

    async def launch(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_launch", launch)
    first = service.enqueue("p", tmp_path, "final", encoder_backend="cpu", params={"quality": "high"})
    same = service.enqueue("p", tmp_path, "final", encoder_backend="cpu", params={"quality": "high"})
    quality = service.enqueue("p", tmp_path, "final", encoder_backend="cpu", params={"quality": "fast"})
    backend = service.enqueue("p", tmp_path, "final", encoder_backend="gpu", params={"quality": "high"})
    assert first.job_id == same.job_id
    assert len({first.job_id, quality.job_id, backend.job_id}) == 3
    assert backend.params["encoder_backend"] == "gpu"
    await service.shutdown()
    assert all(job.status == "cancelled" for job in service.list_jobs(tmp_path))


@pytest.mark.asyncio
async def test_render_services_share_a_lease_and_waiters_do_not_cancel_owner(tmp_path, monkeypatch):
    from open_edit.kernel.render_jobs import RenderJobService

    owner, other = RenderJobService(), RenderJobService()
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def launch(*args):
        calls.append(args[1])
        started.set()
        await release.wait()
        return {"ok": True, "output_path": str(tmp_path / "out.mp4")}

    monkeypatch.setattr(owner, "_launch", launch)
    monkeypatch.setattr(other, "_launch", launch)
    job = owner.enqueue("p", tmp_path, "proxy")
    await asyncio.wait_for(started.wait(), timeout=2)
    alias = other.enqueue("p", tmp_path, "proxy")
    assert alias.job_id == job.job_id
    assert other.recover(tmp_path) == 0
    await asyncio.sleep(0)
    await other.shutdown()
    assert owner.get(tmp_path, job.job_id).status == "running"
    alias = other.enqueue("p", tmp_path, "proxy")
    release.set()
    await asyncio.gather(owner.wait(tmp_path, job.job_id), other.wait(tmp_path, alias.job_id))
    assert calls == [job.job_id]
    assert other.get(tmp_path, alias.job_id).status == "succeeded"


@pytest.mark.asyncio
async def test_shutdown_reaps_a_child_spawned_during_cancellation(tmp_path, monkeypatch):
    from open_edit.kernel.render_jobs import RenderJobService

    original = asyncio.create_subprocess_exec
    spawn_started, release = asyncio.Event(), asyncio.Event()
    processes = []

    async def delayed_spawn(*args, **kwargs):
        spawn_started.set()
        await release.wait()
        proc = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    service = RenderJobService(cancel_grace_s=0.2)
    job = service.enqueue("p", tmp_path, "proxy")
    await asyncio.wait_for(spawn_started.wait(), timeout=2)
    shutdown = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0)
    release.set()
    await asyncio.wait_for(shutdown, timeout=3)
    assert processes[0].returncode is not None
    assert service.get(tmp_path, job.job_id).status == "cancelled"


@pytest.mark.asyncio
async def test_remote_cancellation_during_qc_cannot_be_overwritten(tmp_path, monkeypatch):
    from open_edit.kernel.render_jobs import RenderJobService

    owner, other = RenderJobService(), RenderJobService()
    started, release = asyncio.Event(), asyncio.Event()

    async def launch(*args):
        return {"ok": True, "output_path": str(tmp_path / "out.mp4")}

    async def qc(result, project_path):
        started.set()
        await release.wait()
        return result

    monkeypatch.setattr(owner, "_launch", launch)
    monkeypatch.setattr(owner, "_attach_qc", qc)
    job = owner.enqueue("p", tmp_path, "proxy")
    await asyncio.wait_for(started.wait(), timeout=2)
    await other.cancel(tmp_path, job.job_id)
    release.set()
    assert (await owner.wait(tmp_path, job.job_id)).status == "cancelled"


@pytest.mark.asyncio
async def test_overlay_worker_is_a_reapable_subprocess(tmp_path, monkeypatch):
    from open_edit.kernel.render_jobs import RenderJobService

    original = asyncio.create_subprocess_exec
    started = asyncio.Event()
    processes, commands = [], []

    async def spawn(*command, **kwargs):
        commands.append(command)
        process = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    service = RenderJobService(cancel_grace_s=0.2)
    job = service.enqueue("p", tmp_path, "overlay")
    await asyncio.wait_for(started.wait(), timeout=2)
    await asyncio.wait_for(service.cancel(tmp_path, job.job_id), timeout=3)
    await service.shutdown()
    assert "open_edit.kernel.render_overlay" in commands[0]
    assert processes[0].returncode is not None
    assert service.get(tmp_path, job.job_id).status == "cancelled"


def test_nonoverlay_render_does_not_require_hyperframes(tmp_path, monkeypatch):
    from open_edit.kernel import render_overlay

    def unnecessary_binary_lookup(*args):
        pytest.fail("HyperFrames is unnecessary for a plain MLT render")

    monkeypatch.setattr(render_overlay, "_build_render_spec", unnecessary_binary_lookup)
    monkeypatch.setattr(render_overlay, "_run_mlt_only_render", lambda *args: {"output_path": "out.mp4"})
    assert render_overlay.run_trigger_render({"mode": "proxy"}, tmp_path)["output_path"] == "out.mp4"


def test_hyperframes_executable_path_preserves_spaces(tmp_path, monkeypatch):
    from open_edit.render import html_overlay

    executable = tmp_path / "engine with spaces" / "hyperframes"
    executable.parent.mkdir()
    executable.write_text("placeholder")
    composition = tmp_path / "source.html"
    composition.write_text("<html></html>")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return kwargs["output_path"]

    monkeypatch.setattr(html_overlay, "_run_subprocess_with_cancel", run)
    html_overlay.render_overlay_layer(composition, tmp_path / "out.mov", {
        "hyperframes_bin": str(executable), "fps": 30,
        "hyperframes_timeout_s": 30, "tmpdir": tmp_path / "render",
    })
    assert commands[0][0] == str(executable)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg/ffprobe not installed")
@pytest.mark.parametrize("with_audio", [False, True])
def test_real_ffmpeg_composite_keeps_optional_background_audio(tmp_path, with_audio):
    from open_edit.render.html_overlay import composite_with_background

    common = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi"]
    background = [*common, "-i", "color=c=black:s=64x64:r=10:d=0.4"]
    if with_audio:
        background += ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.4", "-c:a", "aac"]
    background += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "background.mp4")]
    overlay = [*common, "-i", "color=c=red:s=64x64:r=10:d=0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "overlay.mov")]
    subprocess.run(background, check=True, capture_output=True, timeout=10)
    subprocess.run(overlay, check=True, capture_output=True, timeout=10)
    result = composite_with_background(
        tmp_path / "background.mp4", tmp_path / "overlay.mov",
        tmp_path / "output.mp4", {"hyperframes_timeout_s": 10},
    )
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(result),
    ], check=True, capture_output=True, text=True, timeout=10)
    streams = json.loads(probe.stdout)["streams"]
    assert any(stream["codec_type"] == "video" for stream in streams)
    assert sum(stream["codec_type"] == "audio" for stream in streams) == int(with_audio)


def test_render_polling_omits_duplicate_logs_and_keeps_qc_failures():
    from open_edit.kernel.render_jobs import RenderJob, public_job

    qc = {"passed": False, "complete": True, "checks": [{"name": "black", "passed": False}]}
    job = RenderJob("j", "p", "proxy", "succeeded", 1, 2, result={
        "output_path": "out.mp4", "diagnostics": {"log": "x" * 100000}, "qc_report": qc,
    }, qc_report=qc)
    compact = public_job(job, include_details=False)
    assert compact["result"] == {"output_path": "out.mp4"}
    assert compact["qc_report"]["failed_checks"] == qc["checks"]
    assert public_job(job)["result"]["diagnostics"]["log"] == "x" * 100000
