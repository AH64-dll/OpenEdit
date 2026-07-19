"""Tests for black-frame detection."""
import shutil
from pathlib import Path

import pytest

from open_edit.qc.black_frames import list_black_frames, BlackFramesResult


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
