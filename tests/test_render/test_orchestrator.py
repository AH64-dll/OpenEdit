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
