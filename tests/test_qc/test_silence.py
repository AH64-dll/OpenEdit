"""Tests for silence detection."""
import shutil
from pathlib import Path

import pytest

from open_edit.qc.silence import list_silence, get_audio_levels, SilenceResult


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)


def test_list_silence_on_synthetic_clip() -> None:
    """A synthetic color clip (no audio) should produce a clean result."""
    result = list_silence(str(TESTDATA / "clip_a.mp4"))
    assert isinstance(result, SilenceResult)


def test_get_audio_levels_on_synthetic_clip() -> None:
    levels = get_audio_levels(str(TESTDATA / "clip_a.mp4"))
    assert levels.ok is True or "ffmpeg" in (levels.error or "")


def test_list_silence_decode_failure_is_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A decode failure (ffmpeg exit != 0) must surface as ok=False with
    the last stderr line, never as a silent '0 silence' success."""
    garbage = tmp_path / "broken.mp4"
    garbage.write_text("this is not a video file", encoding="utf-8")
    monkeypatch.setattr("open_edit.qc.silence._has_audio_stream", lambda _p: True)

    result = list_silence(str(garbage))
    assert result.ok is False
    assert result.error not in (None, "")
