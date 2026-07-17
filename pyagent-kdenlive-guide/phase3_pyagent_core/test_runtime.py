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


if __name__ == "__main__":
    unittest.main()
