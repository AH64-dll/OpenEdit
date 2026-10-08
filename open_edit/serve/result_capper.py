"""Bound diagnostic tool output before it enters the model context."""
from __future__ import annotations

from typing import Any

_MAX_ITEM_CHARS = 10_000
_MAX_LIST_ITEMS = 20
# Operation proposals are inputs to apply_generated_ops, not display rows.
_ACTION_FIELDS = frozenset({"ops", "suggested_ops", "proposed_ops"})


def cap_tool_result(result: dict[str, Any], max_chars: int = _MAX_ITEM_CHARS) -> dict[str, Any]:
    """Copy and recursively cap display data while retaining executable ops.

    Render diagnostics are removed on success, retained (bounded) on failure.
    Nested query results and transcript strings follow the same limits as
    stdout, avoiding the former unbounded nested-payload loophole.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    truncated = False

    def cap(value: Any, field: str = "") -> Any:
        nonlocal truncated
        if field in _ACTION_FIELDS:
            from copy import deepcopy
            return deepcopy(value)
        if isinstance(value, str) and len(value) > max_chars:
            truncated = True
            return value[:max_chars] + "\n... [truncated]"
        if isinstance(value, dict):
            return {key: cap(item, key) for key, item in value.items()}
        if isinstance(value, list):
            items = [cap(item) for item in value[:_MAX_LIST_ITEMS]]
            if len(value) > _MAX_LIST_ITEMS:
                truncated = True
                items.append(f"... [{len(value) - _MAX_LIST_ITEMS} more items]")
            return items
        return value

    out = cap(result)
    is_successful_render = out.get("output_path") is not None and out.get("status") == "ok"
    if is_successful_render:
        for field in ("stdout", "stderr"):
            if field in out:
                del out[field]
                truncated = True
    if truncated:
        out["_truncated"] = True
    return out
