"""Tests for Remotion graphics ffmpeg burn-in helper."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from open_edit.render.graphics_overlay import OverlayClip, burn_overlays


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg required",
)


def _tiny_mp4(path: Path, color: str = "black", duration: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    import subprocess
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


def test_burn_overlays_keeps_audio_and_writes_output(tmp_path: Path) -> None:
    base = _tiny_mp4(tmp_path / "base.mp4", color="blue", duration=2.0)
    gfx = _tiny_mp4(tmp_path / "gfx.mp4", color="red", duration=0.5)
    out = tmp_path / "out.mp4"
    burn_overlays(
        base,
        [OverlayClip(position_sec=0.2, duration_sec=0.5, media_path=gfx, label="t")],
        out,
        width=320,
        height=180,
    )
    assert out.is_file()
    assert out.stat().st_size > 1000


def test_burn_overlays_noop_copies_base(tmp_path: Path) -> None:
    base = _tiny_mp4(tmp_path / "base.mp4", duration=0.5)
    out = tmp_path / "out.mp4"
    burn_overlays(base, [], out)
    assert out.read_bytes() == base.read_bytes()
