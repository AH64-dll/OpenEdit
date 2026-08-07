from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

import pytest

from open_edit import cli
from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import AddClipOp, AddRemotionCompositionOp, SetAudioGainOp
from open_edit.kernel.render_jobs import RenderJob, RenderJobService
from open_edit.render import preview_chunks
from open_edit.render.preview_cache import PreviewChunkCache
from open_edit.render.preview_invalidation import ChunkFingerprint
from open_edit.render.preview_manifest import (
    PreviewChunk,
    PreviewManifest,
    PreviewPlaneState,
)
from open_edit.storage.edit_graph import EditGraphStore


def _project(
    tmp_path: Path,
    *,
    duration_sec: float = 2.0,
) -> tuple[Path, EditGraphStore]:
    project_dir = tmp_path / "project"
    open_edit_dir = project_dir / ".open_edit"
    open_edit_dir.mkdir(parents=True)
    store = EditGraphStore(open_edit_dir / "edit_graph.db")
    store.append(
        AddClipOp(
            author="user",
            asset_hash="asset-video",
            track_id="v1",
            track_kind="video",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=duration_sec,
        )
    )
    return project_dir, store


def _seed_manifest(
    project_dir: Path,
    store: EditGraphStore,
    *,
    duration_sec: float = 2.0,
) -> PreviewChunkCache:
    cache = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        max_bytes=1_000_000,
        max_age_sec=None,
        min_free_bytes=0,
    )
    graph_hash = compute_edit_graph_hash(store.load_all())
    chunks: list[PreviewChunk] = []
    chunk_count = max(1, round(duration_sec))
    for index in range(chunk_count):
        states: dict[str, PreviewPlaneState] = {}
        for plane, suffix in (("video", "mp4"), ("audio", "m4a"), ("playback", "mp4")):
            key = (
                "old-playback"
                if index == 1 and plane == "playback"
                else f"old-{plane}-{index}"
            )
            source = project_dir / f"{key}.source"
            source.write_bytes(f"{key}\n".encode())
            artifact = cache.commit_artifact(
                plane=plane,
                key=key,
                source=source,
                suffix=suffix,
                graph_hash=graph_hash,
            )
            states[plane] = PreviewPlaneState(status="green", current=artifact)
        chunks.append(
            PreviewChunk(
                chunk_id=f"{index * 30:06d}-{(index + 1) * 30:06d}",
                index=index,
                start_frame=index * 30,
                end_frame=(index + 1) * 30,
                start_sec=float(index),
                end_sec=float(index + 1),
                status="green",
                video=states["video"],
                audio=states["audio"],
                playback=states["playback"],
            )
        )
    cache.write_manifest(
        PreviewManifest(
            project_id="project",
            graph_revision=store.graph_revision(),
            edit_graph_hash=graph_hash,
            duration_frames=chunk_count * 30,
            duration_sec=float(chunk_count),
            fps_num=30,
            fps_den=1,
            chunk_frames=30,
            profile={"name": "preview_chunk"},
            updated_at=time.time(),
            chunks=chunks,
        )
    )
    return cache


def _patch_params(
    monkeypatch: pytest.MonkeyPatch,
    params: dict,
    *,
    chunk_count: int = 2,
    video_dirty_indices: set[int] | None = None,
    audio_dirty_indices: set[int] | None = None,
    key_prefix: str = "new",
) -> None:
    if video_dirty_indices is None:
        video_dirty_indices = {1}
    if audio_dirty_indices is None:
        audio_dirty_indices = set(video_dirty_indices)
    monkeypatch.setattr(
        preview_chunks,
        "_load_job_params",
        lambda project_dir, job_id: dict(params),
    )
    monkeypatch.setattr(
        preview_chunks,
        "compute_chunk_fingerprints",
        lambda **_: [
            ChunkFingerprint(
                video_key=f"{key_prefix}-video-{index}",
                audio_key=f"{key_prefix}-audio-{index}",
                composition_uids=(),
                video_dirty=index in video_dirty_indices,
                audio_dirty=index in audio_dirty_indices,
                start_sec=float(index),
                end_sec=float(index + 1),
            )
            for index in range(chunk_count)
        ],
    )


class FakePreviewVideoRenderer:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def render(self, request) -> Path:
        self.calls.append(request["core_start_frame"] // 30)
        output = request["output_path"]
        output.write_bytes(b"new-video")
        return output


def _run_commands(commands) -> None:
    if commands.audio_cmd is not None and commands.audio_output is not None:
        commands.audio_output.write_bytes(b"new-audio")
    if commands.mux_cmd is not None:
        commands.playback_output.write_bytes(b"new-playback")


def test_worker_reuses_green_chunk_and_publishes_new_chunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    _seed_manifest(project_dir, store)
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 1.0, "end_sec": 2.0}], "media": "both"},
    )
    renderer = FakePreviewVideoRenderer()

    result = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-1",
        renderer=renderer,
        run_commands=_run_commands,
    )

    manifest = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    ).read_manifest()
    assert result["ok"] is True
    assert renderer.calls == [1]
    assert manifest is not None
    assert manifest.chunks[0].status == "green"
    assert manifest.chunks[1].status == "green"


