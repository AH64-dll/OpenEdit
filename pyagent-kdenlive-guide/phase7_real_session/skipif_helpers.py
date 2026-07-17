"""Skipif helpers used by test_e2e_pi_session.py.

These functions are intentionally side-effect-light: they check
whether a dependency is present without launching anything heavy.
Each function is the body of a `@unittest.skipUnless` /
`@unittest.skipIf` decorator on the e2e test class.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _has(name: str) -> bool:
    """True if `name` is on PATH."""
    return shutil.which(name) is not None


def _has_opencode_auth() -> bool:
    """True if pi can authenticate with the opencode provider.

    Accepts either OPENCODE_API_KEY in the environment, or a
    stored auth file at ~/.pi/agent/auth.json (the file pi
    creates after `/login` via OAuth).
    """
    if os.environ.get("OPENCODE_API_KEY"):
        return True
    auth_file = Path.home() / ".pi" / "agent" / "auth.json"
    return auth_file.is_file()


def _kdenlive_already_on_bus() -> bool:
    """True if a kdenlive is already registered on the session D-Bus.

    The test must skip in this case because the D-Bus name
    `org.kde.kdenlive` is global — our launched Kdenlive would
    collide with the user's Kdenlive, and the test's D-Bus
    probes would talk to the wrong instance.
    """
    try:
        out = subprocess.run(
            ["dbus-send", "--session", "--print-reply",
             "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus",
             "org.freedesktop.DBus.ListNames"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return "kdenlive" in (out.stdout or "").lower()
