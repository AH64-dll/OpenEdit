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


if __name__ == "__main__":
    unittest.main()
