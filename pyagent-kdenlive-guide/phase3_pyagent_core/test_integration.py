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
    "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "OPENCODE_API_KEY",
)


def has_provider() -> bool:
    return any(os.environ.get(k) for k in PROVIDER_KEYS)


SKIP_REASON = (
    "no LLM provider configured; set one of "
    + ", ".join(PROVIDER_KEYS)
    + " to enable the integration test"
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "phase3_pyagent_core"
TESTDATA = REPO_ROOT.parent / "testdata" / "clip_short.mp4"
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
        add_transition -> save.

        Note on multi-turn: minimax-m3 (and many smaller models) reliably
        do ONE tool call per turn and wait for follow-up. Real users
        nudge with "continue" between turns. The test mirrors that
        realistic interaction by sending a follow-up prompt if the
        chain is incomplete after the first turn."""
        env = os.environ.copy()
        env["PYAGENT_PROJECT"] = self.project
        env["PYAGENT_AUTO_APPROVE"] = "true"  # skip the confirm dialog
        env["PI_OFFLINE"] = "0"  # ensure pi makes network calls

        proc = subprocess.Popen(
            ["pi", "--mode", "rpc", "--no-session",
             "--provider", "opencode-go", "--model", "minimax-m3",
             "--thinking", "off"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

        def drain_events(deadline_s: float) -> list[str]:
            """Read JSONL events until agent_end or deadline. Return the
            sequence of pyagent_* tool names that were started."""
            seen: list[str] = []
            deadline = time.time() + deadline_s
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
                    name = ev.get("toolName", "?")
                    if name.startswith("pyagent_"):
                        seen.append(name)
                if ev.get("type") == "agent_end":
                    break
            return seen

        def send_prompt(msg: str) -> None:
            proc.stdin.write(json.dumps({"type": "prompt", "message": msg}) + "\n")
            proc.stdin.flush()

        REQUIRED = [
            "pyagent_import_media",
            "pyagent_append_clip",
            "pyagent_add_transition",
            "pyagent_save_project",
        ]

        try:
            # Turn 1: the full spec prompt.
            send_prompt(
                f"Use the pyagent_* tools to import the file at {TESTDATA}, "
                f"append it twice to track 0, and add a 1-second composite "
                f"transition between the two resulting clips. After that, "
                f"call pyagent_save_project with no args."
            )
            seen_tools = drain_events(180)

            # Multi-turn nudge: if the LLM stopped early, prompt it to
            # continue. Up to 3 follow-ups.
            for nudge in range(3):
                missing = [r for r in REQUIRED if r not in seen_tools]
                if not missing:
                    break
                if seen_tools.count("pyagent_append_clip") < 2 and "pyagent_append_clip" in missing:
                    # Need a second append; the LLM needs the first
                    # import's source id to do that, which it has.
                    msg = (
                        f"Continue. You still need to call: "
                        f"{', '.join(missing)}. "
                        f"You have the source id from your earlier import_media. "
                        f"Use it for both append_clips."
                    )
                else:
                    msg = f"Continue. Still needed: {', '.join(missing)}."
                send_prompt(msg)
                seen_tools.extend(drain_events(120))

            # Verify the tool chain includes the expected ops.
            # The LLM may also call get_timeline_summary, list_catalog, etc.;
            # we only require the critical 4 plus 2 appends.
            for required in REQUIRED:
                self.assertIn(required, seen_tools,
                              f"missing {required} in chain: {seen_tools}")
            self.assertGreaterEqual(
                seen_tools.count("pyagent_append_clip"), 2,
                f"expected 2 append_clips, got {seen_tools}",
            )
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