def test_preview_worker_reports_structured_acceptance_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    _seed_manifest(project_dir, store)
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 1.0, "end_sec": 2.0}], "media": "both"},
    )

    result = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-diagnostics",
        renderer=FakePreviewVideoRenderer(),
        run_commands=_run_commands,
    )

    diagnostics = result["diagnostics"]
    assert diagnostics["counts"]["total_chunks"] == 2
    assert diagnostics["counts"]["selected_chunks"] == 1
    assert diagnostics["counts"]["skipped_green"] == 1
    assert diagnostics["selected_ranges"] == [
        {"start_sec": 1.0, "end_sec": 2.0},
    ]
    assert set(diagnostics["elapsed_sec"]) == {"video", "audio", "mux"}
    assert diagnostics["bytes_written"]["video"] > 0
    assert diagnostics["bytes_written"]["audio"] > 0
    assert diagnostics["bytes_written"]["mux"] > 0
    assert diagnostics["cache"]["hits"] >= 1
    assert diagnostics["cache"]["misses"] >= 1
    assert diagnostics["evictions"]["removed_files"] >= 0
    assert diagnostics["graph_changed"] is False
    assert diagnostics["partial"] is False


def test_one_remotion_edit_updates_only_its_preview_zone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path, duration_sec=4.0)
    _seed_manifest(project_dir, store, duration_sec=4.0)
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 0.0, "end_sec": 4.0}], "media": "both"},
        chunk_count=4,
        video_dirty_indices={0, 1, 2, 3},
        audio_dirty_indices={0, 1, 2, 3},
    )
    preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-remotion-initial",
        renderer=FakePreviewVideoRenderer(),
        run_commands=_run_commands,
    )

    store.append(
        AddRemotionCompositionOp(
            author="user",
            entry_point="src/index.ts",
            composition_id="Title",
            position_sec=2.2,
            duration_sec=0.4,
        )
    )
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 2.0, "end_sec": 3.0}], "media": "both"},
        chunk_count=4,
        video_dirty_indices={2},
        audio_dirty_indices=set(),
    )

    def fake_slice_and_emit(**kwargs):
        path = kwargs["temp_dir"] / "remotion-acceptance.mlt"
        path.write_text("<mlt/>", encoding="utf-8")
        return kwargs["timeline"], path, []

    monkeypatch.setattr(preview_chunks, "_slice_and_emit", fake_slice_and_emit)
    started = threading.Event()
    release = threading.Event()

    class BlockingRenderer(FakePreviewVideoRenderer):
        def render(self, request) -> Path:
            started.set()
            assert release.wait(timeout=5)
            return super().render(request)

    result_box: dict[str, dict] = {}

    def run() -> None:
        result_box["result"] = preview_chunks.render_preview_chunks(
            project_id="project",
            project_dir=project_dir,
            job_id="job-remotion-edit",
            renderer=BlockingRenderer(),
            run_commands=_run_commands,
        )

    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(timeout=5)
    cache = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    )
    while True:
        manifest = cache.read_manifest()
        assert manifest is not None
        if manifest.chunks[2].status in {"yellow", "red"}:
            break
        time.sleep(0.01)
    assert manifest.chunks[0].status == "green"
    assert manifest.chunks[1].status == "green"
    assert manifest.chunks[3].status == "green"
    release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert result_box["result"]["ok"] is True
    assert cache.read_manifest().chunks[2].status == "green"


def test_audio_gain_does_not_flush_video(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    _seed_manifest(project_dir, store)
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 0.0, "end_sec": 2.0}], "media": "both"},
        video_dirty_indices={0, 1},
        audio_dirty_indices={0, 1},
    )
    first = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-audio-initial",
        renderer=FakePreviewVideoRenderer(),
        run_commands=_run_commands,
    )
    before = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    ).read_manifest()
    assert before is not None
    before_video_ids = [
        chunk.video.current.artifact_id for chunk in before.chunks
    ]
    before_audio_ids = [
        chunk.audio.current.artifact_id for chunk in before.chunks
    ]
    assert first["ok"] is True

    clip_id = store.load_all()[0].clip_id
    store.append(SetAudioGainOp(author="user", clip_id=clip_id, gain_db=-6.0))
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 0.0, "end_sec": 1.0}], "media": "audio"},
        video_dirty_indices=set(),
        audio_dirty_indices={0},
        key_prefix="audio-edit",
    )
    renderer = FakePreviewVideoRenderer()
    after = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-audio-edit",
        renderer=renderer,
        run_commands=_run_commands,
    )
    manifest = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    ).read_manifest()
    assert manifest is not None
    assert renderer.calls == []
    assert [
        chunk.video.current.artifact_id for chunk in manifest.chunks
    ] == before_video_ids
    assert [
        chunk.audio.current.artifact_id for chunk in manifest.chunks
    ] != before_audio_ids
    assert after["diagnostics"]["bytes_written"]["video"] == 0


