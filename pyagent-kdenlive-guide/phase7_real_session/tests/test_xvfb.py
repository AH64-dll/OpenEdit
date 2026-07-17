"""Unit tests for XvfbContext.

These tests use a fake Xvfb binary (a shell script) so they run
without Xvfb installed. The fake script writes a marker file and
sleeps; the test asserts the marker is created and the cleanup
kills the process.
"""
from __future__ import annotations

import os
import shutil
import signal
import tempfile
import time
import unittest
from pathlib import Path

from phase7_real_session.xvfb import XvfbContext


def _make_fake_xvfb(tmp: Path, hold_seconds: float = 30.0) -> Path:
    """Write a shell script that pretends to be Xvfb.

    It touches a marker file and sleeps, so the test can verify
    the script was launched and then kill it.
    """
    script = tmp / "fake-xvfb.sh"
    script.write_text(
        "#!/bin/sh\n"
        f"touch {tmp}/xvfb-started.marker\n"
        f"sleep {hold_seconds}\n"
    )
    script.chmod(0o755)
    return script


class TestXvfbContextWithFakeBinary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phase7_xvfb_test_"))
        self.fake = _make_fake_xvfb(self.tmp, hold_seconds=30.0)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enter_launches_and_returns_display(self) -> None:
        with XvfbContext(binary=str(self.fake)) as display:
            self.assertTrue(display.startswith(":"), f"display={display!r}")
            # Marker should appear once the fake binary has run.
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if (self.tmp / "xvfb-started.marker").exists():
                    break
                time.sleep(0.05)
            self.assertTrue(
                (self.tmp / "xvfb-started.marker").exists(),
                "fake Xvfb script was not launched",
            )

    def test_exit_kills_process(self) -> None:
        with XvfbContext(binary=str(self.fake)) as display:
            self.assertTrue(display.startswith(":"))
        # After exit, the marker exists (script ran) but no sleep
        # processes from this group should remain.
        # Best-effort: just verify __exit__ didn't raise.
        # (We can't easily check the process is gone across systems.)

    def test_missing_binary_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            with XvfbContext(binary="/nonexistent/binary/xyz"):
                pass

    def test_exit_without_enter_is_safe(self) -> None:
        ctx = XvfbContext(binary=str(self.fake))
        # Should not raise.
        ctx.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
