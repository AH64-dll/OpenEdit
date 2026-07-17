"""End-to-end test: spawn `pi --mode rpc`, drive a 2-turn conversation.

Skipped if no LLM provider is configured (no API key env var set).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROVIDER_KEYS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GROQ_API_KEY", "OPENROUTER_API_KEY", "ZAI_API_KEY",
    "MISTRAL_API_KEY", "DEEPSEEK_API_KEY",
)


def has_provider() -> bool:
    return any(os.environ.get(k) for k in PROVIDER_KEYS)


SKIP_REASON = (
    "no LLM provider configured; set one of "
    + ", ".join(PROVIDER_KEYS)
    + " to enable the integration test"
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / "phase3_pyagent_core"
TESTDATA = REPO_ROOT / "testdata" / "clip_short.mp4"
FIXTURE_PROJECT = RUNTIME_DIR / "tests" / "fixtures" / "demo.kdenlive"


@unittest.skipUnless(has_provider(), SKIP_REASON)
class TestPiIntegration(unittest.TestCase):
    """Drive pi --mode rpc and verify the LLM chains the right tools."""

    def setUp(self):
        if not TESTDATA.exists():
            self.skipTest(f"test clip missing: {TESTDATA}")
        if not FIXTURE_PROJECT.exists():
            self.skipTest(f"fixture missing: {FIXTURE_PROJECT}")
        # Copy the fixture to a temp file so the test is hermetic.
        self.tmpdir = tempfile.mkdtemp()
        self.project = str(Path(self.tmpdir) / "integration.kdenlive")
        FIXTURE_PROJECT.read_bytes() and (
            Path(self.project).write_bytes(FIXTURE_PROJECT.read_bytes())
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_crossfade_chain_runs_end_to_end(self):
        """The spec's headline acceptance test: 'add these two clips with a
        crossfade' should chain import_media -> append_clip x 2 ->
        add_transition."""
        env = os.environ.copy()
        env["PYAGENT_PROJECT"] = self.project
        env["PYAGENT_AUTO_APPROVE"] = "true"  # skip the confirm dialog
        env["PI_OFFLINE"] = "0"  # ensure pi makes network calls

        proc = subprocess.Popen(
            ["pi", "--mode", "rpc", "--no-session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

        try:
            # Wait for pi to be ready (emits initial state).
            # We do this by reading the first event.
            # ... (a real implementation would parse JSONL events; for the
            # skeleton we send the prompt and then poll for the tool call
            # sequence in the event stream).

            prompt = (
                f"Use the pyagent_* tools to import the file at "
                f"{TESTDATA}, append it twice to track 0, and add a 1-second "
                f"composite transition between the two resulting clips. "
                f"After that, call pyagent_save_project with no args."
            )
            proc.stdin.write(json.dumps({"type": "prompt", "message": prompt}) + "\n")
            proc.stdin.flush()

            # Poll for events. Look for tool_execution_start events with
            # toolName pyagent_*. Collect the sequence.
            seen_tools: list[str] = []
            deadline = time.time() + 120  # 2 min max
            while time.time() < deadline and proc.poll() is None:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "tool_execution_start":
                    seen_tools.append(ev.get("toolName", "?"))
                if ev.get("type") == "agent_end":
                    break

            # Verify the tool chain includes the expected ops in order.
            # (The LLM may also call list_catalog or get_timeline_summary
            # along the way; we check that the critical 4 are present and
            # in the right order.)
            for required in ("pyagent_import_media",
                             "pyagent_append_clip",
                             "pyagent_append_clip",
                             "pyagent_add_transition",
                             "pyagent_save_project"):
                self.assertIn(required, seen_tools,
                              f"missing {required} in tool chain: {seen_tools}")
            # The append_clips should both come before add_transition.
            append_indices = [i for i, t in enumerate(seen_tools)
                              if t == "pyagent_append_clip"]
            trans_idx = seen_tools.index("pyagent_add_transition")
            self.assertEqual(len(append_indices), 2)
            self.assertLess(max(append_indices), trans_idx,
                            f"add_transition before both appends: {seen_tools}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
