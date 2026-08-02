"""Tests for the Remotion renderer wrapper (fake CLI; no Chromium)."""
from __future__ import annotations

import json
import stat
import textwrap
from pathlib import Path

import pytest

from open_edit.render.profiles import RenderProfile
from open_edit.render.remotion import renderer as renderer_mod
from open_edit.render.remotion import (
    RemotionRenderError,
    composition_cache_key,
    render_composition,
    remotion_profile_for_mode,
    validate_entry_point,
)


_FAKE_REMOTION = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import argparse, json, os, pathlib, sys
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
    capture = os.environ.get("OPEN_EDIT_CAPTURE_ARGS")
    if capture:
        pathlib.Path(capture).write_text(json.dumps(sys.argv[1:]))
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


def test_render_composition_stages_file_url_asset_in_public(
    remotion_project: Path, tmp_path: Path,
) -> None:
    source = remotion_project / "popup-source.png"
    source.write_bytes(b"popup-image")
    public = remotion_project / ".open_edit" / "remotion" / "public"

    render_composition(
        remotion_project,
        entry_point="src/index.ts",
        composition_id="FocusPopup",
        props={"imageSrc": source.as_uri()},
        output_path=tmp_path / "focus-popup.mp4",
        profile=RenderProfile(
            name="p", width=1280, height=720, frame_rate_num=15, frame_rate_den=1,
        ),
        timeout_s=30,
    )

    assert (public / source.name).read_bytes() == source.read_bytes()


def test_alpha_render_requests_transparent_prores_settings(
    remotion_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_args = tmp_path / "remotion-args.json"
    source = remotion_project / "image.png"
    source.write_bytes(b"image")
    monkeypatch.setenv("OPEN_EDIT_CAPTURE_ARGS", str(captured_args))
    profile = remotion_profile_for_mode("proxy", alpha=True, alpha_mode="prores")
    assert profile.vcodec == "prores_ks"

    render_composition(
        remotion_project,
        entry_point="src/index.ts",
        composition_id="FocusPopup",
        props={"imageSrc": source.as_uri()},
        output_path=tmp_path / "focus-popup.mov",
        profile=profile,
        timeout_s=30,
        alpha=True,
    )

    args = json.loads(captured_args.read_text())
    assert args[args.index("--codec") + 1] == "prores"
    pixel_format_index = args.index("--pixel-format")
    assert args[pixel_format_index + 1] == "yuva444p10le"
    image_format_index = args.index("--image-format")
    assert args[image_format_index + 1] == "png"
    prores_profile_index = args.index("--prores-profile")
    assert args[prores_profile_index + 1] == "4444"


def test_alpha_auto_uses_vp8_only_after_capability_probe(
    remotion_project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(renderer_mod, "probe_alpha_capability", lambda: True)
    profile = remotion_profile_for_mode(
        "proxy", alpha=True, alpha_mode="auto",
    )
    assert profile.vcodec == "libvpx"

    monkeypatch.setattr(renderer_mod, "probe_alpha_capability", lambda: False)
    fallback = remotion_profile_for_mode(
        "proxy", alpha=True, alpha_mode="auto",
    )
    assert fallback.vcodec == "prores_ks"


def test_alpha_capability_probe_falls_back_without_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_mod.probe_alpha_capability.cache_clear()
    monkeypatch.setattr(renderer_mod.shutil, "which", lambda _: None)
    assert renderer_mod.probe_alpha_capability() is False
    renderer_mod.probe_alpha_capability.cache_clear()


def test_cache_key_stable_for_same_inputs(remotion_project: Path) -> None:
    profile = RenderProfile(
        name="p", width=1280, height=720, frame_rate_num=15, frame_rate_den=1,
    )
    src = (remotion_project / ".open_edit" / "remotion" / "src" / "index.ts").read_text()
    a = composition_cache_key(
        composition_source=src, composition_id="TitleCard", props={"a": 1},
        profile=profile, alpha=False, duration_sec=3.0,
    )
    b = composition_cache_key(
        composition_source=src, composition_id="TitleCard", props={"a": 1},
        profile=profile, alpha=False, duration_sec=3.0,
    )
    c = composition_cache_key(
        composition_source=src, composition_id="TitleCard", props={"a": 2},
        profile=profile, alpha=False, duration_sec=3.0,
    )
    assert a == b
    assert a != c


def test_cache_key_changes_when_referenced_local_file_changes(
    remotion_project: Path,
) -> None:
    source = remotion_project / "source.png"
    source.write_bytes(b"first")
    profile = RenderProfile(
        name="p", width=1280, height=720, frame_rate_num=15, frame_rate_den=1,
    )
    kwargs = {
        "composition_source": 'const image = staticFile("asset.svg");',
        "composition_id": "FocusPopup",
        "props": {"imageSrc": source.as_uri()},
        "profile": profile,
        "alpha": True,
        "duration_sec": 1.0,
        "project_path": remotion_project,
    }
    first = composition_cache_key(**kwargs)
    source.write_bytes(b"second")
    second = composition_cache_key(**kwargs)
    assert first != second

    public = remotion_project / ".open_edit" / "remotion" / "public"
    public.mkdir(parents=True)
    asset = public / "asset.svg"
    asset.write_bytes(b"<svg>one</svg>")
    first_public = composition_cache_key(**kwargs)
    asset.write_bytes(b"<svg>two</svg>")
    second_public = composition_cache_key(**kwargs)
    assert first_public != second_public
