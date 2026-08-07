"""Tests for the timeline-view composite (video-use merge, transcript-first layer)."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

import pytest

from open_edit.ir.types import WordAlignment
from open_edit.render.timeline_view import (
    SILENCE_THRESHOLD_S,
    build_timeline_view,
    find_silences,
)


def _words():
    return [
        WordAlignment(word="hello", t_start=0.2, t_end=0.7, confidence=1.0),
        WordAlignment(word="world", t_start=1.8, t_end=2.3, confidence=1.0),
    ]


def test_find_silences_detects_gaps_and_edges():
    sil = find_silences(_words(), start=0.0, end=3.0)
    # lead-in 0->0.2 (0.2s < 0.4 -> no), inter-word 0.7->1.8 (1.1s -> yes),
    # trailing 2.3->3.0 (0.7s -> yes)
    assert (0.7, 1.8) in sil
    assert (2.3, 3.0) in sil
    assert sil[0] == (0.7, 1.8)


def test_find_silences_respects_threshold():
    words = [WordAlignment(word="a", t_start=0.0, t_end=0.5),
             WordAlignment(word="b", t_start=0.85, t_end=1.3)]  # gap 0.35 < 0.4
    # inter-word gap ignored; trailing 1.3->2.0 (0.7s) still reported
    assert find_silences(words, 0.0, 2.0) == [(1.3, 2.0)]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_build_timeline_view_real_ffmpeg(tmp_path):
    video = Path("/home/amr/apps/mlt-pipeline/testdata/video_with_audio.mp4")
    if not video.exists():
        pytest.skip("testdata clip missing")
    out = tmp_path / "view.png"
    result = build_timeline_view(
        video, 0.0, 2.0, words=_words(), n_frames=4, width=1024, out_path=out,
    )
    assert result == out and out.exists() and out.stat().st_size > 5000
    from PIL import Image
    im = Image.open(out)
    assert im.size[1] >= 500  # full composite height
    # filmstrip + waveform regions must contain non-background content
    px = im.convert("RGB").load()
    non_bg = sum(
        1 for y in range(50, 230, 6) for x in range(0, im.size[0], 12)
        if px[x, y] != (18, 18, 22)
    )
    assert non_bg > 50


def test_build_timeline_view_mocked_ffmpeg(tmp_path):
    """Composite layout without real ffmpeg: subprocess is stubbed, PIL is real."""
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def fake_run(cmd, **kw):
        out = cmd[-1]
        Path(out).write_bytes(b"\x89PNG fake")
        return mock.Mock()

    from PIL import Image as PILImage

    plain = PILImage.new("RGB", (64, 64), (100, 100, 100))
    with mock.patch("subprocess.run", side_effect=fake_run), mock.patch.object(
        PILImage, "open", return_value=plain
    ):
        out = tmp_path / "v.png"
        result = build_timeline_view(video, 0.0, 2.0, words=_words(), n_frames=5, out_path=out)
        assert result == out and out.exists() and out.stat().st_size > 1000


def test_get_timeline_view_tool_contract(tmp_path):
    """Tool-level: error handling and path confinement."""
    import sys
    sys.path.insert(0, str(tmp_path.parent))
    from open_edit.agent.tools.pyagent_get_timeline_view import get_timeline_view

    res = get_timeline_view({}, str(tmp_path))
    assert res["status"] == "error"

    res = get_timeline_view({"asset_hash": "nope"}, str(tmp_path))
    assert res["status"] == "error"

    res = get_timeline_view({"path": "../../etc/passwd"}, str(tmp_path))
    assert res["status"] == "error" and "escapes" in res["error"]

    # missing media file inside project -> error
    res = get_timeline_view({"path": "missing.mp4", "start_sec": 0, "end_sec": 1}, str(tmp_path))
    assert res["status"] == "error"