def test_worker_reuses_all_green_chunks_when_graph_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    _seed_manifest(project_dir, store)
    monkeypatch.setattr(
        preview_chunks,
        "_load_job_params",
        lambda project_dir, job_id: {
            "ranges": [{"start_sec": 1.0, "end_sec": 2.0}],
            "media": "both",
        },
    )
    renderer = FakePreviewVideoRenderer()

    result = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-unchanged",
        renderer=renderer,
        run_commands=_run_commands,
    )

    assert result["ok"] is True
    assert renderer.calls == []


def test_worker_preserves_old_artifact_as_yellow_fallback_during_bake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    _seed_manifest(project_dir, store)
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 1.0, "end_sec": 2.0}], "media": "both"},
    )

    started = threading.Event()
    release = threading.Event()

    class BlockingRenderer(FakePreviewVideoRenderer):
        def render(self, request) -> Path:
            self.calls.append(request["core_start_frame"] // 30)
            started.set()
            assert release.wait(timeout=5)
            output = request["output_path"]
            output.write_bytes(b"new-video")
            return output

    renderer = BlockingRenderer()
    result_box: dict[str, dict] = {}

    def run() -> None:
        result_box["result"] = preview_chunks.render_preview_chunks(
            project_id="project",
            project_dir=project_dir,
            job_id="job-2",
            renderer=renderer,
            run_commands=_run_commands,
        )

    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(timeout=5)
    cache = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    )
    while True:
        manifest = cache.read_manifest()
        assert manifest is not None
        if manifest.chunks[1].status == "yellow":
            break
        time.sleep(0.01)
    assert manifest.chunks[1].playback.fallback is not None
    assert manifest.chunks[1].playback.fallback.artifact_id == "old-playback"
    release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert result_box["result"]["ok"] is True
    assert cache.read_manifest().chunks[1].status == "green"


def test_worker_stops_publishing_when_graph_revision_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    _seed_manifest(project_dir, store)
    _patch_params(
        monkeypatch,
        {"ranges": [{"start_sec": 1.0, "end_sec": 2.0}], "media": "both"},
    )
    original_revision = store.graph_revision()

    class GraphChangingRenderer(FakePreviewVideoRenderer):
        def render(self, request) -> Path:
            store.set_project_meta_field("graph_revision", original_revision + 1)
            output = request["output_path"]
            output.write_bytes(b"stale-video")
            return output

    result = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-3",
        renderer=GraphChangingRenderer(),
        run_commands=_run_commands,
    )

    manifest = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    ).read_manifest()
    assert result["graph_changed"] is True
    assert manifest is not None
    assert manifest.graph_revision == original_revision


def test_worker_clears_own_job_id_after_unexpected_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    _seed_manifest(project_dir, store)
    monkeypatch.setattr(
        preview_chunks,
        "_load_job_params",
        lambda project_dir, job_id: {},
    )
    monkeypatch.setattr(
        preview_chunks,
        "compute_chunk_fingerprints",
        lambda **_: [
            ChunkFingerprint(
                video_key=f"video-{index}",
                audio_key=f"audio-{index}",
                composition_uids=(),
                video_dirty=True,
                audio_dirty=True,
                start_sec=float(index),
                end_sec=float(index + 1),
            )
            for index in range(2)
        ],
    )

    def fail_selection(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("selection failed")

    monkeypatch.setattr(preview_chunks, "select_dirty_windows", fail_selection)
    result = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-failed",
        renderer=FakePreviewVideoRenderer(),
        run_commands=_run_commands,
    )

    manifest = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    ).read_manifest()
    assert result["ok"] is False
    assert manifest is not None
    assert manifest.job_id is None


def _patch_fingerprints(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chunk_count: int,
    key_prefix: str = "adaptive",
) -> None:
    monkeypatch.setattr(
        preview_chunks,
        "compute_chunk_fingerprints",
        lambda **_: [
            ChunkFingerprint(
                video_key=f"{key_prefix}-video-{index}",
                audio_key=f"{key_prefix}-audio-{index}",
                composition_uids=(),
                video_dirty=True,
                audio_dirty=True,
                start_sec=float(index),
                end_sec=float(index + 1),
            )
            for index in range(chunk_count)
        ],
    )


