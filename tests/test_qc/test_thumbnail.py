"""Tests for thumbnail extraction."""
import shutil
from pathlib import Path

import pytest

from open_edit.qc.thumbnail import get_thumbnail, ThumbnailResult


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)


def test_get_thumbnail_extracts_frame(tmp_path: Path) -> None:
    output = tmp_path / "thumb.jpg"
    result = get_thumbnail(str(TESTDATA / "clip_a.mp4"), 0.5, str(output))
    assert isinstance(result, ThumbnailResult)
    if result.ok:
        assert output.exists()
        assert result.width > 0
        assert result.height > 0


def test_get_thumbnail_missing_file(tmp_path: Path) -> None:
    result = get_thumbnail("/nonexistent.mp4", 0.5, str(tmp_path / "thumb.jpg"))
    assert result.ok is False
