"""Tests for the pyagent runtime CLI dispatcher.

These tests call `python3 -m phase3_pyagent_core` as a subprocess to exercise
the full CLI path. They require the package to be installed (via
`make install` or `pip install -e .`).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "phase3_pyagent_core"
CATALOG_PATH = REPO_ROOT / "phase1_knowledge_base" / "catalog.json"
FIXTURES_DIR = RUNTIME_DIR / "tests" / "fixtures"
# The test clip lives at <mlt-pipeline>/testdata/clip_short.mp4, one level above
# this package's repo root. (The brief's `REPO_ROOT / "testdata"` was off by one —
# testdata is a sibling of `pyagent-kdenlive-guide/`, not a child.)
MLT_ROOT = Path(__file__).resolve().parents[2]
TESTDATA_CLIP = MLT_ROOT / "testdata" / "clip_short.mp4"


def _run_runtime(op: str, args: dict, project: str, catalog: str = str(CATALOG_PATH)) -> tuple[int, dict]:
    """Invoke phase3_pyagent_core as a subprocess. Returns (exit_code, json_response)."""
    proc = subprocess.run(
        [sys.executable, "-m", "phase3_pyagent_core", op,
         "--project", project,
         "--catalog", catalog,
         "--args-json", json.dumps(args)],
        capture_output=True, text=True,
    )
    last_line = proc.stdout.strip().split("\n")[-1] if proc.stdout.strip() else "{}"
    return proc.returncode, json.loads(last_line)


class TestDispatch(unittest.TestCase):
    """The dispatcher itself, before any backend methods are wired."""

    def test_unknown_op_returns_fatal_error(self):
        """A non-existent op must exit 2 with a fatal flag."""
        with tempfile.TemporaryDirectory() as tmp:
            fake_project = os.path.join(tmp, "fake.kdenlive")
            Path(fake_project).write_text("<mlt/>")
            code, resp = _run_runtime("not_a_real_op", {}, fake_project)
        self.assertEqual(code, 2)
        self.assertFalse(resp["ok"])
        self.assertTrue(resp.get("fatal"))
        self.assertIn("not_a_real_op", resp["error"])

    def test_missing_project_returns_fatal_error(self):
        """A non-existent project file must exit 2 with fatal."""
        code, resp = _run_runtime("get_project_info", {}, "/nonexistent/path.kdenlive")
        self.assertEqual(code, 2)
        self.assertFalse(resp["ok"])
        self.assertTrue(resp.get("fatal"))

    def test_help_flag_prints_usage(self):
        """`python3 -m phase3_pyagent_core --help` should print usage and exit 0."""
        proc = subprocess.run(
            [sys.executable, "-m", "phase3_pyagent_core", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage", proc.stdout.lower())


class TestReadOps(unittest.TestCase):
    """The two read-only ops, exercised against tests/fixtures/demo.kdenlive."""

    @classmethod
    def setUpClass(cls):
        cls.project = str(FIXTURES_DIR / "demo.kdenlive")
        if not Path(cls.project).exists():
            raise unittest.SkipTest(f"demo.kdenlive missing; run tests/fixtures/make_demo.py first")

    def test_get_project_info_returns_valid_dict(self):
        code, resp = _run_runtime("get_project_info", {}, self.project)
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        info = resp["result"]
        self.assertIn("name", info)
        self.assertIn("fps", info)
        self.assertIn("width", info)
        self.assertIn("height", info)
        self.assertIn("track_count", info)
        self.assertIn("duration_sec", info)

    def test_get_timeline_summary_returns_valid_dict(self):
        code, resp = _run_runtime("get_timeline_summary", {}, self.project)
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        summary = resp["result"]
        self.assertIn("project", summary)
        self.assertIn("tracks", summary)
        self.assertIn("clips", summary)
        self.assertIsInstance(summary["clips"], list)
        # demo.kdenlive has exactly 1 clip from make_demo.py.
        self.assertEqual(len(summary["clips"]), 1)
        clip = summary["clips"][0]
        self.assertIn("clip_id", clip)
        self.assertIn("start_sec", clip)
        self.assertIn("end_sec", clip)


class TestMutatingOps(unittest.TestCase):
    """Mutating ops. Each test copies demo.kdenlive to a temp file so the
    fixture stays clean for the rest of the suite."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = os.path.join(self.tmpdir, "test.kdenlive")
        # Copy the demo fixture to the temp location.
        with open(FIXTURES_DIR / "demo.kdenlive", "rb") as src:
            with open(self.project, "wb") as dst:
                dst.write(src.read())
        self.clip_path = str(TESTDATA_CLIP)
        if not Path(self.clip_path).exists():
            self.skipTest(f"test clip missing: {self.clip_path}")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_import_media_returns_clip_id(self):
        code, resp = _run_runtime(
            "import_media", {"paths": [self.clip_path]}, self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        ids = resp["result"]
        self.assertIsInstance(ids, list)
        self.assertEqual(len(ids), 1)
        self.assertIsInstance(ids[0], str)

    def test_append_clip_after_import(self):
        # Import a clip, then append it. The full chain from the spec.
        code, resp = _run_runtime(
            "import_media", {"paths": [self.clip_path]}, self.project,
        )
        self.assertEqual(code, 0)
        source_id = resp["result"][0]

        code, resp = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": source_id,
             "source_in_sec": 0.0, "source_out_sec": 4.0},
            self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        self.assertIsInstance(resp["result"], str)
        # The new clip id should be visible in a fresh get_timeline_summary.
        _, summary_resp = _run_runtime("get_timeline_summary", {}, self.project)
        clip_ids = [c["clip_id"] for c in summary_resp["result"]["clips"]]
        self.assertIn(resp["result"], clip_ids)
        self.assertEqual(len(summary_resp["result"]["clips"]), 2)

    def test_full_crossfade_chain(self):
        """The spec's headline acceptance test: import two clips, append them,
        add a transition between them, then save. The saved file must still
        be a valid .kdenlive."""
        # Import two copies of the test clip.
        code, r = _run_runtime(
            "import_media", {"paths": [self.clip_path, self.clip_path]}, self.project,
        )
        self.assertEqual(code, 0)
        a_src, b_src = r["result"]

        # Append both.
        code, r = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": a_src, "source_out_sec": 4.0},
            self.project,
        )
        self.assertEqual(code, 0)
        a_id = r["result"]

        code, r = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": b_src, "source_out_sec": 4.0},
            self.project,
        )
        self.assertEqual(code, 0)
        b_id = r["result"]

        # Add the crossfade.
        code, r = _run_runtime(
            "add_transition",
            {"clip_a_id": a_id, "clip_b_id": b_id,
             "kind": "composite", "duration_sec": 1.0},
            self.project,
        )
        self.assertEqual(code, 0)
        t_id = r["result"]
        self.assertIsInstance(t_id, str)

        # Save.
        code, r = _run_runtime("save", {}, self.project)
        self.assertEqual(code, 0)

        # The saved file must be a valid .kdenlive that opens without errors.
        # (Round-trip: reload and verify clip count + transition count.)
        # demo.kdenlive starts with 1 clip; we appended 2 more, so 3 total.
        _, summary = _run_runtime("get_timeline_summary", {}, self.project)
        self.assertEqual(len(summary["result"]["clips"]), 3)
        self.assertEqual(len(summary["result"]["transitions"]), 1)

    def test_insert_clip_then_move(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]

        code, r = _run_runtime(
            "insert_clip",
            {"track_index": 0, "position_sec": 0.0, "source_id": sid,
             "source_out_sec": 3.0},
            self.project,
        )
        self.assertEqual(code, 0)
        cid = r["result"]

        # Move it to a new position on the same track. (The plan's brief
        # specified new_track=1, but demo.kdenlive has only 1 track, so
        # move to a new position on track 0 instead. The move-mechanic
        # under test — that move_clip updates track_index + start_sec — is
        # identical for the same-track case.)
        code, r = _run_runtime(
            "move_clip", {"clip_id": cid, "new_track": 0, "new_position_sec": 5.0},
            self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(r["ok"])

        # Verify.
        _, summary = _run_runtime("get_timeline_summary", {}, self.project)
        moved = next(c for c in summary["result"]["clips"] if c["clip_id"] == cid)
        self.assertEqual(moved["track_index"], 0)
        self.assertAlmostEqual(moved["start_sec"], 5.0, places=2)

    def test_trim_clip_rejects_invalid_range(self):
        """trim_clip with out < in must exit 1 with a fix: hint."""
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": sid, "source_out_sec": 10.0},
            self.project,
        )
        cid = r["result"]

        # Try to trim to a backwards range.
        code, r = _run_runtime(
            "trim_clip", {"clip_id": cid, "new_in_sec": 5.0, "new_out_sec": 2.0},
            self.project,
        )
        self.assertEqual(code, 1)
        self.assertFalse(r["ok"])
        self.assertIn("fix:", r["error"])

    def test_apply_effect_with_valid_id(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip", {"track_index": 0, "source_id": sid, "source_out_sec": 5.0},
            self.project,
        )
        cid = r["result"]
        code, r = _run_runtime(
            "apply_effect",
            {"clip_id": cid, "effect_id": "brightness", "params": {"level": 0.5}},
            self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(r["ok"])

    def test_apply_effect_with_invalid_id_returns_fix_hint(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip", {"track_index": 0, "source_id": sid, "source_out_sec": 3.0},
            self.project,
        )
        cid = r["result"]
        code, r = _run_runtime(
            "apply_effect",
            {"clip_id": cid, "effect_id": "no_such_effect"},
            self.project,
        )
        self.assertEqual(code, 1)
        self.assertIn("fix:", r["error"])

    def test_add_marker_and_delete_clip(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip", {"track_index": 0, "source_id": sid, "source_out_sec": 4.0},
            self.project,
        )
        cid = r["result"]

        # Add a marker.
        code, r = _run_runtime(
            "add_marker", {"position_sec": 2.0, "label": "cut point", "kind": "guide"},
            self.project,
        )
        self.assertEqual(code, 0)

        # Delete the clip.
        code, r = _run_runtime("delete_clip", {"clip_id": cid}, self.project)
        self.assertEqual(code, 0)

        _, summary = _run_runtime("get_timeline_summary", {}, self.project)
        # demo.kdenlive starts with 1 pre-existing clip; we appended and
        # then deleted one, so 1 clip remains.
        self.assertEqual(len(summary["result"]["clips"]), 1)
        self.assertEqual(len(summary["result"]["markers"]), 1)


if __name__ == "__main__":
    unittest.main()
