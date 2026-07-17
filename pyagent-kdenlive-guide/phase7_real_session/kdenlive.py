"""KdenliveLaunch — launch Kdenlive in a virtual display and wait for D-Bus.

The launch is lazy: __init__ stores config, and wait_ready() is what
actually spawns the subprocess and probes D-Bus. This lets tests
verify "no launch happens until wait_ready is called".

The `binary` argument is injectable for unit tests. In production
it defaults to "kdenlive".
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from typing import Optional

from phase7_real_session.skipif_helpers import _kdenlive_already_on_bus


class KdenliveLaunch:
    """Launch kdenlive in a given DISPLAY, opening a project file.

    Usage:
        k = KdenliveLaunch(project_path, display=display,
                           xdg_config_home=tmp/.config,
                           xdg_cache_home=tmp/.cache)
        k.wait_ready()        # blocks up to timeout
        ...
        k.terminate()         # SIGTERM, then SIGKILL
    """

    def __init__(
        self,
        project_path: str,
        display: str,
        xdg_config_home: str,
        xdg_cache_home: str,
        timeout: float = 30.0,
        binary: str = "kdenlive",
    ) -> None:
        self._project_path = project_path
        self._display = display
        self._xdg_config_home = xdg_config_home
        self._xdg_cache_home = xdg_cache_home
        self._timeout = timeout
        self._binary = binary
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_path: Optional[str] = None

    @property
    def pid(self) -> int:
        """The kdenlive pid, or -1 if not started."""
        if self._proc is None:
            return -1
        return self._proc.pid

    def _spawn(self) -> None:
        if shutil.which(self._binary) is None and not os.path.isfile(self._binary):
            raise RuntimeError(
                f"kdenlive binary not found: {self._binary!r}"
            )
        # Make sure the XDG dirs exist (Kdenlive refuses to start
        # without them).
        os.makedirs(self._xdg_config_home, exist_ok=True)
        os.makedirs(self._xdg_cache_home, exist_ok=True)
        env = dict(os.environ)
        env["DISPLAY"] = self._display
        env["XDG_CONFIG_HOME"] = self._xdg_config_home
        env["XDG_CACHE_HOME"] = self._xdg_cache_home
        self._stderr_path = os.path.join(self._xdg_cache_home, "kdenlive.stderr")
        stderr_fp = open(self._stderr_path, "w")
        argv = [self._binary, "--no-splash", self._project_path]
        self._proc = subprocess.Popen(
            argv,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr_fp,
            preexec_fn=os.setsid,
        )

    def wait_ready(self) -> None:
        """Launch Kdenlive and block until org.kde.kdenlive is on the bus.

        Raises RuntimeError on timeout.
        """
        if self._proc is None:
            self._spawn()
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    f"kdenlive exited unexpectedly with code "
                    f"{self._proc.returncode}; see {self._stderr_path}"
                )
            if _kdenlive_already_on_bus():
                return
            time.sleep(0.2)
        raise RuntimeError(
            f"kdenlive did not register on D-Bus within {self._timeout}s; "
            f"see {self._stderr_path}"
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
