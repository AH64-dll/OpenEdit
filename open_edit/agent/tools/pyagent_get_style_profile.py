"""pyagent_get_style_profile: returns the tag-gated style profile slice.

Per phase4-design-revised.md §3.2 (T3): the agent pulls a tag-gated
slice of the style profile for the op_type it's about to plan.
"""
from __future__ import annotations

from open_edit.style.retrieve import get_slice


def get_style_profile(args: dict, project_path: str) -> dict:
    """Return the style profile slice for ``args['op_type']``.

    Args:
        args: {"op_type": str (required)} — the operation type to get
              the style profile for (e.g. ``"cut"``, ``"trim"``,
              ``"add_effect"``).
        project_path: path to the project directory.

    Returns:
        The style profile slice on success, or
        ``{"status": "error", "error": "..."}`` on failure.
    """
    try:
        op_type = args.get("op_type")
        if not op_type:
            return {
                "status": "error",
                "error": "op_type is required. Call with {\"op_type\": \"<op_kind>\"}.",
            }
        return get_slice(op_type)
    except Exception as e:
        return {"status": "error", "error": str(e)}
