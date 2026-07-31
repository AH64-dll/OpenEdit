"""Centralised env-var loading for the open_edit server.

v1.5 introduced a new visual-verification stage with its own knobs. The
defaults and parsing live here so that ``agent.py`` and ``visual_verify.py``
can both depend on a single source of truth.

Usage::

    from open_edit.serve.serve_env import get_visual_verify_config
    cfg = get_visual_verify_config()
    if cfg["enabled"]:
        ...

The overlay-pipeline config (``get_overlay_config``, ``RENDER_TIMEOUT_S``)
moved to ``open_edit.render.env`` in the kernel-restructure so the kernel
can read it without importing serve; this module re-exports it for legacy
serve consumers.
"""
from __future__ import annotations

from typing import Any

from open_edit.render.env import (  # noqa: F401  (re-exported for serve consumers)
    RENDER_TIMEOUT_S,
    _env_bool,
    _env_int,
    _env_str,
    get_overlay_config,
)


def get_visual_verify_config() -> dict[str, Any]:
    """Return the typed config for the visual verification stage."""
    return {
        "enabled": _env_bool("OPEN_EDIT_VERIFY_ENABLED", True),
        "frames": _env_int("OPEN_EDIT_VERIFY_FRAMES", 3),
        "max_renders": _env_int("OPEN_EDIT_VERIFY_MAX_RENDERS", 100),
        "max_edge_px": _env_int("OPEN_EDIT_VERIFY_MAX_EDGE_PX", 4096),
        "jpeg_quality": _env_int("OPEN_EDIT_VERIFY_JPEG_QUALITY", 95),
        "total_timeout_seconds": _env_int("OPEN_EDIT_VERIFY_TOTAL_TIMEOUT_SECONDS", 3600),
        "max_image_bytes": _env_int("OPEN_EDIT_VERIFY_MAX_IMAGE_BYTES", 100_000_000),
        "debug_dir": _env_str("OPEN_EDIT_VERIFY_DEBUG_DIR", None),
        "render_mode": _env_str("OPEN_EDIT_VERIFY_RENDER_MODE", "proxy") or "proxy",
        "allow_no_change_skip": _env_bool("OPEN_EDIT_VERIFY_ALLOW_NO_CHANGE_SKIP", True),
        "persist_history": _env_bool("OPEN_EDIT_VERIFY_PERSIST_HISTORY", True),
    }
