"""pyagent_set_pinned_value: writes a pinned value to the style profile.

Per phase4-design-revised.md §3.2 (T3): the user can pin a preference
(e.g. 'aspect_ratio': '9:16') that overrides the agent's defaults.
"""
from __future__ import annotations

from open_edit.style.aggregate import set_pinned


def set_pinned_value(args: dict, project_path: str) -> dict:
    """Set pinned key=value in the global style profile."""
    try:
        set_pinned(args["key"], args["value"])
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
