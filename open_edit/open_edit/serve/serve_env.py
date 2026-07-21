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
RENDER_TIMEOUT_S = 1800


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


def get_overlay_config() -> dict[str, Any]:
    """Return the typed config for the v1.6 HTML overlay pipeline.

    All values are real Python types (not raw strings); this is the only
    function any consumer should call. Tests rely on this contract.

    Returns:
        {
            "hyperframes_bin": str | None, # path to the hyperframes binary; None = auto-resolve at call time
            "hyperframes_timeout_s": int,  # subprocess timeout in seconds
            "overlay_tmpdir": Path | None, # base dir for per-render intermediate files; None = project-scoped default
        }

    Contract: when the env var is unset, ``hyperframes_bin`` is ``None``
    (not ``""``), so consumers can use ``or`` to short-circuit to the
    resolver. The sibling field ``overlay_tmpdir`` uses the same
    ``None`` sentinel for its "unset" case.
    """
    overlay_tmpdir_str = _env_str("OPEN_EDIT_OVERLAY_TMPDIR", "") or ""
    return {
        "hyperframes_bin": (
            # None when OPEN_EDIT_HYPERFRAMES_BIN is unset; the consumer
            # (pi_bridge._build_render_spec) falls back to
            # html_overlay._resolve_hyperframes_bin() in that case.
            _env_str("OPEN_EDIT_HYPERFRAMES_BIN", None)
        ),
        "hyperframes_timeout_s": _env_int("OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS", 120),
        "overlay_tmpdir": Path(overlay_tmpdir_str).resolve() if overlay_tmpdir_str else None,
    }
