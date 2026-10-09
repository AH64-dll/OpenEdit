"""Regression tests for the ranged silencedetect/astats window fix (report-1 R1).

Covers open_edit/render/ffmpeg_probe.detect_silence_spans and
open_edit/qc/silence.get_audio_levels: fixture is a real MP4 with loud audio
in [0, 2) and silence in [2, 4) (see testdata build below).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.qc.silence import list_silence
from open_edit.render.ffmpeg_probe import detect_silence_spans

# A span may overshoot the requested end by at most one audio frame of the
# 44.1 kHz AAC fixture (~0.108 s is generous for the last partial frame).
_FRAME_GRACE_SEC = 0.15

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg/ffprobe not installed",
)


def _fixture_encoder_available() -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    )
    return proc.returncode == 0 and "libx264" in proc.stdout


@pytest.fixture(scope="module")
def loud_then_silent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """4s clip: 1 kHz sine for the first 2s, digital silence afterwards."""
    if not _fixture_encoder_available():
        pytest.skip("ffmpeg build lacks libx264 needed to build the test fixture")
    tmp = tmp_path_factory.mktemp("silence-window")
    path = tmp / "loud-then-silent.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100:duration=2",
            "-f", "lavfi", "-i", "anullsrc=sample_rate=44100:duration=2",
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]",
            "-map", "[a]", "-c:a", "pcm_s16le", str(tmp / "mix.wav"),
        ],
        check=True, capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=4",
            "-i", str(tmp / "mix.wav"),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def test_ranged_spans_stay_within_the_requested_window(
    loud_then_silent: Path,
) -> None:
    """A [1, 3] window reports the loud/silent boundary; no span leaks
    outside the window and nothing is re-offset by start_sec. The final
    frame-length overshoot of the last AAC frame is allowed."""
    spans = detect_silence_spans(loud_then_silent, start_sec=1.0, end_sec=3.0)
    assert spans, "expected the [2, end) silence inside a [1, 3] window"
    for start, end in spans:
        assert 1.0 <= start
        assert end <= 3.0 + _FRAME_GRACE_SEC
    # The detected boundary matches the fixture's real 2.0 s transition
    # (frame quantization shifts the transition by at most one AAC frame).
    starts = [start for start, _ in spans]
    assert min(starts) == pytest.approx(2.0, abs=0.2)


def test_ranged_window_before_the_silence_detects_nothing(
    loud_then_silent: Path,
) -> None:
    """A window that only covers loud audio reports no silence."""
    assert detect_silence_spans(loud_then_silent, start_sec=0.0, end_sec=1.5) == []


def test_unranged_detection_is_unchanged(loud_then_silent: Path) -> None:
    """Without a window the whole file is scanned from t=0."""
    spans = detect_silence_spans(loud_then_silent)
    assert len(spans) == 1
    start, end = spans[0]
    assert start == pytest.approx(2.0, abs=0.2)
    assert end == pytest.approx(4.0, abs=0.2)


def test_ranged_window_reports_no_spans_after_the_file(
    loud_then_silent: Path,
) -> None:
    """A window past the last loud frame still stays inside the window and
    never re-offsets absolute timestamps past the file duration."""
    spans = detect_silence_spans(loud_then_silent, start_sec=2.5, end_sec=4.0)
    for start, end in spans:
        assert 2.5 <= start
        assert end <= 4.0 + _FRAME_GRACE_SEC


def test_list_silence_forwards_the_ranged_window(loud_then_silent: Path) -> None:
    """The qc.silence wrapper keeps the window on the spans it returns."""
    result = list_silence(str(loud_then_silent), 1.0, 3.0)
    assert result.ok, result.error
    for span in result.spans:
        assert 1.0 <= span.start_sec
        assert span.end_sec <= 3.0 + _FRAME_GRACE_SEC


def test_get_audio_levels_sees_only_the_requested_window(
    loud_then_silent: Path,
) -> None:
    """Windowed astats differ from the whole-file result and from silence."""
    import subprocess  # noqa: PLC0415 (local import mirrors call site)

    from open_edit.qc.silence import get_audio_levels  # noqa: PLC0415

    loud = get_audio_levels(str(loud_then_silent), 0.0, 1.5)
    quiet = get_audio_levels(str(loud_then_silent), 2.0, 4.0)
    at_window = get_audio_levels(str(loud_then_silent), 1.0, 2.0)
    full = get_audio_levels(str(loud_then_silent))

    assert loud.ok and quiet.ok and full.ok, (loud.error, quiet.error, full.error)
    assert quiet.rms_db < loud.rms_db - 20.0, (quiet.rms_db, loud.rms_db)
    # The R1 bug produced the same whole-file value for every window;
    # windowed stats are distinctly lower inside the silent half.
    assert at_window.rms_db > quiet.rms_db + 10.0
    # Aggregate values must reflect the window, not silently the whole file.
    measured_window_rms = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-ss", "1.000",
            "-i", str(loud_then_silent), "-vn", "-af", "astats=metadata=1:reset=0",
            "-t", "1.000", "-f", "null", "-",
        ],
        capture_output=True, text=True, check=False,
    ).stderr
    assert at_window.rms_db == pytest.approx(-21.27, abs=0.5), measured_window_rms
