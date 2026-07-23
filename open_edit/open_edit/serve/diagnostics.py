"""System health & diagnostics collection for the open_edit server.

Provides three pure, side-effect-free (no launches, no network) helpers
that an integration agent can wire to ``/health`` and ``/diagnostics``:

* :func:`collect_diagnostics` — full, redacted health snapshot.
* :func:`system_healthy` — permissive boolean liveness check.
* :func:`get_health` — minimal payload for ``/health``.

Every detection is wrapped in try/except: these functions NEVER raise.
Secrets, API keys, and user-identifying absolute paths are never emitted —
only booleans, versions, and coarse info.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path


def _sqlite_ok() -> bool:
    """Return True if an in-memory sqlite connection can round-trip a query."""
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE _t (v INTEGER)")
            conn.execute("INSERT INTO _t (v) VALUES (1)")
            row = conn.execute("SELECT v FROM _t").fetchone()
            return row is not None and row[0] == 1
        finally:
            conn.close()
    except Exception:
        return False


def _mlt_available() -> bool:
    """Best-effort check for MLT: the ``melt`` binary or the python binding."""
    try:
        if shutil.which("melt") is not None:
            return True
    except Exception:
        pass
    try:
        import importlib.util

        return importlib.util.find_spec("mlt") is not None
    except Exception:
        return False


def _chromium_available() -> bool:
    """Best-effort check for the overlay compositor (hyperframes/chromium)."""
    try:
        if os.environ.get("OPEN_EDIT_HYPERFRAMES_BIN", "").strip():
            return True
        if Path("node_modules/.bin/hyperframes").is_file():
            return True
        for binary in ("chromium", "chromium-browser", "google-chrome", "chrome"):
            if shutil.which(binary) is not None:
                return True
    except Exception:
        return False
    return False


def _sandbox_backend() -> str:
    """Return the configured sandbox backend name, or ``"unknown"``.

    The Rust bwrap sandbox has no explicit backend env var; we honour an
    optional ``OPEN_EDIT_SANDBOX_BACKEND`` override and otherwise infer
    ``"bwrap"`` when the sandbox binary is resolvable, falling back to
    ``"dev"`` (the in-process dev fallback) or ``"unknown"``.
    """
    try:
        override = os.environ.get("OPEN_EDIT_SANDBOX_BACKEND", "").strip()
        if override:
            return override
        return "bwrap" if _sandbox_available() else "dev"
    except Exception:
        return "unknown"


def _sandbox_available() -> bool:
    """Best-effort check for the sandbox binary. Never launches a sandbox."""
    try:
        from open_edit.agent import sandbox_bridge

        sandbox_bridge._resolve_sandbox_bin()
        return True
    except Exception:
        return False


def _disk_free_bytes() -> int | None:
    """Return free bytes on the filesystem holding the cwd, or None."""
    try:
        stat = os.statvfs(os.getcwd())
        return stat.f_bavail * stat.f_frsize
    except Exception:
        return None


def _config_summary() -> dict:
    """Return a redacted subset of server config. NEVER includes secrets."""
    summary: dict = {}
    try:
        summary["host"] = os.environ.get("OPEN_EDIT_SERVE_HOST", "0.0.0.0")
    except Exception:
        summary["host"] = None
    try:
        summary["port"] = int(os.environ.get("OPEN_EDIT_SERVE_PORT", "8000"))
    except Exception:
        summary["port"] = None
    try:
        from open_edit.serve.serve_env import get_visual_verify_config

        summary["verify_enabled"] = bool(get_visual_verify_config()["enabled"])
    except Exception:
        summary["verify_enabled"] = None
    try:
        from open_edit.serve import cli_adapter

        summary["providers"] = cli_adapter.list_adapters()
    except Exception:
        summary["providers"] = []
    return summary


def collect_diagnostics() -> dict:
    """Return a redacted system health snapshot. NEVER raises."""
    try:
        sqlite_version = sqlite3.sqlite_version
    except Exception:
        sqlite_version = None
    return {
        "python_version": sys.version,
        "sqlite_version": sqlite_version,
        "mlt_available": _mlt_available(),
        "chromium_available": _chromium_available(),
        "sandbox_backend": _sandbox_backend(),
        "sandbox_available": _sandbox_available(),
        "disk_free_bytes": _disk_free_bytes(),
        "config_summary": _config_summary(),
    }


def system_healthy() -> bool:
    """Return True unless a critical component is catastrophically missing.

    Permissive by design: a missing sandbox does NOT mark the system
    unhealthy (there is a dev fallback). Only a broken sqlite — the durable
    store backing every project — is treated as fatal.
    """
    try:
        return _sqlite_ok()
    except Exception:
        return False


def get_health() -> dict:
    """Return the minimal payload for a ``/health`` endpoint. NEVER raises."""
    try:
        sqlite_ok = _sqlite_ok()
    except Exception:
        sqlite_ok = False
    try:
        mlt = _mlt_available()
    except Exception:
        mlt = False
    try:
        sandbox = _sandbox_available()
    except Exception:
        sandbox = False
    return {
        "status": "ok" if sqlite_ok else "degraded",
        "mlt": mlt,
        "sandbox": sandbox,
        "sqlite": sqlite_ok,
    }
