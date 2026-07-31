"""Tests for stream-level QC probing."""
import shutil
from pathlib import Path

import pytest

from open_edit.qc.streams import probe_streams, StreamsInfo


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


pytestmark = pytest.mark.skipif(
    not shutil.which("ffprobe"), reason="ffprobe not installed"
)


def test_probe_streams_on_synthetic_clip() -> None:
    """The testdata clips are 2s video-only MP4s."""
    info = probe_streams(str(TESTDATA / "clip_a.mp4"))
    assert isinstance(info, StreamsInfo)
    assert info.ok is True
    assert info.video_streams == 1
    assert info.audio_streams == 0
    assert info.video_duration_s is not None
    assert info.container_duration_s == pytest.approx(2.0, abs=0.05)
    assert "video" in info.codec_types


def test_probe_streams_missing_file() -> None:
    info = probe_streams("/nonexistent/file.mp4")
    assert info.ok is False
    assert "not found" in (info.error or "")
    assert info.video_streams == 0


def test_probe_streams_non_media_file() -> None:
    info = probe_streams(str(__file__))
    assert info.ok is False
    assert info.error
