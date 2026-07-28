"""Tests for the Remotion renderer wrapper (fake CLI; no Chromium)."""
from __future__ import annotations

import json
import stat
import textwrap
from pathlib import Path

import pytest

from open_edit.render.profiles import RenderProfile
from open_edit.render.remotion import (
    RemotionRenderError,
    composition_cache_key,
    render_composition,
    validate_entry_point,
)


_FAKE_REMOTION = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import argparse, json, pathlib, sys
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
    args = p.parse_args()
    props = json.loads(pathlib.Path(args.props_file).read_text())
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\\x00\\x00\\x00\\x18ftypmp42fake-remotion-output")
    print(json.dumps({
        "ok": True,
        "output_path": str(out),
        "width": int(args.width),
        "height": int(args.height),
        "fps": float(args.fps),
        "props_title": props.get("titleText"),
    }))
    """
)


@pytest.fixture
def remotion_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "proj"
    root = project / ".open_edit" / "remotion"
    (root / "src" / "compositions").mkdir(parents=True)
    (root / "src" / "index.ts").write_text("// entry\nexport const RemotionRoot = () => null;\n")
    (root / "src" / "compositions" / "TitleCard.tsx").write_text(
        "export const TitleCard = ({titleText}: {titleText: string}) => titleText;\n"
    )
    fake = tmp_path / "fake_remotion.py"
    fake.write_text(_FAKE_REMOTION)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("OPEN_EDIT_REMOTION_BIN", str(fake))
    return project


def test_validate_entry_point_rejects_escape(remotion_project: Path) -> None:
    with pytest.raises(RemotionRenderError, match="relative"):
        validate_entry_point(remotion_project, "../secret.tsx")
    with pytest.raises(RemotionRenderError, match="relative"):
        validate_entry_point(remotion_project, "/etc/passwd")


def test_validate_entry_point_ok(remotion_project: Path) -> None:
    path = validate_entry_point(remotion_project, "src/index.ts")
    assert path.name == "index.ts"


def test_render_composition_writes_props_file_and_output(
    remotion_project: Path, tmp_path: Path,
) -> None:
    out = tmp_path / "out.mp4"
    profile = RenderProfile(
        name="p", width=1280, height=720, frame_rate_num=15, frame_rate_den=1,
    )
    result = render_composition(
        remotion_project,
        entry_point="src/index.ts",
        composition_id="TitleCard",
        props={"titleText": "Hello"},
        output_path=out,
        profile=profile,
        timeout_s=30,
    )
    assert result.ok
    assert Path(result.output_path).is_file()
    assert result.content_hash
    props_path = out.with_suffix(".props.json")
    assert json.loads(props_path.read_text()) == {"titleText": "Hello"}


def test_cache_key_stable_for_same_inputs(remotion_project: Path) -> None:
    profile = RenderProfile(
        name="p", width=1280, height=720, frame_rate_num=15, frame_rate_den=1,
    )
    src = (remotion_project / ".open_edit" / "remotion" / "src" / "index.ts").read_text()
    a = composition_cache_key(
        entry_source=src, composition_id="TitleCard", props={"a": 1},
        profile=profile, alpha=False,
    )
    b = composition_cache_key(
        entry_source=src, composition_id="TitleCard", props={"a": 1},
        profile=profile, alpha=False,
    )
    c = composition_cache_key(
        entry_source=src, composition_id="TitleCard", props={"a": 2},
        profile=profile, alpha=False,
    )
    assert a == b
    assert a != c
