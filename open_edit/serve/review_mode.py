"""Review-only server mode (no built-in LLM / chat)."""
from __future__ import annotations

import os


def is_review_only() -> bool:
    """True when the UI is a harness-driven review studio (MCP plugin workflow).

    Defaults ON (MCP-first). Set ``OPEN_EDIT_REVIEW_ONLY=0`` or pass
    ``open_edit serve --with-agent`` to enable the built-in chat / provider UI.
    """
    raw = (os.environ.get("OPEN_EDIT_REVIEW_ONLY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def auto_proxy_enabled() -> bool:
    """When set, the review UI may enqueue a proxy render after graph changes."""
    raw = (os.environ.get("OPEN_EDIT_AUTO_PROXY") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def auto_preview_enabled() -> bool:
    """When set, the review UI may enqueue preview chunks automatically."""
    raw = (os.environ.get("OPEN_EDIT_AUTO_PREVIEW") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def preview_chunks_enabled() -> bool:
    """Return whether preview-chunk generation is enabled for this server.

    Default on; set ``OPEN_EDIT_PREVIEW_CHUNKS=0`` to disable.
    """
    from open_edit.kernel.tool_executor import (
        preview_chunks_enabled as _enabled,
    )

    return _enabled()
