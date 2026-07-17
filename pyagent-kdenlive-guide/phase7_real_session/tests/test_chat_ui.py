"""Unit tests for ChatUIServer.

We use a tiny HTTP server fixture (http.server in a thread) that
responds 200 to GET /api/project, instead of launching the real
phase4_chat_ui. This is what the `command` injection is for.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from phase7_real_session.chat_ui import ChatUIServer


class _FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path == "/api/project":
            body = json.dumps({"name": "demo", "duration": 6.0}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs) -> None:  # silence stderr noise
        pass


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_fake_server() -> tuple[HTTPServer, int]:
    port = _pick_free_port()
    server = HTTPServer(("127.0.0.1", port), _FakeHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Tiny sleep so the socket is actually listening.
    time.sleep(0.05)
    return server, port


class TestChatUIServerHappyPath(unittest.TestCase):
    def setUp(self) -> None:
        self._server, self._port = _start_fake_server()

    def tearDown(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def test_wait_ready_succeeds(self) -> None:
        # The "chat UI" here is just the fake server — we tell the
        # ChatUIServer to launch a no-op `sleep 5` command so it
        # spawns a real subprocess, but the wait_ready probe hits
        # the fake server we started in setUp.
        #
        # We give the server's port to ChatUIServer so its
        # healthcheck targets it. We use a dummy `sleep 5` as the
        # "command" so the spawn doesn't error.
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=self._port,
            command=["sleep", "5"],
            timeout=2.0,
        )
        cu.wait_ready()
        self.assertEqual(cu.port, self._port)
        self.assertEqual(cu.url, f"http://127.0.0.1:{self._port}")
        cu.terminate()

    def test_pick_free_port_when_zero(self) -> None:
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=0,  # pick one
            command=["sleep", "5"],
            timeout=1.0,
        )
        self.assertGreater(cu.port, 0)
        self.assertEqual(cu.url, f"http://127.0.0.1:{cu.port}")
        # Don't call wait_ready — we'd need a server on that port.
        # Just verify construction worked.

    def test_terminate_is_idempotent(self) -> None:
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=self._port,
            command=["sleep", "5"],
            timeout=2.0,
        )
        cu.wait_ready()
        cu.terminate()
        cu.terminate()  # second call must not raise


class TestChatUIServerTimeout(unittest.TestCase):
    def test_wait_ready_times_out(self) -> None:
        # Port that's not listening: pick a free port and don't start a server.
        port = _pick_free_port()
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=port,
            command=["sleep", "5"],
            timeout=0.5,
        )
        with self.assertRaises(RuntimeError):
            cu.wait_ready()
        cu.terminate()


if __name__ == "__main__":
    unittest.main()
