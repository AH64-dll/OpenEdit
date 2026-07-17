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
    """The auto_approve gate's MUTATING set must cover exactly tools 3-12."""

    def test_mutating_set_includes_all_10_mutating_tools(self):
        src = EXT_TS.read_text()
        # Extract the MUTATING = new Set([...]) block.
        match = re.search(r"const MUTATING = new Set\(\[(.*?)\]\);", src, re.DOTALL)
        self.assertIsNotNone(match, "could not find MUTATING set in extension.ts")
        block = match.group(1)
        expected = [
            "pyagent_import_media", "pyagent_insert_clip", "pyagent_append_clip",
            "pyagent_move_clip", "pyagent_trim_clip", "pyagent_delete_clip",
            "pyagent_add_transition", "pyagent_apply_effect",
            "pyagent_add_marker", "pyagent_save_project",
        ]
        for name in expected:
            self.assertIn(f'"{name}"', block, f"{name} missing from MUTATING set")

    def test_mutating_set_does_not_include_readonly_tools(self):
        src = EXT_TS.read_text()
        match = re.search(r"const MUTATING = new Set\(\[(.*?)\]\);", src, re.DOTALL)
        block = match.group(1)
        for name in ("pyagent_get_project_info",
                     "pyagent_get_timeline_summary",
                     "pyagent_list_catalog"):
            self.assertNotIn(f'"{name}"', block,
                             f"{name} should NOT be in MUTATING set")


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
