"""Unit tests for the deterministic-QC text parsers.

These run without ffmpeg/melt — they verify the regex parsing logic that
turns ffmpeg stderr into structured spans. The integration tests (which
spawn ffmpeg) are in test_render_integration.py.
"""
from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from phase6_render_qc.audio import (
    _parse_db,
    _parse_overall_db,
    _parse_silence,
    get_audio_levels,
    list_silence,
)
from phase6_render_qc.black_frames import _parse_blackdetect, list_black_frames
from phase6_render_qc.render import parse_profile
from phase6_render_qc.thumbnails import _long_edge_scale


class TestParseProfile(unittest.TestCase):
    def test_parses_1920x1080_30fps(self) -> None:
        text = (
            '<?xml version="1.0"?>\n'
            '<mlt version="7.40.0">\n'
            '  <profile width="1920" height="1080" frame_rate_num="30" '
            'frame_rate_den="1" description="1920x1080 30.00fps"/>\n'
            '</mlt>\n'
        )
        p = parse_profile_from_text(text)
        self.assertEqual(p["width"], 1920)
        self.assertEqual(p["height"], 1080)
        self.assertEqual(p["frame_rate_num"], 30)
        self.assertEqual(p["frame_rate_den"], 1)

    def test_no_profile(self) -> None:
        self.assertEqual(parse_profile_from_text("<mlt></mlt>"), {})


def parse_profile_from_text(text: str) -> dict:
    import tempfile, os
    f = tempfile.NamedTemporaryFile(suffix=".kdenlive", delete=False, mode="w")
    f.write(text)
    f.close()
    try:
        return parse_profile(f.name)
    finally:
        os.unlink(f.name)


class TestLongEdgeScale(unittest.TestCase):
    def test_already_small(self) -> None:
        self.assertEqual(_long_edge_scale(400, 300), (400, 300))

    def test_scale_1920(self) -> None:
        w, h = _long_edge_scale(1920, 1080)
        self.assertEqual(max(w, h), 480)
        # Aspect preserved (~16:9).
        self.assertAlmostEqual(w / h, 1920 / 1080, places=2)

    def test_scale_portrait(self) -> None:
        w, h = _long_edge_scale(720, 1280)
        self.assertEqual(max(w, h), 480)
        self.assertEqual(min(w, h), 270)  # 480 * 720/1280

    def test_zero_dimensions(self) -> None:
        self.assertEqual(_long_edge_scale(0, 0), (0, 0))


class TestParseSilence(unittest.TestCase):
    def test_single_span(self) -> None:
        text = (
            "[silencedetect @ 0xabc] silence_start: 12.345\n"
            "[silencedetect @ 0xabc] silence_end: 14.567 | silence_duration: 2.222\n"
        )
        spans = _parse_silence(text, base_offset=0.0)
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0].start_sec, 12.345)
        self.assertAlmostEqual(spans[0].end_sec, 14.567)
        self.assertAlmostEqual(spans[0].duration_sec, 2.222)

    def test_with_offset(self) -> None:
        text = "[silencedetect @ 0x] silence_start: 1.0\n[silencedetect @ 0x] silence_end: 2.0 | silence_duration: 1.0\n"
        spans = _parse_silence(text, base_offset=10.0)
        self.assertEqual(spans[0].start_sec, 11.0)
        self.assertEqual(spans[0].end_sec, 12.0)

    def test_empty(self) -> None:
        self.assertEqual(_parse_silence("nothing here", 0.0), [])


class TestParseBlackdetect(unittest.TestCase):
    def test_single_span(self) -> None:
        text = "[blackdetect @ 0xabc] black_start:5.0 black_end:6.0 black_duration:1.0\n"
        spans = _parse_blackdetect(text, base_offset=0.0)
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0].start_sec, 5.0)
        self.assertAlmostEqual(spans[0].end_sec, 6.0)
        self.assertAlmostEqual(spans[0].duration_sec, 1.0)

    def test_with_offset(self) -> None:
        text = "[blackdetect @ 0x] black_start:2.0 black_end:3.0 black_duration:1.0\n"
        spans = _parse_blackdetect(text, base_offset=100.0)
        self.assertEqual(spans[0].start_sec, 102.0)

    def test_empty(self) -> None:
        self.assertEqual(_parse_blackdetect("nothing", 0.0), [])


