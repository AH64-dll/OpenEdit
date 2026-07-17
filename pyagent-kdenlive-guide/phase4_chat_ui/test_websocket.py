"""WebSocket integration test: a prompt flows through to tool + state events.

Uses a fake `pi` binary (no model access) patched into PiClient so the full
WebSocket handler path is exercised.
"""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

FIXTURE = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "demo.kdenlive"
CATALOG = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "catalog.json"
FAKE_PI = str(_REPO_ROOT / "phase4_chat_ui" / "tests" / "fake_pi.py")


class TestWebSocket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "work.kdenlive")
        with open(FIXTURE, "rb") as src, open(self.project, "wb") as dst:
            dst.write(src.read())

        from phase4_chat_ui import pi_client
        orig_init = pi_client.PiClient.__init__
        self._orig_init = orig_init  # type: ignore

        def _patched_init(self, provider, model, project, binary=None, pi_args=None):
            orig_init(
                self, provider, model, project,
                binary=binary or FAKE_PI,
                pi_args=pi_args if pi_args is not None else [FAKE_PI],
            )
            return

        pi_client.PiClient.__init__ = _patched_init  # type: ignore

        from phase4_chat_ui.app import create_app
        self.app = create_app(
            project=self.project, provider="x", model="y",
            pi_binary=FAKE_PI, catalog=str(CATALOG),
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        import phase4_chat_ui.pi_client as pc
        pc.PiClient.__init__ = self._orig_init  # type: ignore

    def test_prompt_yields_tool_and_state(self):
        with self.client.websocket_connect("/ws") as ws:
            # First messages: project + state snapshot.
            hello = ws.receive_json()
            self.assertEqual(hello["type"], "project")
            state0 = ws.receive_json()
            self.assertEqual(state0["type"], "state")

            # Send a prompt.
            ws.send_json({"type": "prompt", "text": "hi"})

            # Collect until we see a tool event, then a post-run state refresh.
            seen_tool = False
            seen_state_after = False
            for _ in range(20):
                msg = ws.receive_json()
                if msg["type"] == "tool":
                    seen_tool = True
                # The post-run broadcast sends the project info snapshot.
                if seen_tool and msg["type"] == "state" and "name" in msg:
                    seen_state_after = True
                    break

            self.assertTrue(seen_tool, "expected a tool event in the stream")
            self.assertTrue(seen_state_after, "expected a state refresh after run")


if __name__ == "__main__":
    unittest.main()
