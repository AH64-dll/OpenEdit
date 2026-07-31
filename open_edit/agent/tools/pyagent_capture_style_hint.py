"""pyagent_capture_style_hint: persist a confirmed user style preference."""
from __future__ import annotations

from open_edit.agent.tools._contract import tool_result
from open_edit.style.aggregate import capture_hint


@tool_result
def capture_style_hint(args: dict, project_path: str) -> dict:
    """Store a confirmed style hint (and optional pin) in the global profile.

    ``project_path`` is accepted for TOOL_TABLE symmetry; the profile is
    user-global under ``~/.open-edit/style_profile.json``.
    """
    del project_path  # global profile; keep signature consistent with peers
    if args.get("confirmed") is not True:
        return {
            "status": "error",
            "error": "confirmed must be true — ask the user before persisting",
        }
    hint = args.get("hint")
    if not isinstance(hint, str) or not hint.strip():
        return {"status": "error", "error": "hint (non-empty string) is required"}
    category = args.get("category") or "other"
    if not isinstance(category, str):
        return {"status": "error", "error": "category must be a string"}
    key = args.get("key")
    value = args.get("value")
    if key is not None and not isinstance(key, str):
        return {"status": "error", "error": "key must be a string when provided"}
    entry = capture_hint(
        category=category,
        hint=hint,
        key=key if isinstance(key, str) else None,
        value=value,
    )
    return {"status": "ok", "hint": entry}