class TestParseAudioDb(unittest.TestCase):
    def test_overall(self) -> None:
        text = "Number of samples: 100\nOverall\nRMS level=-23.5\nPeak level=-3.2\n"
        self.assertAlmostEqual(_parse_overall_db(text, "RMS level"), -23.5)
        self.assertAlmostEqual(_parse_overall_db(text, "Peak level"), -3.2)

    def test_fallback(self) -> None:
        text = "RMS level=-15.0\nPeak level=-1.0\n"
        self.assertAlmostEqual(_parse_db(text, "RMS level"), -15.0)

    def test_missing(self) -> None:
        self.assertEqual(_parse_db("", "RMS level"), 0.0)


class TestAudioTimeout(unittest.TestCase):
    """Regression: a synthetic infinite-audio source (FIFO that never closes)
    must not crash the caller. The ffmpeg subprocess will hang; the function
    must catch TimeoutExpired and return ok=False with a clear error."""

    def setUp(self) -> None:
        import tempfile
        # Real file so the function's "video not found" check passes; the
        # file content is irrelevant because subprocess.run is mocked.
        fd, self.path = tempfile.mkstemp(suffix=".mp4")
        import os
        os.close(fd)

    def tearDown(self) -> None:
        import os
        os.unlink(self.path)

    def test_get_audio_levels_timeout_returns_ok_false(self) -> None:
        with patch(
            "phase6_render_qc.audio.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=60),
        ):
            r = get_audio_levels(self.path)
        self.assertFalse(r.ok)
        self.assertIsNotNone(r.error)
        self.assertIn("timed out", r.error.lower())

    def test_list_silence_timeout_returns_ok_false(self) -> None:
        with patch(
            "phase6_render_qc.audio.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=60),
        ):
            r = list_silence(self.path)
        self.assertFalse(r.ok)
        self.assertIsNotNone(r.error)
        self.assertIn("timed out", r.error.lower())


class TestBlackFramesRangeValidation(unittest.TestCase):
    """Regression: the -to argument passed to ffmpeg is computed as
    ``out_sec - in_sec``. If out_sec <= in_sec, this becomes zero or
    negative and ffmpeg errors out. The function must reject the bad
    range up-front instead of passing a nonsense command line."""

    def test_out_sec_less_than_in_sec_rejected(self) -> None:
        r = list_black_frames("dummy.mp4", in_sec=5.0, out_sec=2.0)
        self.assertFalse(r.ok)
        self.assertIsNotNone(r.error)
        self.assertIn("range", r.error.lower())

    def test_out_sec_equal_to_in_sec_rejected(self) -> None:
        r = list_black_frames("dummy.mp4", in_sec=3.0, out_sec=3.0)
        self.assertFalse(r.ok)
        self.assertIsNotNone(r.error)
        self.assertIn("range", r.error.lower())


class TestBlackFramesSyntheticFixture(unittest.TestCase):
    """Synthetic ffmpeg blackdetect output exercising multi-span and
    min_sec-filtered (sub-threshold) cases. ffmpeg's blackdetect only
    emits lines for spans >= d= (the min_sec windowing parameter), so
    the parser should never see sub-threshold lines in production; this
    fixture locks in the expected parsing of the standard output."""

    def test_multi_span_fixture(self) -> None:
        text = (
            "[blackdetect @ 0xabc] black_start:0.5 black_end:2.0 black_duration:1.5\n"
            "[blackdetect @ 0xabc] black_start:5.0 black_end:6.5 black_duration:1.5\n"
        )
        spans = _parse_blackdetect(text, base_offset=0.0)
        self.assertEqual(len(spans), 2)
        self.assertAlmostEqual(spans[0].start_sec, 0.5)
        self.assertAlmostEqual(spans[0].end_sec, 2.0)
        self.assertAlmostEqual(spans[0].duration_sec, 1.5)
        self.assertAlmostEqual(spans[1].start_sec, 5.0)
        self.assertAlmostEqual(spans[1].end_sec, 6.5)
        self.assertAlmostEqual(spans[1].duration_sec, 1.5)

    def test_multi_span_with_offset(self) -> None:
        text = (
            "[blackdetect @ 0xabc] black_start:0.5 black_end:2.0 black_duration:1.5\n"
        )
        spans = _parse_blackdetect(text, base_offset=100.0)
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0].start_sec, 100.5)
        self.assertAlmostEqual(spans[0].end_sec, 102.0)


if __name__ == "__main__":
    unittest.main()
