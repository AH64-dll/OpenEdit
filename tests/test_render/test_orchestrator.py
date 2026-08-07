"""Tests for the render orchestrator (melt + cache + QC)."""
import shutil
import stat
import textwrap
from pathlib import Path

import pytest

from open_edit.render.orchestrator import (
    RenderResult,
    render_project,
)


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


def _has_melt() -> bool:
    return shutil.which("melt") is not None


pytestmark = pytest.mark.skipif(
    not _has_melt(), reason="melt not installed"
)


def test_render_project_returns_error_when_no_ops(tmp_path: Path) -> None:
    result = render_project(
        project_id="nonexistent",
        project_dir=tmp_path,
        workdir=tmp_path,
    )
    assert result.ok is False
    assert "no ops" in (result.error or "").lower() or "empty" in (result.error or "").lower()


def test_render_result_has_required_fields() -> None:
    """RenderResult is a Pydantic model with the spec's fields."""
    r = RenderResult(ok=True, output_path="/tmp/out.mp4", mode="proxy", duration_sec=1.0, elapsed_sec=0.5)
    assert r.ok is True
    assert r.output_path == "/tmp/out.mp4"
    assert r.mode == "proxy"
    assert r.duration_sec == 1.0
    assert r.elapsed_sec == 0.5


def test_final_render_rejects_non_final_emission_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="final emission"):
        render_project(
            "project",
            tmp_path,
            tmp_path / "renders",
            mode="final",
            emission_profile="preview-chunk",
        )


def _make_project(tmp_path: Path, *, name: str = "proj"):
    """Ingest one fixture clip and apply one AddClipOp (mirrors test_e2e_render)."""
    from pathlib import Path

    from open_edit.ir.types import AddClipOp, Project
    from open_edit.storage.assets import AssetStore
    from open_edit.storage.edit_graph import EditGraphStore

    TESTDATA = Path(__file__).resolve().parents[1] / "testdata" / "raw_videos"
    project_dir = tmp_path / name
    open_edit_dir = project_dir / ".open_edit"
    open_edit_dir.mkdir(parents=True, exist_ok=True)
    asset_store = AssetStore(open_edit_dir / "assets")
    assets = asset_store.ingest_paths([str(TESTDATA / "clip_a.mp4")])
    graph = EditGraphStore(open_edit_dir / "edit_graph.db")
    project = Project(name=name, assets={a.asset_hash: a for a in assets})
    op = AddClipOp(author="user", asset_hash=assets[0].asset_hash,
                   track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=1.0)
    graph.append(op)
    project.edit_graph.append(op)
    return project_dir


def test_render_project_uses_profile_scoped_cache_key(tmp_path: Path, monkeypatch) -> None:
    from open_edit.render import orchestrator
    from open_edit.render.cache import RenderCache
    from open_edit.render.melt_runner import PipeResult

    cache_keys: list[str] = []

    def fake_get(self, key: str, ext: str = "mp4"):
        cache_keys.append(key)
        return None

    def fake_put(self, key: str, source_path):
        from pathlib import Path
        return Path(source_path)

    monkeypatch.setattr(RenderCache, "get", fake_get)
    monkeypatch.setattr(RenderCache, "put", fake_put)

    def fake_run_pipe(cmds, *, timeout_s):
        out = cmds.ffmpeg_cmd[-1]
        from pathlib import Path
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(orchestrator.shutil, "which",
                        lambda name: "/usr/bin/melt" if name == "melt" else None)

    project_dir = _make_project(tmp_path)
    result = orchestrator.render_project(
        "proj", project_dir, tmp_path / "work", mode="final",
        quality="high", encoder_backend="cpu",
    )
    assert result.ok is True, result.error
    assert cache_keys and all("high" in k and "cpu" in k for k in cache_keys)
    assert result.diagnostics["product"] == {
        "kind": "final_export",
        "mode": "final",
        "label": "Final export",
        "width": 1920,
        "height": 1080,
        "interactive": False,
        "source_proxy": False,
        "timeline_preview_chunk": False,
    }
    assert result.diagnostics["legacy_stage_aliases"] == {
        "melt": "melt_video",
        "ffmpeg": "ffmpeg_encode",
        "audio": "melt_audio",
    }
    assert result.diagnostics["stages"]["remotion_materialize"]["elapsed_sec"] >= 0
    assert result.diagnostics["stages"]["ffmpeg"]["bytes"] == 3
    assert result.diagnostics["stages"]["melt"] == result.diagnostics["stages"]["melt_video"]
    assert result.diagnostics["stages"]["ffmpeg"] == result.diagnostics["stages"]["ffmpeg_encode"]
    assert result.diagnostics["stages"]["audio"] == result.diagnostics["stages"]["melt_audio"]


