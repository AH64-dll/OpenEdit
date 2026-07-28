"""Validate that emitted MLT XML loads in melt without errors."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _melt_discard_consumer() -> str:
    """Consumer URI that discards melt output (platform-specific null device)."""
    if os.name == "nt":
        return "xml:NUL"
    return "xml:/dev/null"


def validate_mlt_loads(xml: str, timeout: int = 30) -> tuple[bool, str]:
    """Write the XML to a temp file and run ``melt -consumer xml:<null>``.

    Returns (True, "") if melt exits 0, or (False, last_stderr_line) otherwise.
    """
    melt = shutil.which("melt")
    if melt is None:
        return False, "melt not on PATH"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mlt", delete=False
    ) as f:
        f.write(xml)
        path = f.name
    try:
        result = subprocess.run(
            [melt, path, "-consumer", _melt_discard_consumer()],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"melt timed out after {timeout}s"
    finally:
        Path(path).unlink(missing_ok=True)

    if result.returncode == 0:
        return True, ""
    last = (result.stderr or "").strip().splitlines()
    return False, last[-1] if last else f"melt exited {result.returncode}"
