"""Render-side env config shared by the kernel overlay trigger and serve.

Homes for the overlay-pipeline config (``get_overlay_config``) and the
render subprocess timeout (``RENDER_TIMEOUT_S``). These are pure env
readers (stdlib only) — they live outside ``open_edit.serve`` so the
kernel can use them without violating the kernel→serve layering
invariant (see ``open_edit/kernel/render_overlay.py``).

``serve_env.get_overlay_config``/``RENDER_TIMEOUT_S`` remain available
as re-exports for legacy serve consumers.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# Single source of truth for the render subprocess timeout. Both
# ``render_overlay._run_mlt_only_render`` (subprocess path) and
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
