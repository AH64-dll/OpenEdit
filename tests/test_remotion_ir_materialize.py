"""IR + materialize tests for Remotion compositions."""
from __future__ import annotations

import json
import stat
import textwrap
import uuid
from pathlib import Path

import pytest

from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    AddRemotionCompositionOp,
    Project,
    RemoveRemotionCompositionOp,
    Timeline,
)
from open_edit.render.materialize import (
    RemotionMaterializeError,
    materialize_remotion_compositions,
)
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


@pytest.fixture
def project_with_remotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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


def test_apply_add_and_remove_remotion_composition() -> None:
    timeline = Timeline()
    op = AddRemotionCompositionOp(
        author="user",
        entry_point="src/index.ts",
        composition_id="TitleCard",
        props={"titleText": "Hi"},
        position_sec=1.0,
        duration_sec=3.0,
    )
    timeline = apply_operation(timeline, op)
    assert len(timeline.remotion_compositions) == 1
    assert timeline.remotion_compositions[0].composition_id == "TitleCard"
    timeline = apply_operation(
        timeline,
        RemoveRemotionCompositionOp(
            author="user",
            composition_uid=op.composition_uid,
        ),
    )
    assert timeline.remotion_compositions == []


def test_derive_timeline_includes_remotion_duration(project_with_remotion: Path) -> None:
    store = EditGraphStore(project_with_remotion / ".open_edit" / "edit_graph.db")
    op = AddRemotionCompositionOp(
        author="ai",
        entry_point="src/index.ts",
        composition_id="TitleCard",
        position_sec=2.0,
        duration_sec=4.0,
    )
    store.append(op)
    project = Project(
        name="proj",
        workdir=project_with_remotion,
        edit_graph=store.load_all(),
    )
    timeline = derive_timeline(project)
    assert timeline.duration_sec == pytest.approx(6.0)
    assert len(timeline.remotion_compositions) == 1


def test_materialize_injects_clip_and_caches(project_with_remotion: Path) -> None:
    store = EditGraphStore(project_with_remotion / ".open_edit" / "edit_graph.db")
    op = AddRemotionCompositionOp(
        author="ai",
        entry_point="src/index.ts",
        composition_id="TitleCard",
        props={"titleText": "Hello"},
        position_sec=0.0,
        duration_sec=2.5,
    )
    store.append(op)
    project = Project(
        name="proj",
        workdir=project_with_remotion,
        edit_graph=store.load_all(),
    )
    timeline = derive_timeline(project)
    updated = materialize_remotion_compositions(
        timeline, project_with_remotion, mode="proxy",
    )
    assert updated.remotion_compositions[0].asset_hash
    graphics = next(t for t in updated.tracks if t.track_id == "video_graphics")
    assert len(graphics.clips) == 1
    assert graphics.clips[0].asset_hash == updated.remotion_compositions[0].asset_hash
    assert graphics.clips[0].out_point_sec == pytest.approx(2.5)

    # Second call is a cache hit (same asset hash; fake still ok).
    again = materialize_remotion_compositions(
        timeline, project_with_remotion, mode="proxy",
    )
    assert again.remotion_compositions[0].asset_hash == updated.remotion_compositions[0].asset_hash

    # Cache is the RenderCache under the materialize: key prefix.
    cache_dir = project_with_remotion / ".open_edit" / "remotion" / "out" / "cache"
    cached = [p.name for p in cache_dir.glob("materialize:*")]
    assert len(cached) == 1
    assert cached[0].endswith(".mp4")
    assert not (project_with_remotion / ".open_edit" / "remotion" / "out" / "materialize_cache.json").exists()


def test_materialize_fails_hard_on_bad_entry(project_with_remotion: Path) -> None:
    timeline = Timeline()
    timeline = apply_operation(
        timeline,
        AddRemotionCompositionOp(
            author="ai",
            entry_point="src/missing.ts",
            composition_id="X",
            position_sec=0,
            duration_sec=1,
        ),
    )
    with pytest.raises(RemotionMaterializeError):
        materialize_remotion_compositions(timeline, project_with_remotion, mode="proxy")


def test_append_rejects_path_escape(project_with_remotion: Path) -> None:
    store = EditGraphStore(project_with_remotion / ".open_edit" / "edit_graph.db")
    from open_edit.ir.validate import OpValidationError

    with pytest.raises(Exception):
        store.append(AddRemotionCompositionOp(
            author="ai",
            entry_point="../etc/passwd",
            composition_id="X",
            position_sec=0,
            duration_sec=1,
        ))
