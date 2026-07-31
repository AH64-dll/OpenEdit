"""Tests for the QC gate (documented 6 checks + pipeline diagnostics)."""
import shutil
from pathlib import Path

import pytest

from open_edit.qc.gate import run_qc_gate, QCReport


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)

ALL_CHECK_NAMES = [
    "render_completed", "proxy_render",
    "streams", "duration", "audio_sync",
    "black_frames", "frozen_frames",
    "silence", "overlays_burned", "thumbnail",
]


def test_run_qc_gate_produces_report() -> None:
    report = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
    )
    assert isinstance(report, QCReport)
    assert len(report.checks) == 10


def test_run_qc_gate_check_names() -> None:
    report = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
    )
    names = [c.name for c in report.checks]
    assert names == ALL_CHECK_NAMES


def test_run_qc_gate_missing_file_fails_proxy_render() -> None:
    report = run_qc_gate(
        video_path="/nonexistent.mp4",
        output_thumb_dir=Path("/tmp"),
    )
    proxy_check = next(c for c in report.checks if c.name == "proxy_render")
    assert proxy_check.passed is False
    # The probe-based checks are skipped when there is no video
    assert report.passed is False
    assert report.spans == {"black_frames": [], "silence": [], "frozen_frames": []}
    assert report.duration_sec is None


def test_run_qc_gate_duration_with_target() -> None:
    """clip_a is 2.0s; target 2.0s passes, target 30.0s fails."""
    ok = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
        target_duration_s=2.0,
    )
    dur = next(c for c in ok.checks if c.name == "duration")
    assert dur.passed is True
    assert "diff=0.00s" in dur.detail

    bad = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
        target_duration_s=30.0,
    )
    dur = next(c for c in bad.checks if c.name == "duration")
    assert dur.passed is False
    assert "target=30.00s" in dur.detail


def test_run_qc_gate_duration_without_target_is_informational() -> None:
    report = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
    )
    dur = next(c for c in report.checks if c.name == "duration")
    assert dur.passed is True
    assert "no target to compare" in dur.detail
    assert report.duration_sec == pytest.approx(2.0, abs=0.05)


def test_run_qc_gate_streams_missing_audio_fails() -> None:
    """The testdata clips are video-only: the streams + audio_sync checks
    must fail while the file-level checks pass."""
    report = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
    )
    streams = next(c for c in report.checks if c.name == "streams")
    assert streams.passed is False
    assert "1 video, 0 audio" in streams.detail
    audio_sync = next(c for c in report.checks if c.name == "audio_sync")
    assert audio_sync.passed is False


def test_run_qc_gate_overlays_burned_informational() -> None:
    """overlays_burned is informational (no OCR); it never fails the gate."""
    proxy = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
        mode="proxy",
    )
    overlays = next(c for c in proxy.checks if c.name == "overlays_burned")
    assert overlays.passed is True
    assert "not requested" in overlays.detail

    overlay = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
        mode="overlay",
    )
    overlays = next(c for c in overlay.checks if c.name == "overlays_burned")
    assert overlays.passed is True
    assert "visual review" in overlays.detail