def test_proxy_edit_emission_is_diagnosed_and_cache_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.kernel import asset_proxy_jobs
    from open_edit.render import orchestrator
    from open_edit.render.cache import RenderCache
    from open_edit.render.melt_runner import PipeResult

    cache_keys: list[str] = []

    monkeypatch.setattr(
        RenderCache,
        "get",
        lambda self, key, ext="mp4": cache_keys.append(key) or None,
    )
    monkeypatch.setattr(
        RenderCache,
        "put",
        lambda self, key, source_path: Path(source_path),
    )
    monkeypatch.setattr(
        asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE,
        "enqueue",
        lambda *args, **kwargs: object(),
    )

    def fake_run_pipe(cmds, *, timeout_s):
        output = Path(cmds.ffmpeg_cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(
        orchestrator.shutil,
        "which",
        lambda name: "/usr/bin/melt" if name == "melt" else None,
    )
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: False)

    project_dir = _make_project(tmp_path, name="proxy-edit")
    result = orchestrator.render_project(
        "proxy-edit",
        project_dir,
        tmp_path / "work-proxy-edit",
        mode="proxy",
        emission_profile="proxy-edit",
    )

    assert result.ok is True, result.error
    diagnostics = result.diagnostics
    assert diagnostics["emission_profile"] == "proxy-edit"
    assert diagnostics["source_media_policy"] == "proxy"
    assert diagnostics["source_proxy_profile_fingerprint"].startswith(
        "source_proxy_360_v1:"
    )
    assert "source_proxy_360_v1:" in diagnostics["cache_content_fingerprint"]
    assert cache_keys and "source_proxy_360_v1:" in cache_keys[0]


def test_final_render_passes_repair_budget_and_records_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.render import orchestrator
    from open_edit.render.melt_runner import PipeResult

    captured: dict[str, object] = {}

    def fake_run_pipe(cmds, *, timeout_s):
        output = Path(cmds.ffmpeg_cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    def fake_repair(input_path, output_path, baseline, **kwargs):
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "changed": False,
            "output_path": str(input_path),
            "protected_spans": [],
            "source_hashes": {},
        }

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(orchestrator, "repair_render_output", fake_repair)
    monkeypatch.setattr(
        orchestrator, "collect_source_baseline",
        lambda timeline, asset_paths, **kwargs: {
            "black_frames": [], "frozen_frames": [], "errors": [],
        },
    )
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: False)
    monkeypatch.setattr(
        orchestrator.shutil,
        "which",
        lambda name: "/usr/bin/melt" if name == "melt" else None,
    )

    project_dir = _make_project(tmp_path, name="final-repair-policy")
    result = orchestrator.render_project(
        "final-repair-policy",
        project_dir,
        tmp_path / "final-repair-work",
        mode="final",
    )

    assert result.ok is True, result.error
    kwargs = captured["kwargs"]
    assert kwargs["detector_timeout_s"] is not None
    assert result.diagnostics["repair_policy"]["emission_profile"] == "final"
    assert result.diagnostics["repair"]["changed"] is False
    assert result.diagnostics["repair"]["protected_spans"] == []


