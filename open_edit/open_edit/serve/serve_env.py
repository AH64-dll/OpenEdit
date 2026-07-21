"""Centralised env-var loading for the open_edit server.

v1.5 introduced a new visual-verification stage with its own knobs. The
defaults and parsing live here so that ``agent.py`` and ``visual_verify.py``
can both depend on a single source of truth.

Usage::

    from open_edit.serve.serve_env import get_visual_verify_config
    cfg = get_visual_verify_config()
    if cfg["enabled"]:
        ...
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str | None) -> str | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip()


def get_visual_verify_config() -> dict[str, Any]:
    """Return the typed config for the visual verification stage.

    All values are real Python types (not raw strings); this is the only
    function any consumer should call. Tests rely on this contract.
    """
    return {
        "enabled": _env_bool("OPEN_EDIT_VERIFY_ENABLED", True),
        "frames": _env_int("OPEN_EDIT_VERIFY_FRAMES", 3),
        "max_renders": _env_int("OPEN_EDIT_VERIFY_MAX_RENDERS", 3),
        "max_edge_px": _env_int("OPEN_EDIT_VERIFY_MAX_EDGE_PX", 1024),
        "jpeg_quality": _env_int("OPEN_EDIT_VERIFY_JPEG_QUALITY", 85),
        "total_timeout_seconds": _env_int("OPEN_EDIT_VERIFY_TOTAL_TIMEOUT_SECONDS", 30),
        "max_image_bytes": _env_int("OPEN_EDIT_VERIFY_MAX_IMAGE_BYTES", 5_242_880),
        "debug_dir": _env_str("OPEN_EDIT_VERIFY_DEBUG_DIR", None),
        "render_mode": _env_str("OPEN_EDIT_VERIFY_RENDER_MODE", "proxy") or "proxy",
        "allow_no_change_skip": _env_bool("OPEN_EDIT_VERIFY_ALLOW_NO_CHANGE_SKIP", True),
        "persist_history": _env_bool("OPEN_EDIT_VERIFY_PERSIST_HISTORY", True),
    }
