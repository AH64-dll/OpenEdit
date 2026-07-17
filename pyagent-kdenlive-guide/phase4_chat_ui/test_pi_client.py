"""Tests for PiClient using a fake `pi` binary (no model access)."""
import asyncio
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase4_chat_ui.pi_client import PiClient, PiEvent  # noqa: E402
from phase4_chat_ui.session import Session  # noqa: E402

FAKE_PI = str(_REPO_ROOT / "phase4_chat_ui" / "tests" / "fake_pi.py")


class TestPiClient(unittest.TestCase):
    def setUp(self):
        self.client = PiClient(
            provider="x", model="y", project="/tmp/none.kdenlive",
            binary=FAKE_PI, session_id="test", pi_args=[],
        )

    def _run(self, text):
        events = []
        async def go():
            async for ev in self.client.run_prompt(text):
                events.append(ev)
        asyncio.run(go())
        return events

    def test_emits_assistant_message(self):
        events = self._run("hello")
        msgs = [e for e in events if e.kind == "message" and e.role == "assistant"]
        self.assertTrue(msgs)
        self.assertIn("Echo: hello", msgs[-1].text)

    def test_emits_tool_event(self):
        events = self._run("hello")
        tools = [e for e in events if e.kind == "tool"]
        self.assertTrue(tools)
        self.assertEqual(tools[0].tool, "pyagent_get_project_info")
        self.assertEqual(tools[0].result["name"], "demo")

    def test_emits_done_event(self):
        events = self._run("hello")
        self.assertTrue(any(e.kind == "done" for e in events))

    def test_session_records_tool_event(self):
        s = Session()
        events = self._run("hi")
        for e in events:
            if e.kind == "tool":
                s.add_tool_event(e.tool or "t", e.args or {}, e.result)
        self.assertEqual(len([m for m in s.history if m.role == "tool"]), 1)


if __name__ == "__main__":
    unittest.main()
