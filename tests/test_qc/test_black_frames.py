"""Tests for black-frame detection."""
import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.qc.black_frames import list_black_frames, BlackFramesResult
import open_edit.qc.black_frames as black_frames_mod


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


pytestmark = pytest.mark.skipif(
    not _has_ffmpeg(), reason="ffmpeg not installed"
)


def test_list_black_frames_on_synthetic_clip() -> None:
    """A synthetic 2s color clip should have no black frames."""
    result = list_black_frames(str(TESTDATA / "clip_a.mp4"))
    assert result.ok is True
    assert isinstance(result.spans, list)


def test_list_black_frames_invalid_range() -> None:
    result = list_black_frames(str(TESTDATA / "clip_a.mp4"), in_sec=5.0, out_sec=2.0)
    assert result.ok is False
    assert "invalid range" in result.error


def test_list_black_frames_missing_file() -> None:
    result = list_black_frames("/nonexistent/file.mp4")
    assert result.ok is False
    assert "not found" in result.error


def test_list_black_frames_uses_pixel_threshold(tmp_path, monkeypatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"source")
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(black_frames_mod.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(black_frames_mod.subprocess, "run", fake_run)

    result = list_black_frames(str(source))

    assert result.ok is True
    vf = seen[0][seen[0].index("-vf") + 1]
    assert "pix_th=0.1" in vf
    assert "pic_th=0.98" in vf


def test_list_black_frames_timeout_is_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not decoded")
    monkeypatch.setattr(black_frames_mod.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(
        black_frames_mod.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(kwargs["timeout"], kwargs["timeout"])
        ),
    )

    result = list_black_frames(str(source), timeout_s=7.0)

    assert result.ok is False
    assert "timed out" in (result.error or "")