def test_preview_chunk_skips_whole_file_source_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.kernel import asset_proxy_jobs
    from open_edit.render import orchestrator
    from open_edit.render.cache import RenderCache
    from open_edit.render.melt_runner import PipeResult

    monkeypatch.setattr(
        asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE,
        "enqueue",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(RenderCache, "get", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        RenderCache, "put", lambda self, key, source_path: Path(source_path),
    )
    monkeypatch.setattr(
        orchestrator,
        "collect_source_baseline",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("preview chunks do not collect source repair baselines")
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "repair_render_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("preview chunks do not run whole-file repair")
        ),
    )
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: False)
    monkeypatch.setattr(
        orchestrator.shutil,
        "which",
        lambda name: "/usr/bin/melt" if name == "melt" else None,
    )

    def fake_run_pipe(cmds, *, timeout_s):
        output = Path(cmds.ffmpeg_cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    project_dir = _make_project(tmp_path, name="preview-chunk")
    result = orchestrator.render_project(
        "preview-chunk",
        project_dir,
        tmp_path / "preview-chunk-work",
        mode="proxy",
        emission_profile="preview-chunk",
    )

    assert result.ok is True, result.error
    assert result.diagnostics["repair_policy"]["enabled"] is False
    assert result.diagnostics["stages"]["source_repair"]["status"] == "skipped"


def test_render_project_hwaccel_retry(tmp_path: Path, monkeypatch) -> None:
    from open_edit.render import orchestrator
    from open_edit.render.melt_runner import PipeResult

    attempts: list[list[str]] = []

    def fake_run_pipe(cmds, *, timeout_s):
        attempts.append(cmds.melt_video_cmd)
        from pathlib import Path
        if len(attempts) == 1:
            return PipeResult(1, 1, 0, "melt: hwaccel exploded")
        Path(cmds.ffmpeg_cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmds.ffmpeg_cmd[-1]).write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(orchestrator.shutil, "which",
                        lambda name: "/usr/bin/melt" if name == "melt" else None)
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: True)
    monkeypatch.setattr(orchestrator, "canonical_json_hash", lambda obj: "h1")

    project_dir = _make_project(tmp_path, name="proj2")
    result = orchestrator.render_project("proj2", project_dir, tmp_path / "work2",
                                         mode="proxy", encoder_backend="gpu")
    assert result.ok is True, result.error
    assert len(attempts) == 2  # first hwaccel attempt failed -> CPU retry


