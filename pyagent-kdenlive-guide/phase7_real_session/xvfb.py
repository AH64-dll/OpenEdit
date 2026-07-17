"""XvfbContext — start a virtual X display for headless Kdenlive.

The context manager picks the lowest free display in
[min_display, max_display] and starts Xvfb there. On exit, it
sends SIGTERM to the Xvfb process group; if the process is still
alive 5 seconds later, it sends SIGKILL.

The `binary` argument is injectable so unit tests can run a fake
script. In production it defaults to "Xvfb".
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from typing import Optional


class XvfbContext:
    """Context manager wrapping a virtual X display.

    Usage:
        with XvfbContext() as display:
            os.environ["DISPLAY"] = display
            launch_kdenlive(...)

    The `binary` parameter lets tests substitute a fake script.
    """

    def __init__(
        self,
        min_display: int = 99,
        max_display: int = 199,
        binary: str = "Xvfb",
    ) -> None:
        self._min = min_display
        self._max = max_display
        self._binary = binary
        self._proc: Optional[subprocess.Popen] = None
        self._display: str = ""

    @property
    def display(self) -> str:
        """The display string (e.g. ':99'), or '' if not entered."""
        return self._display

    def __enter__(self) -> str:
        if shutil.which(self._binary) is None and not os.path.isfile(self._binary):
            raise RuntimeError(
                f"Xvfb binary not found: {self._binary!r}. "
                f"Install xorg-server-xvfb (Arch) or xvfb (Debian/Ubuntu)."
            )
        last_err: Optional[Exception] = None
        for n in range(self._min, self._max + 1):
            display = f":{n}"
            argv = [self._binary, display, "-ac", "-screen", "0", "1024x768x24"]
            try:
                self._proc = subprocess.Popen(
                    argv,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,  # new process group
                )
            except FileNotFoundError as e:
                last_err = e
                continue
            except OSError as e:
                last_err = e
                continue
            # Give Xvfb a moment to bind the display. 200ms is enough
            # for the real Xvfb; the fake script just sleeps so we
            # can't probe its socket — we trust the Popen succeeded.
            time.sleep(0.2)
            if self._proc.poll() is None:
                self._display = display
                return display
            last_err = RuntimeError(f"Xvfb exited on {display}")
        raise RuntimeError(
            f"No free display in [{self._min}, {self._max}]: {last_err}"
        )

    def __exit__(self, *exc) -> None:
        if self._proc is None:
            return
        proc = self._proc
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
        finally:
            self._proc = None
            self._display = ""
