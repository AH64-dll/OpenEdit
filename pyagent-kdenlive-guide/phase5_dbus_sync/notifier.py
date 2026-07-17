"""Desktop notification via notify-send. No-op if unavailable."""
from __future__ import annotations

import shutil
import subprocess


def notify(title: str, body: str, urgency: str = "normal") -> None:
    """Shell out to `notify-send`. Returns silently if not available."""
    if shutil.which("notify-send") is None:
        return
    try:
        subprocess.run(
            ["notify-send", f"--urgency={urgency}", title, body],
            check=False, timeout=5,
        )
    except Exception:
        pass
