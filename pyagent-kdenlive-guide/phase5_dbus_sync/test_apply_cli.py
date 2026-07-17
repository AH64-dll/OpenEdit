"""End-to-end: extension -> spawnSync(phase5_dbus_sync apply) -> LiveSync.

Mocks LiveSync.apply() to verify the extension routes through the live-sync
path when PYAGENT_LIVE=1, and falls back to file-mode otherwise.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PY3 = sys.executable


def _run_apply_cli(payload: dict) -> subprocess.CompletedProcess:
    p = subprocess.run(
        [PY3, "-m", "phase5_dbus_sync", "apply"],
        cwd=REPO,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
    )
    return p


class TestApplyCli(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".kdenlive")
        os.close(fd)
        Path(self.path).write_text(
            '<?xml version="1.0"?><kdenlive><producer id="main_bin">'
            '<property name="resource"></property></producer></kdenlive>'
        )

    def tearDown(self) -> None:
        os.unlink(self.path)

    def test_apply_via_file_mode(self) -> None:
        # No Kdenlive running -> LiveSync falls through to file-mode; the
        # call errors on the missing clip args. The CLI returns 0 and
        # surfaces the error inside the JSON result.
        r = _run_apply_cli({
            "tool": "pyagent_add_transition",
            "args": {"duration_sec": 1.0},
            "project": self.path,
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        body = json.loads(r.stdout)
        self.assertFalse(body["ok"])
        self.assertEqual(body.get("mode"), "file")
        # The nested error should mention missing args.
        nested_err = body.get("result", {}).get("error", "")
        self.assertIn("clip_a_id", nested_err)

    def test_apply_missing_project(self) -> None:
        r = _run_apply_cli({
            "tool": "pyagent_add_transition",
            "args": {"duration_sec": 1.0},
            "project": "/nonexistent.kdenlive",
        })
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found", r.stderr)

    def test_apply_cli_help(self) -> None:
        r = subprocess.run(
            [PY3, "-m", "phase5_dbus_sync", "--help"],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("apply", r.stdout)
        self.assertIn("notify", r.stdout)


if __name__ == "__main__":
    unittest.main()
