"""Tests for the QC gate (5 checks)."""
import shutil
from pathlib import Path

import pytest

from open_edit.qc.gate import run_qc_gate, QCReport


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)


def test_run_qc_gate_produces_report() -> None:
    report = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
    )
    assert isinstance(report, QCReport)
    assert len(report.checks) == 5


def test_run_qc_gate_check_names() -> None:
    report = run_qc_gate(
        video_path=str(TESTDATA / "clip_a.mp4"),
        output_thumb_dir=Path("/tmp"),
    )
    names = [c.name for c in report.checks]
    assert "mlt_load" in names
    assert "proxy_render" in names
    assert "black_frames" in names
    assert "silence" in names
    assert "thumbnail" in names


def test_run_qc_gate_missing_file_fails_proxy_render() -> None:
    report = run_qc_gate(
        video_path="/nonexistent.mp4",
        output_thumb_dir=Path("/tmp"),
    )
    proxy_check = next(c for c in report.checks if c.name == "proxy_render")
    assert proxy_check.passed is False
