"""Golden Remotion → materialize → emit / proxy path (fake Remotion CLI)."""
from __future__ import annotations

import shutil
import stat
import textwrap
from pathlib import Path

import pytest

from open_edit.ir.apply import derive_timeline
from open_edit.ir.types import AddRemotionCompositionOp, Project
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.materialize import materialize_remotion_compositions
from open_edit.render.orchestrator import render_project
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


_FAKE_REMOTION = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import argparse, json, os, pathlib, shutil
    p = argparse.ArgumentParser()
    p.add_argument("--project-root")
    p.add_argument("--entry-point")
    p.add_argument("--composition-id")
    p.add_argument("--props-file")
    p.add_argument("--output")
    p.add_argument("--width")
    p.add_argument("--height")
    p.add_argument("--fps")
    p.add_argument("--codec")
    p.add_argument("--concurrency")
    p.add_argument("--pixel-format")
    p.add_argument("--image-format")
    p.add_argument("--prores-profile")
    args = p.parse_args()
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    media = os.environ.get("OPEN_EDIT_REMOTION_FAKE_MEDIA", "")
    if media and pathlib.Path(media).is_file():
        shutil.copy2(media, out)
    else:
        out.write_bytes(b"\\x00\\x00\\x00\\x18ftypmp42" + b"\\x00" * 64)
    print(json.dumps({"ok": True, "output_path": str(out),
                      "width": int(args.width), "height": int(args.height),
                      "fps": float(args.fps)}))
    """
)

_FAKE_FAIL = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import sys
    print("boom", file=sys.stderr)
    sys.exit(1)
    """
)


@pytest.fixture
def remotion_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "proj"
    (project / ".open_edit").mkdir(parents=True)
    remotion = project / ".open_edit" / "remotion"
    (remotion / "src").mkdir(parents=True)
    (remotion / "src" / "index.ts").write_text("export {};\n")
    EditGraphStore(project / ".open_edit" / "edit_graph.db")
    fake = tmp_path / "fake_remotion.py"
    fake.write_text(_FAKE_REMOTION)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("OPEN_EDIT_REMOTION_BIN", str(fake))
    # A real, ffprobe-parseable mp4 (with audio) is copied as the fake
    # remotion output so the materialize ingest step can probe it.
    media = Path(__file__).resolve().parents[1] / "testdata" / "video_with_audio.mp4"
    monkeypatch.setenv("OPEN_EDIT_REMOTION_FAKE_MEDIA", str(media))
    return project


def test_remotion_materialize_emit_includes_producer(remotion_project: Path) -> None:
    """Golden: TitleCard op → CAS clip → MLT producer resource."""
    store = EditGraphStore(remotion_project / ".open_edit" / "edit_graph.db")
    op = AddRemotionCompositionOp(
        author="ai",
        entry_point="src/index.ts",
        composition_id="TitleCard",
        props={"titleText": "Hello"},
        position_sec=0.0,
        duration_sec=2.0,
        track_id="video_graphics",
    )
    store.append(op)
    project = Project(
        name="golden",
        workdir=remotion_project,
        edit_graph=store.load_all(),
    )
    timeline = derive_timeline(project)
    updated = materialize_remotion_compositions(
        timeline, remotion_project, mode="proxy",
    )
    asset_hash = updated.remotion_compositions[0].asset_hash
    assert asset_hash
    asset_path = AssetStore(remotion_project / ".open_edit" / "assets").path(asset_hash)
    assert asset_path is not None

    xml = emit_timeline(
        updated,
        EmitterConfig(profile={"width": 1280, "height": 720, "fps": 15}),
        asset_paths={asset_hash: str(asset_path)},
    )
    assert asset_hash in xml or str(asset_path) in xml
    assert "video_graphics" in xml or "producer" in xml.lower()


@pytest.mark.skipif(shutil.which("melt") is None, reason="melt not installed")
def test_remotion_proxy_render_via_orchestrator(remotion_project: Path) -> None:
    """Full proxy path: Remotion materialize then melt."""
    store = EditGraphStore(remotion_project / ".open_edit" / "edit_graph.db")
    store.append(AddRemotionCompositionOp(
        author="ai",
        entry_point="src/index.ts",
        composition_id="TitleCard",
        props={"titleText": "Proxy"},
        position_sec=0.0,
        duration_sec=1.5,
    ))
    result = render_project(
        project_id="remotion-golden",
        project_dir=remotion_project,
        workdir=remotion_project / "renders",
        mode="proxy",
        profile_name="480p30",
        force=True,
    )
    assert result.ok, f"render failed: {result.error}"
    assert Path(result.output_path).exists()
    assert Path(result.output_path).stat().st_size > 0


def test_orchestrator_strips_remotion_clips_for_melt() -> None:
    from open_edit.ir.types import Clip, RemotionComposition, Timeline, Track
    from open_edit.render.timeline_plan import timeline_for_melt

    rem = RemotionComposition(
        id="r1",
        entry_point="src/index.ts",
        composition_id="TalkIntro",
        position_sec=0.0,
        duration_sec=3.0,
        clip_id="gfx1",
        asset_hash="hashgfx",
    )
    talk = Clip(
        clip_id="talk1",
        asset_hash="hashtalk",
        track_id="v1",
        track_kind="video",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=5.0,
    )
    gfx = Clip(
        clip_id="gfx1",
        asset_hash="hashgfx",
        track_id="video_graphics",
        track_kind="video",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=3.0,
    )
    tl = Timeline(
        duration_sec=5.0,
        tracks=[
            Track(track_id="v1", kind="video", clips=[talk]),
            Track(track_id="video_graphics", kind="video", clips=[gfx]),
        ],
        remotion_compositions=[rem],
    )
    stripped = timeline_for_melt(tl)
    assert [t.track_id for t in stripped.tracks] == ["v1"]
    v1 = next(t for t in stripped.tracks if t.track_id == "v1")
    assert len(v1.clips) == 1
    assert stripped.remotion_compositions[0].composition_id == "TalkIntro"


def test_orchestrator_fails_hard_on_remotion_error(
    remotion_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Materialize failure must fail the render (no silent omission)."""
    fail = tmp_path / "fake_fail.py"
    fail.write_text(_FAKE_FAIL)
    fail.chmod(fail.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("OPEN_EDIT_REMOTION_BIN", str(fail))
    monkeypatch.setattr(
        "open_edit.render.orchestrator.shutil.which",
        lambda name: "/usr/bin/melt" if name == "melt" else shutil.which(name),
    )

    # Avoid actually invoking melt: fail during materialize first.
    store = EditGraphStore(remotion_project / ".open_edit" / "edit_graph.db")
    store.append(AddRemotionCompositionOp(
        author="ai",
        entry_point="src/index.ts",
        composition_id="Broken",
        position_sec=0.0,
        duration_sec=1.0,
    ))
    result = render_project(
        project_id="remotion-fail",
        project_dir=remotion_project,
        workdir=remotion_project / "renders",
        mode="proxy",
        force=True,
    )
    assert result.ok is False
    assert result.error
    assert "remotion" in result.error.lower() or "materialize" in result.error.lower()