def test_chunk_size_adaptive_default_and_explicit_param() -> None:
    # 37-min/2211s at 30fps: round(66331/64)=1036 -> capped at 30s (900).
    assert preview_chunks._chunk_size(30, 1, {}, 66331) == 900
    assert preview_chunks._chunk_size(30, 1, {}, 66330) == 900
    # Short/empty timelines fall back to the 1s floor.
    assert preview_chunks._chunk_size(30, 1, {}, 0) == 30
    assert preview_chunks._chunk_size(30, 1, {}, 1920) == 30
    assert preview_chunks._chunk_size(30000, 1001, {}, 66331) == 900
    # Explicit param still wins.
    assert preview_chunks._chunk_size(30, 1, {"chunk_frames": 120}, 66331) == 120
    # Invalid explicit values fall back to the adaptive default (None).
    assert preview_chunks._chunk_size(30, 1, {"chunk_frames": 0}, 66331) is None
    assert preview_chunks._chunk_size(30, 1, {"chunk_frames": "x"}, 66331) is None


def test_preview_worker_uses_adaptive_chunk_size_on_long_timeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path, duration_sec=2211.0)
    monkeypatch.setattr(
        preview_chunks,
        "_load_job_params",
        lambda project_dir, job_id: {
            "ranges": [{"start_sec": 0.0, "end_sec": 2211.0}],
            "media": "both",
        },
    )
    # 2211s * 30fps = 66330 frames -> 900-frame chunks -> 74 windows.
    _patch_fingerprints(monkeypatch, chunk_count=74)
    renderer = FakePreviewVideoRenderer()

    result = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-adaptive",
        renderer=renderer,
        run_commands=_run_commands,
    )

    manifest = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    ).read_manifest()
    assert result["ok"] is True
    assert manifest is not None
    assert manifest.chunk_frames == 900
    assert len(manifest.chunks) == 74
    assert manifest.chunks[0].start_frame == 0
    assert manifest.chunks[0].end_frame == 900
    assert manifest.chunks[-1].end_frame == 66330
    assert result["diagnostics"]["counts"]["total_chunks"] == 74
    # Renderer records core_start_frame // 30: one call per 900-frame chunk.
    assert len(renderer.calls) == 74
    assert renderer.calls[1] == 30


def test_preview_worker_honors_explicit_chunk_frames_param(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir, store = _project(tmp_path)
    monkeypatch.setattr(
        preview_chunks,
        "_load_job_params",
        lambda project_dir, job_id: {
            "ranges": [{"start_sec": 0.0, "end_sec": 2.0}],
            "media": "both",
            "chunk_frames": 10,
        },
    )
    # Explicit 10-frame chunks win over the 1s (30-frame) adaptive default.
    _patch_fingerprints(monkeypatch, chunk_count=6)

    result = preview_chunks.render_preview_chunks(
        project_id="project",
        project_dir=project_dir,
        job_id="job-explicit",
        renderer=FakePreviewVideoRenderer(),
        run_commands=_run_commands,
    )

    manifest = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        min_free_bytes=0,
    ).read_manifest()
    assert result["ok"] is True
    assert manifest is not None
    assert manifest.chunk_frames == 10
    assert len(manifest.chunks) == 6
    assert [(c.start_frame, c.end_frame) for c in manifest.chunks[:2]] == [
        (0, 10),
        (10, 20),
    ]


def test_preview_chunks_cli_emits_one_worker_result_json(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    project_dir = tmp_path / ".open_edit"
    project_dir.mkdir(parents=True)
    EditGraphStore(project_dir / "edit_graph.db")
    job = RenderJob(
        job_id="preview-job",
        project_id="project-id",
        mode="preview-chunks",
        status="queued",
        created_at=1.0,
        updated_at=1.0,
        params={
            "ranges": [{"start_sec": 2.0, "end_sec": 4.0}],
            "media": "audio",
        },
    )
    service = RenderJobService()
    monkeypatch.setattr(service, "get", lambda path, job_id: job)
    monkeypatch.setattr(cli, "DEFAULT_RENDER_JOB_SERVICE", service, raising=False)
    monkeypatch.setattr(
        cli,
        "render_preview_chunks",
        lambda **kwargs: {
            "ok": True,
            "mode": "preview-chunks",
            "output_path": str(tmp_path / "manifest.json"),
            "manifest_path": str(tmp_path / "manifest.json"),
            "ready_chunks": 1,
        },
    )
    monkeypatch.chdir(tmp_path)

    exit_code = cli.cmd_preview_chunks(
        argparse.Namespace(job_id="preview-job", json=True),
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["mode"] == "preview-chunks"
    assert payload["ready_chunks"] == 1
