"""Tests for the project-state snapshot helpers."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase4_chat_ui import state as project_state  # noqa: E402

FIXTURE = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "demo.kdenlive"
CATALOG = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "catalog.json"


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "work.kdenlive")
        with open(FIXTURE, "rb") as src, open(self.project, "wb") as dst:
            dst.write(src.read())

    def test_get_project_info_returns_dict(self):
        info = project_state.get_project_info(self.project, str(CATALOG))
        self.assertIsNotNone(info)
        self.assertEqual(info["width"], 1920)
        self.assertEqual(info["height"], 1080)
        self.assertIn("fps", info)

    def test_get_project_info_missing_file_returns_none(self):
        self.assertIsNone(project_state.get_project_info("/nope.kdenlive"))

    def test_get_timeline_summary_returns_dict(self):
        summary = project_state.get_timeline_summary(self.project, str(CATALOG))
        self.assertIsNotNone(summary)
        self.assertIn("clips", summary)
        self.assertIsInstance(summary["clips"], (list, tuple))

    def test_get_timeline_summary_missing_file_returns_none(self):
        self.assertIsNone(project_state.get_timeline_summary("/nope.kdenlive"))


if __name__ == "__main__":
    unittest.main()
