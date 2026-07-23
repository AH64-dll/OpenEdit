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


# Single source of truth for the render subprocess timeout. Both
# ``pi_bridge._run_mlt_only_render`` (subprocess path) and
# ``agent._execute_trigger_render`` (in-process path) must use this
# same value so the two paths time out consistently.
RENDER_TIMEOUT_S = 14400


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


def get_context_budget_config() -> dict[str, Any]:
    """Return the typed config for the context budget system."""
    return {
        "max_tokens": _env_int("OPEN_EDIT_CONTEXT_MAX_TOKENS", 32000),
        "reserve_tokens": _env_int("OPEN_EDIT_CONTEXT_RESERVE_TOKENS", 4000),
        "max_state_chars": _env_int("OPEN_EDIT_CONTEXT_MAX_STATE_CHARS", 10000),
    }


def get_overlay_config() -> dict[str, Any]:
    """Return the typed config for the v1.6 HTML overlay pipeline."""
    overlay_tmpdir_str = _env_str("OPEN_EDIT_OVERLAY_TMPDIR", "") or ""
    return {
        "hyperframes_bin": (
            _env_str("OPEN_EDIT_HYPERFRAMES_BIN", None)
        ),
        "hyperframes_timeout_s": _env_int("OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS", 3600),
        "overlay_tmpdir": Path(overlay_tmpdir_str).resolve() if overlay_tmpdir_str else None,
    }
