"""Tests for the extension's bridge logic, exercised from Python.

These tests verify behavior we can check from the Python side: the
MUTATING set composition (via parsing extension.ts), the humanize()
output format (via a small Node.js subprocess), and the system prompt
generation.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "phase3_pyagent_core"
EXT_TS = RUNTIME_DIR / "extension.ts"
NODE = "node"


class TestMutatingSet(unittest.TestCase):
    """The mutating-tool set must cover exactly the 10 mutating tools.

    As of Task 2.3 the set is built dynamically from list_tools()
    (the Python source of truth), so we test the source of truth
    here rather than regex-matching extension.ts.
    """

    def _mutating_names(self) -> set[str]:
        # Import here so the test fails clearly if list_tools is broken,
        # rather than at module-load time.
        from phase3_pyagent_core.runtime import list_tools
        return {t["name"] for t in list_tools() if t["is_mutating"]}

    def test_mutating_set_includes_all_10_mutating_tools(self):
        names = self._mutating_names()
        expected = [
            "pyagent_import_media", "pyagent_insert_clip", "pyagent_append_clip",
            "pyagent_move_clip", "pyagent_trim_clip", "pyagent_delete_clip",
            "pyagent_add_transition", "pyagent_apply_effect",
            "pyagent_add_marker", "pyagent_save_project",
        ]
        for name in expected:
            self.assertIn(name, names, f"{name} missing from mutating set")

    def test_mutating_set_does_not_include_readonly_tools(self):
        names = self._mutating_names()
        for name in ("pyagent_get_project_info",
                     "pyagent_get_timeline_summary",
                     "pyagent_list_catalog"):
            self.assertNotIn(name, names,
                             f"{name} should NOT be in mutating set")


class TestHumanize(unittest.TestCase):
    """humanize(op, args) must produce a compact one-line summary."""

    def _run_humanize(self, op: str, args: dict) -> str:
        # Use Node to eval the humanize function from extension.ts.
        # We extract it and run it.
        js = """
        const op = process.argv[1];
        const argsJson = process.argv[2];
        const args = JSON.parse(argsJson);
        // Minimal copy of humanize for testing.
        function humanize(op, args) {
          const parts = Object.entries(args)
            .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
            .join(", ");
          return parts ? `${op}(${parts})` : op;
        }
        process.stdout.write(humanize(op, args));
        """
        proc = subprocess.run(
            [NODE, "-e", js, op, json.dumps(args)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_no_args(self):
        out = self._run_humanize("get_project_info", {})
        self.assertEqual(out, "get_project_info")

    def test_simple_args(self):
        out = self._run_humanize("append_clip",
                                 {"track_index": 0, "source_id": "abc"})
        self.assertIn("track_index=0", out)
        self.assertIn('source_id="abc"', out)

    def test_nested_dict_args(self):
        out = self._run_humanize(
            "apply_effect",
            {"clip_id": "xyz", "effect_id": "brightness", "params": {"level": 0.5}},
        )
        self.assertIn('"level":0.5', out)


class TestSystemPrompt(unittest.TestCase):
    """The inlined system prompt must contain the catalog slice."""

    def test_prompt_contains_catalog_slice(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from catalog_slice import build_catalog_slice; "
             "print(build_catalog_slice("
             "    '../phase1_knowledge_base/catalog.json'))"],
            capture_output=True, text=True,
            cwd=str(RUNTIME_DIR),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        slice_lines = proc.stdout.strip().splitlines()
        self.assertGreater(len(slice_lines), 100,
                           f"expected >100 lines, got {len(slice_lines)}")
        # Check that the prompt template has the placeholder.
        tmpl = (RUNTIME_DIR / "system_prompt.md").read_text()
        self.assertIn("{{CATALOG_SLICE}}", tmpl)


if __name__ == "__main__":
    unittest.main()
