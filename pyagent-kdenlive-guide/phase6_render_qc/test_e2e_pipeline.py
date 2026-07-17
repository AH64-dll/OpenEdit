"""End-to-end pipeline smoke test: Phase 3 edit -> Phase 6 render/QC.

No LLM. Uses the demo fixture to apply a known sequence of edits via
phase3_pyagent_core.run_op, then renders and inspects the result with
every Phase 6 tool. Asserts real artifacts (file size, MP4 dimensions,
JPEG magic, file-size caps). Runs in <15s on a developer machine.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "phase3_pyagent_core" / "tests" / "fixtures" / "demo.kdenlive"
CATALOG = REPO / "phase1_knowledge_base" / "catalog.json"


def _run(op: str, args: dict, project: str, catalog: str) -> tuple[int, dict]:
    """Helper: call phase3_pyagent_core.run_op and return (code, resp)."""
    from phase3_pyagent_core.__main__ import run_op
    return run_op(op, args, project, catalog)


def _video_info(path: str) -> dict:
    """Tiny ffprobe wrapper — just width/height/duration of video stream."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,duration",
         "-of", "default=noprint_wrappers=1:nokey=0", path],
        capture_output=True, text=True, timeout=30,
    )
    info: dict = {}
    for line in (out.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


@unittest.skipIf(shutil.which("melt") is None, "melt not on PATH")
@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not on PATH")
@unittest.skipIf(shutil.which("ffprobe") is None, "ffprobe not on PATH")
@unittest.skipIf(not FIXTURE.is_file(), "demo.kdenlive fixture missing")
@unittest.skipIf(not CATALOG.is_file(), "catalog.json missing")
class TestE2EPipeline(unittest.TestCase):
    """Edit a copy of the demo fixture, render a proxy, run all QC tools."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pyagent_e2e_")
        self.project = os.path.join(self.tmp, "work.kdenlive")
        with open(FIXTURE, "rb") as src, open(self.project, "wb") as dst:
            dst.write(src.read())
        self.proxy = os.path.join(self.tmp, "proxy.mp4")
        self.thumb = os.path.join(self.tmp, "thumb.jpg")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_edit_render_qc_roundtrip(self) -> None:
        # ---- Phase 3: read the existing clip from the demo fixture ----
        # The demo has one clip on track 0 (4s long, kdenlive:id="2") whose
        # source media is the 10s clip_short.mp4.
        code, resp = _run("get_timeline_summary", {}, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"get_timeline_summary failed: {resp}")
        self.assertTrue(resp.get("ok"), resp)
        summary = resp["result"]
        self.assertGreaterEqual(len(summary.clips), 1, "demo has no clips")
        existing_clip = summary.clips[0]
        existing_id = existing_clip.clip_id
        source_path = existing_clip.source_path

        # Import the source media to get a fresh source_id (the bin's
        # existing kdenlive:id is "1", but going through import_media
        # exercises a realistic e2e path: bin -> timeline).
        code, resp = _run(
            "import_media", {"paths": [source_path]}, self.project, str(CATALOG)
        )
        self.assertEqual(code, 0, f"import_media failed: {resp}")
        self.assertTrue(resp.get("ok"), resp)
        source_ids = resp["result"]
        self.assertIsInstance(source_ids, list)
        self.assertGreaterEqual(len(source_ids), 1, resp)
        new_source_id = source_ids[0]

        # Append a 2s clip onto track 0 using the imported source.
        code, resp = _run("append_clip", {
            "track_index": 0,
            "source_id": new_source_id,
            "source_in_sec": 0,
            "source_out_sec": 2.0,
        }, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"append_clip failed: {resp}")
        self.assertTrue(resp.get("ok"), resp)
        # append_clip returns the new kdenlive:id as a plain string.
        new_id = resp["result"]
        self.assertIsInstance(new_id, str)
        self.assertGreater(len(new_id), 0, f"empty clip id: {resp}")

        # Add a 1s dissolve between the existing clip and the new one.
        # ("crossfade" is not a catalog id — the catalog uses "dissolve".)
        code, resp = _run("add_transition", {
            "clip_a_id": existing_id,
            "clip_b_id": new_id,
            "kind": "dissolve",
            "duration_sec": 1.0,
        }, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"add_transition failed: {resp}")
        self.assertTrue(resp.get("ok"), resp)

        # Save.
        code, resp = _run("save", {}, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"save failed: {resp}")
        self.assertTrue(resp.get("ok"), resp)

        # ---- Phase 6: render + QC every tool ----
        from phase6_render_qc.render import render
        rr = render(self.project, self.proxy, mode="proxy")
        self.assertTrue(rr.ok, f"render failed: {rr.error}")
        self.assertTrue(os.path.isfile(self.proxy), "proxy not written")
        self.assertGreater(os.path.getsize(self.proxy), 5_000, "proxy too small")

        info = _video_info(self.proxy)
        self.assertEqual(info.get("width"), "640", info)
        self.assertEqual(info.get("height"), "360", info)
        # 4s original + 2s appended; the dissolve is an effect, not a
        # position shift, so total timeline = ~6s. We accept [4.5, 7.0]
        # to be tolerant of test drift.
        dur = float(info.get("duration", 0))
        self.assertGreater(dur, 4.5, f"proxy too short: {dur}s")
        self.assertLess(dur, 7.0, f"proxy too long: {dur}s")

        from phase6_render_qc.black_frames import list_black_frames
        bf = list_black_frames(self.proxy)
        self.assertTrue(bf.ok, f"blackdetect failed: {bf.error}")
        self.assertIsInstance(bf.spans, list)

        from phase6_render_qc.audio import list_silence, get_audio_levels
        sil = list_silence(self.proxy)
        self.assertTrue(sil.ok, f"silencedetect failed: {sil.error}")
        self.assertIsInstance(sil.spans, list)
        self.assertEqual(sil.threshold_db, -35.0)
        self.assertEqual(sil.min_sec, 1.0)

        al = get_audio_levels(self.proxy)
        self.assertTrue(al.ok, f"audio levels failed: {al.error}")
        self.assertLess(al.peak_db, 10.0)
        self.assertGreater(al.peak_db, -200.0)

        from phase6_render_qc.thumbnails import get_thumbnail, get_qc_crop
        # Thumbnail at the dissolve midpoint (4s = cut point).
        th = get_thumbnail(self.proxy, 4.0, self.thumb)
        self.assertTrue(th.ok, f"thumbnail failed: {th.error}")
        self.assertLessEqual(max(th.width, th.height), 480)
        self.assertLess(th.file_bytes, 250_000)
        with open(self.thumb, "rb") as f:
            self.assertEqual(f.read(3), b"\xff\xd8\xff", "not a JPEG")

        # QC crop — sample a 200x150 region at the same timestamp.
        crop_out = os.path.join(self.tmp, "crop.jpg")
        cr = get_qc_crop(self.proxy, 4.0,
                         {"x": 200, "y": 100, "w": 200, "h": 150}, crop_out)
        self.assertTrue(cr.ok, f"qc crop failed: {cr.error}")
        self.assertLessEqual(max(cr.width, cr.height), 480)
        self.assertLess(cr.file_bytes, 250_000)


if __name__ == "__main__":
    unittest.main()
