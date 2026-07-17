"""ChatUIServer — launch the phase4 chat UI and wait for it to serve HTTP.

The `command` argument is injectable for unit tests. In production
it defaults to `python3 -m phase4_chat_ui --project <p> --port <port>
--provider <provider> --model <model>`.

The `port` argument: if 0 (the default), a free port is picked and
used in the spawned command. If nonzero, that port is used in the
spawned command and the healthcheck. Tests can pass a known port
to point the healthcheck at a fixture server.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from typing import Optional


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ChatUIServer:
    """Launch the chat UI in a subprocess, wait for it to be ready."""

    def __init__(
        self,
        project_path: str,
        display: str,
        provider: str = "opencode",
        model: str = "minimax-m3",
        timeout: float = 15.0,
        port: int = 0,
        command: Optional[list] = None,
    ) -> None:
        self._project_path = project_path
        self._display = display
        self._provider = provider
        self._model = model
        self._timeout = timeout
        if port == 0:
            port = _pick_free_port()
        self._port = port
        self._command = command if command is not None else [
            "python3", "-m", "phase4_chat_ui",
            "--project", project_path,
            "--port", str(port),
            "--provider", provider,
            "--model", model,
        ]
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_path: Optional[str] = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _spawn(self) -> None:
        env = dict(os.environ)
        env["DISPLAY"] = self._display
        self._stderr_path = os.path.join(
            os.path.dirname(self._project_path) or ".",
            "chat_ui.stderr",
        )
        stderr_fp = open(self._stderr_path, "w")
        self._proc = subprocess.Popen(
            self._command,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr_fp,
            preexec_fn=os.setsid,
        )

    def wait_ready(self) -> None:
        """Spawn the chat UI and block until /api/project returns 200."""
        if self._proc is None:
            self._spawn()
        deadline = time.time() + self._timeout
        last_err: Optional[Exception] = None
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    f"chat UI exited unexpectedly with code "
                    f"{self._proc.returncode}; see {self._stderr_path}"
                )
            try:
                with urllib.request.urlopen(
                    f"{self.url}/api/project", timeout=1.0
                ) as resp:
                    if resp.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_err = e
            time.sleep(0.2)
        raise RuntimeError(
            f"chat UI did not become ready within {self._timeout}s: {last_err}"
        )

    def terminate(self) -> None:
        """SIGTERM, then SIGKILL after 5s. Safe to call multiple times."""
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
