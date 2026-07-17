"""Unit tests for WSClient.

We use a local websockets server fixture that echoes a fixed
event stream when it receives a prompt.
"""
from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import unittest

from phase7_real_session.ws_client import WSClient


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _echo_handler(websocket) -> None:
    """Receive a 'prompt' message, send a canned event stream + done."""
    async for msg in websocket:
        data = json.loads(msg)
        if data.get("type") == "prompt":
            # Send a small event stream.
            await websocket.send(json.dumps({
                "type": "message", "role": "user", "text": data["text"]
            }))
            await websocket.send(json.dumps({
                "type": "tool", "tool": "pyagent_add_transition",
                "args": {"kind": "dissolve", "duration_sec": 1.0},
                "result": {"ok": True},
            }))
            await websocket.send(json.dumps({
                "type": "message", "role": "assistant",
                "text": "Added a 1-second dissolve.",
            }))
            await websocket.send(json.dumps({"type": "done"}))


def _start_ws_server() -> tuple[object, int]:
    """Start a websockets server in a thread. Returns (server, port)."""
    import websockets
    port = _pick_free_port()
    stop_event = threading.Event()

    async def _runner():
        async with websockets.serve(_echo_handler, "127.0.0.1", port):
            await asyncio.get_event_loop().create_future()
            # The serve() call blocks; we never return from here.
            # The thread is daemonized so the test process can exit
            # even if we don't reach the stop_event branch.

    t = threading.Thread(
        target=lambda: asyncio.run(_runner()), daemon=True
    )
    t.start()
    # Wait for the server to bind.
    time.sleep(0.2)
    return None, port  # server handle is None; we rely on daemon thread


class TestWSClient(unittest.TestCase):
    def test_run_prompt_collects_events(self) -> None:
        _, port = _start_ws_server()
        ws = WSClient(url=f"ws://127.0.0.1:{port}/ws", timeout=5.0)
        events = ws.run_prompt_sync("Add a 1-second dissolve.")
        kinds = [e.get("type") for e in events]
        self.assertIn("message", kinds)
        self.assertIn("tool", kinds)
        self.assertEqual(kinds[-1], "done")
        # Find the tool event and assert the args.
        tool_events = [e for e in events if e.get("type") == "tool"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0]["tool"], "pyagent_add_transition")
        self.assertEqual(tool_events[0]["args"]["kind"], "dissolve")

    def test_run_prompt_raises_on_timeout(self) -> None:
        # Use a port that's not listening.
        port = _pick_free_port()
        ws = WSClient(url=f"ws://127.0.0.1:{port}/ws", timeout=1.0)
        with self.assertRaises((ConnectionError, OSError, RuntimeError)):
            ws.run_prompt_sync("anything")


if __name__ == "__main__":
    unittest.main()
