"""Review-only server mode (no built-in LLM / chat)."""
from __future__ import annotations

import os


def is_review_only() -> bool:
    """True when the UI is a harness-driven review studio (MCP plugin workflow)."""
    raw = (os.environ.get("OPEN_EDIT_REVIEW_ONLY") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def auto_proxy_enabled() -> bool:
    """When set, the review UI may enqueue a proxy render after graph changes."""
    raw = (os.environ.get("OPEN_EDIT_AUTO_PROXY") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")
