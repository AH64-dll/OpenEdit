"""Detect a running Kdenlive instance and its D-Bus service name."""
from __future__ import annotations

import shutil
import subprocess


def is_running() -> bool:
    """True if `pgrep` finds a kdenlive process."""
    if shutil.which("pgrep") is None:
        return False
    r = subprocess.run(
        ["pgrep", "-x", "kdenlive"],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def detect_service_name() -> str | None:
    """Return the actual D-Bus service name (e.g. `org.kde.kdenlive-2046260`)
    by listing bus names via `busctl`, or None if not found."""
    if shutil.which("busctl") is None:
        # Common fallback: the well-known name.
        return "org.kde.kdenlive" if is_running() else None
    r = subprocess.run(
        ["busctl", "--user", "list"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return "org.kde.kdenlive" if is_running() else None
    for line in r.stdout.splitlines():
        if "org.kde.kdenlive" in line:
            # busctl list format: first column is the service name.
            return line.split()[0]
    return None
