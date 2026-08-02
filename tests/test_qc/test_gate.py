"""Tests for the QC gate (documented 6 checks + pipeline diagnostics)."""
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest

from open_edit.qc import gate as gate_mod
from open_edit.qc.black_frames import BlackFramesResult, BlackSpan
from open_edit.qc.frozen_frames import FrozenFramesResult
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


def test_source_known_black_span_is_not_a_new_render_defect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "proxy.mp4"
    output.write_bytes(b"proxy")
    monkeypatch.setattr(
        gate_mod,
        "probe_streams",
        lambda _: SimpleNamespace(
            ok=True, container_duration_s=1.0, video_streams=1,
            audio_streams=1, video_duration_s=1.0, audio_duration_s=1.0,
            codec_types=["video", "audio"], error=None,
        ),
    )
    monkeypatch.setattr(
        gate_mod,
        "list_black_frames",
        lambda _: BlackFramesResult(
            ok=True, in_sec=0.0, out_sec=0.0, threshold=0.1, min_sec=0.5,
            spans=[BlackSpan(start_sec=0.0, end_sec=0.6, duration_sec=0.6)],
        ),
    )
    monkeypatch.setattr(
        gate_mod,
        "list_frozen_frames",
        lambda *args, **kwargs: FrozenFramesResult(
            ok=True, min_sec=1.0, noise_db=-50.0, spans=[],
        ),
    )
    monkeypatch.setattr(
        gate_mod, "list_silence",
        lambda _: SimpleNamespace(ok=True, spans=[]),
    )
    monkeypatch.setattr(
        gate_mod, "get_thumbnail",
        lambda *args, **kwargs: SimpleNamespace(
            ok=True, width=2, height=2, error=None,
        ),
    )

    report = run_qc_gate(
        str(output),
        tmp_path,
        source_baseline={
            "black_frames": [{"start_sec": 0.0, "end_sec": 0.6}],
            "frozen_frames": [],
        },
    )

    black_check = next(c for c in report.checks if c.name == "black_frames")
    assert black_check.passed is True
    assert report.source_known_spans["black_frames"]
