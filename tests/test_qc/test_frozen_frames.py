"""Tests for frozen-frame detection."""
import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.qc.frozen_frames import list_frozen_frames, FrozenFramesResult


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)


def _make_clip(tmp_path: Path, first_secs_static: float) -> Path:
    """Build a clip whose first ``first_secs_static`` are a static color and
    whose remainder is animated (testsrc2), all concat'd into one MP4."""
    out = tmp_path / "mixed.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s=320x240:r=10:d={first_secs_static}",
        "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=10",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out


def _make_animated_clip(tmp_path: Path) -> Path:
    """A fully animated testsrc2 clip — no frozen frames."""
    out = tmp_path / "animated.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out


def _make_static_clip(tmp_path: Path, duration: float) -> Path:
    """A fully static-color clip — frozen from t=0 to EOF."""
    out = tmp_path / "static.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", f"color=c=red:s=320x240:r=10:d={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out


def test_list_frozen_frames_on_animated_clip(tmp_path) -> None:
    """An animated clip should have no frozen frames."""
    clip = _make_animated_clip(tmp_path)
    result = list_frozen_frames(str(clip))
    assert result.ok is True
    assert result.spans == []


def test_list_frozen_frames_flags_solid_color_clip() -> None:
    """The testdata clip_a is a solid-color clip: every frame is identical,
    so freezedetect flags a frozen span from t=0 (the video ends while
    still frozen, so no freeze_end is emitted)."""
    result = list_frozen_frames(str(TESTDATA / "clip_a.mp4"))
    assert result.ok is True
    assert len(result.spans) == 1
    assert result.spans[0].start_sec == 0.0


def test_list_frozen_frames_detects_static_segment(tmp_path) -> None:
    """A 1.5s static color followed by animated content flags a frozen span."""
    clip = _make_clip(tmp_path, first_secs_static=1.5)
    result = list_frozen_frames(str(clip))
    assert result.ok is True
    assert len(result.spans) == 1
    span = result.spans[0]
    assert span.start_sec <= 0.5
    assert span.end_sec >= 1.0
    assert span.duration_sec >= 0.9


def test_list_frozen_frames_missing_file() -> None:
    result = list_frozen_frames("/nonexistent/file.mp4")
    assert result.ok is False
    assert "not found" in (result.error or "")


def test_list_frozen_frames_short_static_not_flagged(tmp_path) -> None:
    """A 0.5s static segment is below the 1.0s minimum and must not fail."""
    clip = _make_clip(tmp_path, first_secs_static=0.5)
    result = list_frozen_frames(str(clip), min_sec=1.0)
    assert result.ok is True
    assert result.spans == []


def test_parse_freezedetect_freeze_to_eof_extends_to_total_duration() -> None:
    """A freeze with no freeze_end must end at the probed video duration,
    not collapse to duration 0."""
    from open_edit.qc.frozen_frames import _parse_freezedetect

    spans = _parse_freezedetect("freeze_start: 1.0\n", total_duration=5.0)
    assert len(spans) == 1
    assert spans[0].start_sec == 1.0
    assert spans[0].end_sec == 5.0
    assert spans[0].duration_sec == 4.0


def test_list_frozen_frames_freeze_to_eof_extends_span(tmp_path) -> None:
    """A fully static clip ends while frozen (no freeze_end): the span
    must extend to the probed video duration."""
    clip = _make_static_clip(tmp_path, duration=3.0)
    result = list_frozen_frames(str(clip))
    assert result.ok is True
    assert len(result.spans) == 1
    span = result.spans[0]
    assert span.start_sec == 0.0
    assert span.end_sec > 2.0
    assert span.duration_sec > 2.0
