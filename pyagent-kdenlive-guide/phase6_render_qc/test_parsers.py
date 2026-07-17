"""Unit tests for the deterministic-QC text parsers.

These run without ffmpeg/melt — they verify the regex parsing logic that
turns ffmpeg stderr into structured spans. The integration tests (which
spawn ffmpeg) are in test_render_integration.py.
"""
from __future__ import annotations

import unittest

from phase6_render_qc.audio import _parse_db, _parse_overall_db, _parse_silence
from phase6_render_qc.black_frames import _parse_blackdetect
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


if __name__ == "__main__":
    unittest.main()
