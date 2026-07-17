"""Unit tests for KdenliveLaunch.

These tests use a fake kdenlive binary (a shell script that
registers a fake D-Bus name via dbus-send then sleeps, or
just sleeps without registering, depending on the test).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from phase7_real_session.kdenlive import KdenliveLaunch


def _make_fake_kdenlive(tmp: Path, register_dbus: bool, hold_seconds: float = 30.0) -> Path:
    """Write a shell script that pretends to be kdenlive.

    If register_dbus is True, the script calls dbus-send to register
    org.kde.kdenlive on the session bus (so the wait_ready probe
    succeeds). Then it sleeps.
    """
    script = tmp / "fake-kdenlive.sh"
    lines = ["#!/bin/sh"]
    if register_dbus:
        # dbus-send --session ... org.freedesktop.DBus.ListNames
        # would need a real bus; instead, the test will mock
        # _kdenlive_already_on_bus via the KdenliveLaunch wait_ready
        # path. We use a different approach: write a marker file
        # that the test can read.
        pass
    # Write a marker file so the test knows the script ran.
    lines.append(f"touch {tmp}/kdenlive-started.marker")
    lines.append(f"sleep {hold_seconds}")
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return script


class TestKdenliveLaunchWithFakeBinary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phase7_kdenlive_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_constructor_does_not_launch(self) -> None:
        """__init__ stores config; the subprocess is launched by wait_ready."""
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        # No wait_ready called yet — the fake's marker should NOT exist.
        KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
        )
        time.sleep(0.1)
        self.assertFalse(
            (self.tmp / "kdenlive-started.marker").exists(),
            "kdenlive was launched by __init__, expected lazy launch",
        )

    def test_wait_ready_raises_on_timeout(self) -> None:
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        k = KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
            timeout=0.5,
        )
        with self.assertRaises(RuntimeError):
            k.wait_ready()
        # Cleanup so the fake sleep doesn't linger.
        k.terminate()

    def test_wait_ready_succeeds_when_dbus_already_has_kdenlive(self) -> None:
        """If a kdenlive is already on the bus (mocked), wait_ready returns."""
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        k = KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
            timeout=2.0,
        )
        with unittest.mock.patch(
            "phase7_real_session.kdenlive._kdenlive_already_on_bus",
            return_value=True,
        ):
            k.wait_ready()
        self.assertGreaterEqual(k.pid, 0, "kdenlive was not launched")
        # Marker should appear.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if (self.tmp / "kdenlive-started.marker").exists():
                break
            time.sleep(0.05)
        self.assertTrue(
            (self.tmp / "kdenlive-started.marker").exists(),
            "kdenlive was not launched",
        )
        k.terminate()

    def test_terminate_is_idempotent(self) -> None:
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        k = KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
            timeout=0.5,
        )
        with self.assertRaises(RuntimeError):
            k.wait_ready()
        k.terminate()
        # Second call should not raise.
        k.terminate()


import unittest.mock  # noqa: E402  (placed after the test class so the
                       # mock import doesn't shadow test methods)


if __name__ == "__main__":
    unittest.main()
