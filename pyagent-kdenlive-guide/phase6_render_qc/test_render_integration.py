"""Integration tests for Phase 6 — actually invokes melt and ffmpeg.

Requires:
- melt on PATH
- ffmpeg + ffprobe on PATH
- the demo.kdenlive fixture at phase3_pyagent_core/tests/fixtures/

These tests are slow (a few seconds each) but exercise the real
acceptance criteria from PHASE_6_render_and_qc.md §Acceptance.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "phase3_pyagent_core" / "tests" / "fixtures" / "demo.kdenlive"


@unittest.skipIf(shutil.which("melt") is None, "melt not on PATH")
@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not on PATH")
@unittest.skipIf(not FIXTURE.is_file(), "demo.kdenlive fixture missing")
class TestRenderIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pyagent_phase6_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_proxy_render_produces_playable_file(self) -> None:
        from phase6_render_qc.render import render
        out = os.path.join(self.tmp, "proxy.mp4")
        rr = render(str(FIXTURE), out, mode="proxy")
        self.assertTrue(rr.ok, f"render failed: {rr.error}")
        self.assertTrue(os.path.isfile(out))
        size = os.path.getsize(out)
        # A 4-second 640x360 ultrafast encode should land well under 5MB.
        self.assertGreater(size, 5_000)
        self.assertLess(size, 5_000_000)

    def test_final_render_uses_project_profile(self) -> None:
        from phase6_render_qc.render import render
        out = os.path.join(self.tmp, "final.mp4")
        rr = render(str(FIXTURE), out, mode="final")
        self.assertTrue(rr.ok, f"render failed: {rr.error}")
        # ffprobe the output to confirm resolution matches the project profile.
        import subprocess
        info = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "default=noprint_wrappers=1:nokey=0", out],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(info.returncode, 0, info.stderr)
        text = info.stdout
        # The demo fixture is 1920x1080. We just check the output is HD,
        # not 640x360 (which would mean the proxy path was taken).
        self.assertIn("width=1920", text)
        self.assertIn("height=1080", text)

    def test_render_invalid_mode(self) -> None:
        from phase6_render_qc.render import render
        out = os.path.join(self.tmp, "x.mp4")
        rr = render(str(FIXTURE), out, mode="garbage")
        self.assertFalse(rr.ok)
        self.assertIn("invalid mode", rr.error)

    def test_render_missing_project(self) -> None:
        from phase6_render_qc.render import render
        out = os.path.join(self.tmp, "x.mp4")
        rr = render("/nonexistent.kdenlive", out, mode="proxy")
        self.assertFalse(rr.ok)


@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not on PATH")
class TestThumbnailIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pyagent_phase6_")
        # Render a tiny proxy first so we have something to thumbnail.
        from phase6_render_qc.render import render
        self.video = os.path.join(self.tmp, "video.mp4")
        if shutil.which("melt") and FIXTURE.is_file():
            rr = render(str(FIXTURE), self.video, mode="proxy")
            if not rr.ok:
                self.video = None

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_thumbnail_respects_caps(self) -> None:
        if not self.video:
            self.skipTest("no video (melt/fixture unavailable)")
        from phase6_render_qc.thumbnails import get_thumbnail
        out = os.path.join(self.tmp, "thumb.jpg")
        r = get_thumbnail(self.video, 0.0, out)
        self.assertTrue(r.ok, f"thumbnail failed: {r.error}")
        self.assertLessEqual(max(r.width, r.height), 480)
        # Hard cap: <250KB per the Phase 6 plan.
        self.assertLess(r.file_bytes, 250_000)
        # And it should actually be a JPEG.
        with open(out, "rb") as f:
            self.assertEqual(f.read(3), b"\xff\xd8\xff")

    def test_get_qc_crop(self) -> None:
        if not self.video:
            self.skipTest("no video (melt/fixture unavailable)")
        from phase6_render_qc.thumbnails import get_qc_crop
        out = os.path.join(self.tmp, "crop.jpg")
        r = get_qc_crop(self.video, 1.0,
                        {"x": 100, "y": 100, "w": 400, "h": 300}, out)
        self.assertTrue(r.ok, f"crop failed: {r.error}")
        self.assertLessEqual(max(r.width, r.height), 480)


@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not on PATH")
class TestBlackFramesIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pyagent_phase6_")
        from phase6_render_qc.render import render
        self.video = os.path.join(self.tmp, "video.mp4")
        if shutil.which("melt") and FIXTURE.is_file():
            rr = render(str(FIXTURE), self.video, mode="proxy")
            if not rr.ok:
                self.video = None

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_blackdetect_on_intentionally_black_demo(self) -> None:
        # The demo fixture references a source clip that is all black, so
        # blackdetect SHOULD return a span covering the full duration.
        # This verifies the parser/wrapper plumbing, not the absence of
        # black frames (which is asserted in a unit test on fake input).
        if not self.video:
            self.skipTest("no video (melt/fixture unavailable)")
        from phase6_render_qc.black_frames import list_black_frames
        r = list_black_frames(self.video)
        self.assertTrue(r.ok, f"blackdetect failed: {r.error}")
        self.assertGreaterEqual(len(r.spans), 1)
        # First span should start at 0 and cover most of the 4s clip.
        sp = r.spans[0]
        self.assertLessEqual(sp.start_sec, 0.5)
        self.assertGreaterEqual(sp.end_sec, 3.0)


@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not on PATH")
class TestSilenceIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pyagent_phase6_")
        from phase6_render_qc.render import render
        self.video = os.path.join(self.tmp, "video.mp4")
        if shutil.which("melt") and FIXTURE.is_file():
            rr = render(str(FIXTURE), self.video, mode="proxy")
            if not rr.ok:
                self.video = None

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_audio_levels(self) -> None:
        if not self.video:
            self.skipTest("no video (melt/fixture unavailable)")
        from phase6_render_qc.audio import get_audio_levels
        r = get_audio_levels(self.video)
        self.assertTrue(r.ok, f"audio levels failed: {r.error}")
        # dB values should be finite and negative (or zero for total silence).
        self.assertLess(r.peak_db, 10.0)
        self.assertGreater(r.peak_db, -200.0)


if __name__ == "__main__":
    unittest.main()
