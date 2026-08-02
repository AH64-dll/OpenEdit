from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

import pytest

from open_edit import cli
from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import AddClipOp
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


def _project(tmp_path: Path) -> tuple[Path, EditGraphStore]:
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
            out_point_sec=2.0,
        )
    )
    return project_dir, store


def _seed_manifest(
    project_dir: Path,
    store: EditGraphStore,
) -> PreviewChunkCache:
    cache = PreviewChunkCache(
        project_dir / ".open_edit" / "preview_chunks",
        max_bytes=1_000_000,
        max_age_sec=None,
        min_free_bytes=0,
    )
    graph_hash = compute_edit_graph_hash(store.load_all())
    chunks: list[PreviewChunk] = []
    for index in range(2):
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
            duration_frames=60,
            duration_sec=2.0,
            fps_num=30,
            fps_den=1,
            chunk_frames=30,
            profile={"name": "preview_chunk"},
            updated_at=time.time(),
            chunks=chunks,
        )
    )
    return cache


def _patch_params(monkeypatch: pytest.MonkeyPatch, params: dict) -> None:
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
                video_key=f"new-video-{index}",
                audio_key=f"new-audio-{index}",
                composition_uids=(),
                video_dirty=index == 1,
                audio_dirty=index == 1,
                start_sec=float(index),
                end_sec=float(index + 1),
            )
            for index in range(2)
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
