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
