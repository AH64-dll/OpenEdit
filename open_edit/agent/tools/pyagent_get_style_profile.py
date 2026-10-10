"""pyagent_get_style_profile: returns the tag-gated style profile slice.

Per phase4-design-revised.md §3.2 (T3): the agent pulls a tag-gated
slice of the style profile for the op_type it's about to plan.
"""
from __future__ import annotations

from open_edit.agent.tools._contract import tool_result
from open_edit.style.retrieve import TAG_MAP, get_slice


def _normalize(op_type: str) -> str:
    """Accept AddClip, AddClipOp or add_clip for the PascalCase TAG_MAP keys."""
    name = op_type.strip()
    if "_" in name or name.islower():
        name = "".join(part.capitalize() for part in name.split("_"))
    return name.removesuffix("Op") if name.removesuffix("Op") in TAG_MAP else name


@tool_result
def get_style_profile(args: dict, project_path: str) -> dict:
    """Return the style profile slice for ``args['op_type']``.

    Args:
        args: {"op_type": str (required)}: a PascalCase op type such as
              ``"AddClip"``, ``"AddTransition"`` or ``"AddEffect"``
              (``AddClipOp`` and ``add_clip`` are also accepted).
        project_path: path to the project directory.

    Returns:
        ``{"status": "ok", "profile": {...}}`` on success, or
        ``{"status": "error", "error": "..."}`` on failure. Unknown op types
        return the corrections-only slice plus a ``note`` with valid values.
    """
    op_type = args.get("op_type")
    if not op_type:
        return {
            "status": "error",
            "error": f"op_type is required; one of {sorted(TAG_MAP)}",
        }
    key = _normalize(str(op_type))
    result = {"status": "ok", "op_type": key, "profile": get_slice(key)}
    if key not in TAG_MAP:
        result["note"] = f"unknown op_type; only corrections apply. Valid: {sorted(TAG_MAP)}"
    return result
