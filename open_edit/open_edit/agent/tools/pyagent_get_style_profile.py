"""pyagent_get_style_profile: returns the tag-gated style profile slice.

Per phase4-design-revised.md §3.2 (T3): the agent pulls a tag-gated
slice of the style profile for the op_type it's about to plan.
"""
from __future__ import annotations

from open_edit.style.retrieve import get_slice


def get_style_profile(args: dict, project_path: str) -> dict:
    """Return the style profile slice for args['op_type']."""
    try:
        return get_slice(args["op_type"])
    except Exception as e:
        return {"status": "error", "error": str(e)}