def test_deliverable_cache_hit_skips_remotion_materialize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.ir.types import AddRemotionCompositionOp
    from open_edit.storage.edit_graph import EditGraphStore

    fake = tmp_path / "fake_remotion.py"
    fake.write_text(textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import argparse, os, pathlib, shutil
        p = argparse.ArgumentParser()
        p.add_argument("--output")
        p.add_argument("--width")
        p.add_argument("--height")
        p.add_argument("--fps")
        p.add_argument("--project-root")
        p.add_argument("--entry-point")
        p.add_argument("--composition-id")
        p.add_argument("--props-file")
        p.add_argument("--codec")
        p.add_argument("--concurrency")
        p.add_argument("--pixel-format")
        p.add_argument("--image-format")
        p.add_argument("--prores-profile")
        args = p.parse_args()
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(os.environ["OPEN_EDIT_REMOTION_FAKE_MEDIA"], out)
        """
    ))
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("OPEN_EDIT_REMOTION_BIN", str(fake))
    monkeypatch.setenv(
        "OPEN_EDIT_REMOTION_FAKE_MEDIA",
        str(Path(__file__).resolve().parents[2] / "testdata" / "video_with_audio.mp4"),
    )

    project_dir = _make_project(tmp_path, name="remotion-cache-order")
    remotion_root = project_dir / ".open_edit" / "remotion"
    (remotion_root / "src").mkdir(parents=True)
    (remotion_root / "src" / "index.ts").write_text("export {};\n")
    store = EditGraphStore(project_dir / ".open_edit" / "edit_graph.db")
    store.append(AddRemotionCompositionOp(
        author="ai",
        entry_point="src/index.ts",
        composition_id="TitleCard",
        props={"titleText": "cache"},
        position_sec=0.0,
        duration_sec=1.0,
    ))

    from open_edit.render import orchestrator
    from open_edit.render.melt_runner import PipeResult

    monkeypatch.setattr(
        orchestrator.shutil,
        "which",
        lambda name: "/usr/bin/melt" if name == "melt" else None,
    )
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: False)
    monkeypatch.setattr(
        orchestrator,
        "repair_render_output",
        lambda *args, **kwargs: {"ok": True, "changed": False},
    )

    def fake_run_pipe(cmds, *, timeout_s):
        output = Path(cmds.ffmpeg_cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    first = orchestrator.render_project(
        "remotion-cache-order",
        project_dir,
        tmp_path / "renders",
        mode="proxy",
    )
    assert first.ok is True, first.error
    assert first.cache_hit is False

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Remotion materialize must not run on MP4 hit")

    monkeypatch.setattr(orchestrator, "materialize_remotion_compositions", fail_if_called)
    second = orchestrator.render_project(
        "remotion-cache-order",
        project_dir,
        tmp_path / "renders",
        mode="proxy",
    )

    assert second.ok is True, second.error
    assert second.cache_hit is True
    assert second.diagnostics["cache"]["hit"] is True
    assert second.diagnostics["stages"]["remotion_materialize"]["status"] == "skipped"
    assert second.diagnostics["stages"]["remotion_materialize"]["reason"] == (
        "deliverable_cache_hit"
    )


def test_render_diagnostics_include_canonical_stages_and_product(
    tmp_path: Path, monkeypatch,
) -> None:
    from open_edit.render import orchestrator
    from open_edit.render.melt_runner import PipeResult

    def fake_run_pipe(cmds, *, timeout_s):
        output_path = Path(cmds.ffmpeg_cmd[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"MP4")
        return PipeResult(
            0,
            0,
            0,
            "",
            audio_elapsed_sec=0.1,
            melt_elapsed_sec=0.2,
            ffmpeg_elapsed_sec=0.3,
        )

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: False)
    monkeypatch.setattr(
        orchestrator.shutil,
        "which",
        lambda name: "/usr/bin/melt" if name == "melt" else None,
    )
    monkeypatch.setattr(
        orchestrator,
        "repair_render_output",
        lambda *args, **kwargs: {"ok": True, "changed": False},
    )

    project_dir = _make_project(tmp_path, name="canonical-stages")
    result = orchestrator.render_project(
        "canonical-stages",
        project_dir,
        tmp_path / "work",
        mode="proxy",
    )

    assert result.ok is True, result.error
    assert result.diagnostics["product"]["kind"] == "review_artifact"
    assert result.diagnostics["product"]["width"] == 640
    assert set(result.diagnostics["stages"]) >= {
        "derive_timeline",
        "render_cache_lookup",
        "remotion_materialize",
        "build_render_plan",
        "emit_mlt",
        "melt_audio",
        "melt_video",
        "ffmpeg_encode",
        "source_repair",
        "qc",
    }
    assert result.diagnostics["stages"]["melt_audio"]["elapsed_sec"] == 0.1
    assert result.diagnostics["stages"]["melt_video"]["elapsed_sec"] == 0.2
    assert result.diagnostics["stages"]["ffmpeg_encode"]["elapsed_sec"] == 0.3
    assert result.diagnostics["legacy_stage_aliases"]["ffmpeg"] == "ffmpeg_encode"


def _seed_ready_proxy(
    project_dir: Path,
    asset_hash: str,
    proxy_bytes: bytes = b"derived source proxy bytes",
) -> str:
    """Store derived CAS bytes and link them as the asset's ready proxy."""
    from open_edit.render.source_proxy import DEFAULT_SOURCE_PROXY_PROFILE
    from open_edit.storage.assets import AssetStore

    store = AssetStore(project_dir / ".open_edit" / "assets")
    fake = project_dir / ".open_edit" / "tmp" / "fake-proxy.mp4"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_bytes(proxy_bytes)
    proxy_hash = store.store_derived(fake)
    store.update_proxy_metadata(
        asset_hash,
        proxy_hash=proxy_hash,
        profile=DEFAULT_SOURCE_PROXY_PROFILE.name,
        status="ready",
    )
    return proxy_hash


def _asset_hash(project_dir: Path) -> str:
    from open_edit.storage.edit_graph import EditGraphStore

    graph = EditGraphStore(project_dir / ".open_edit" / "edit_graph.db")
    for op in graph.load_all():
        if op.status == "applied":
            return op.asset_hash
    raise AssertionError("no applied ops")


def _proxy_render_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Shared monkeypatches for proxy-mode orchestrator renders."""
    from open_edit.kernel import asset_proxy_jobs
    from open_edit.render import orchestrator
    from open_edit.render.cache import RenderCache
    from open_edit.render.melt_runner import PipeResult

    enqueued: list[tuple] = []
    monkeypatch.setattr(
        asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE,
        "enqueue",
        lambda *args, **kwargs: enqueued.append((args, kwargs)) or object(),
    )
    monkeypatch.setattr(RenderCache, "get", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        RenderCache, "put", lambda self, key, source_path: Path(source_path),
    )
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: False)
    monkeypatch.setattr(
        orchestrator.shutil,
        "which",
        lambda name: "/usr/bin/melt" if name == "melt" else None,
    )

    def fake_run_pipe(cmds, *, timeout_s):
        output = Path(cmds.ffmpeg_cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)

    real_emit = orchestrator.emit_timeline
    captured: dict = {}

    def spy_emit(timeline, config=None, asset_paths=None, **kwargs):
        xml = real_emit(timeline, config, asset_paths=asset_paths, **kwargs)
        captured["xml"] = xml
        captured["asset_paths"] = dict(asset_paths or {})
        return xml

    monkeypatch.setattr(orchestrator, "emit_timeline", spy_emit)
    return captured, enqueued


def test_review_artifact_uses_ready_source_proxy_and_reports_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, enqueued = _proxy_render_harness(tmp_path, monkeypatch)
    project_dir = _make_project(tmp_path, name="proxy-use")
    asset_hash = _asset_hash(project_dir)
    proxy_hash = _seed_ready_proxy(project_dir, asset_hash)
    from open_edit.storage.assets import AssetStore

    store = AssetStore(project_dir / ".open_edit" / "assets")

    result = render_project(
        "proxy-use",
        project_dir,
        tmp_path / "proxy-use-work",
        mode="proxy",
    )

    assert result.ok is True, result.error
    diagnostics = result.diagnostics
    assert diagnostics["emission_profile"] == "review-artifact"
    assert diagnostics["source_media_policy"] == "proxy"
    assert diagnostics["source_proxy_hits"] == {asset_hash: proxy_hash}
    assert diagnostics["source_proxy_fallbacks"] == {}
    assert diagnostics["source_proxy_profile_fingerprint"].startswith(
        "source_proxy_360_v1:"
    )
    assert "source_proxy_360_v1:" in diagnostics["cache_content_fingerprint"]
    # The emitted MLT must point at the proxy CAS object, not the original.
    assert captured["asset_paths"][asset_hash] == str(
        store.path(proxy_hash)
    )
    assert captured["asset_paths"][asset_hash] != str(store.path(asset_hash))
    assert str(store.path(proxy_hash)) in captured["xml"]
    assert str(store.path(asset_hash)) not in captured["xml"]
    # No proxy was missing, so nothing was enqueued.
    assert enqueued == []


def test_review_artifact_missing_proxy_falls_back_and_queues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_edit.render.source_proxy import DEFAULT_SOURCE_PROXY_PROFILE
    from open_edit.storage.assets import AssetStore

    captured, enqueued = _proxy_render_harness(tmp_path, monkeypatch)
    project_dir = _make_project(tmp_path, name="proxy-fallback")
    asset_hash = _asset_hash(project_dir)
    store = AssetStore(project_dir / ".open_edit" / "assets")

    result = render_project(
        "proxy-fallback",
        project_dir,
        tmp_path / "proxy-fallback-work",
        mode="proxy",
    )

    assert result.ok is True, result.error
    diagnostics = result.diagnostics
    assert diagnostics["source_media_policy"] == "proxy"
    assert diagnostics["source_proxy_hits"] == {}
    # Safety: preview renders fall back to canonical bytes and queue the
    # proxy job instead of failing or corrupting.
    assert diagnostics["source_proxy_fallbacks"] == {asset_hash: "queued"}
    assert captured["asset_paths"][asset_hash] == str(store.path(asset_hash))
    assert str(store.path(asset_hash)) in captured["xml"]
    assert enqueued and enqueued[0][0][2] == asset_hash
    assert enqueued[0][1]["profile"] == DEFAULT_SOURCE_PROXY_PROFILE
