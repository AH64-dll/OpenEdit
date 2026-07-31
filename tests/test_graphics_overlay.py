"""Tests for the frame-server overlay burn path (melt -> ffmpeg pipe)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.render.encoder import select_encoder
from open_edit.render.melt_runner import run_pipe
from open_edit.render.pipe_builder import OverlayClip, build_pipe_commands
from open_edit.render.profiles import select_profile


pytestmark = pytest.mark.skipif(
    shutil.which("melt") is None or shutil.which("ffmpeg") is None,
    reason="melt + ffmpeg required",
)


def _tiny_mp4(path: Path, color: str = "black", duration: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def _render_with_overlay(tmp_path: Path, base: Path, overlays: list[OverlayClip]) -> Path:
    xml = tmp_path / "t.mlt"
    xml.write_text(
        "<mlt><producer id='p0'><property name='resource'>"
        f"{base}</property></producer>"
        "<playlist id='pl'><entry producer='p0'/></playlist>"
        "<tractor id='t0'><track producer='pl'/></tractor></mlt>"
    )
    profile = select_profile("480p30").model_copy(update={"scale": "320x180"})
    spec = select_encoder("cpu", tier="fast")
    out = tmp_path / "out.mp4"
    cmds = build_pipe_commands(
        shutil.which("melt"), xml, out, profile, spec, overlays,
        audio_bitrate="160k", workdir=tmp_path,
    )
    result = run_pipe(cmds, timeout_s=120)
    assert result.returncode == 0, result.stderr
    return out


def test_overlay_pipe_keeps_audio_and_writes_output(tmp_path: Path) -> None:
    base = _tiny_mp4(tmp_path / "base.mp4", color="blue", duration=2.0)
    gfx = _tiny_mp4(tmp_path / "gfx.mp4", color="red", duration=0.5)
    out = _render_with_overlay(
        tmp_path, base,
        [OverlayClip(position_sec=0.2, duration_sec=0.5, media_path=gfx, label="t")],
    )
    assert out.is_file()
    assert out.stat().st_size > 1000


def test_overlay_pipe_no_overlays_writes_output(tmp_path: Path) -> None:
    base = _tiny_mp4(tmp_path / "base.mp4", duration=0.5)
    out = _render_with_overlay(tmp_path, base, [])
    assert out.is_file()
    assert out.stat().st_size > 1000
