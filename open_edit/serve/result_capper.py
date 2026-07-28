"""Cap oversized tool results before they enter conversation history.

Called from both ``agent.py`` and ``pi_bridge.py`` to proactively
limit tool result size, preventing ``LimitOverrunError`` in the
pi subprocess pipe and keeping the conversation history lean.
"""
from __future__ import annotations

from typing import Any


_MAX_BYTES = 512_000
_MAX_ITEM_CHARS = 10_000
_MAX_LIST_ITEMS = 20


def cap_tool_result(result: dict[str, Any], max_bytes: int = _MAX_BYTES) -> dict[str, Any]:
    """Return a copy of ``result`` with oversized fields truncated.

    * Truncates ``stdout``, ``stderr``, ``error`` to 10K chars each.
    * Caps list fields to 20 items (with ``...[N more]`` marker).
    * For ``trigger_render`` results: strips ``stdout``/``stderr`` entirely
      (they are debugging-only).
    * Adds ``_truncated: true`` when any truncation occurs.
    """
    truncated = False
    out = dict(result)

    is_render = out.get("output_path") is not None and out.get("status") in ("ok", "error")

    for field in ("stdout", "stderr"):
        if field in out:
            if is_render:
                truncated = True
                del out[field]
            elif isinstance(out[field], str) and len(out[field]) > _MAX_ITEM_CHARS:
                out[field] = out[field][:_MAX_ITEM_CHARS] + "\n... [truncated]"
                truncated = True

    for field in ("error",):
        if isinstance(out.get(field), str) and len(out[field]) > _MAX_ITEM_CHARS:
            out[field] = out[field][:_MAX_ITEM_CHARS] + "\n... [truncated]"
            truncated = True

    for field in list(out.keys()):
        if isinstance(out[field], list) and len(out[field]) > _MAX_LIST_ITEMS:
            out[field] = out[field][:_MAX_LIST_ITEMS]
            out[field].append(f"... [{len(out[field]) - _MAX_LIST_ITEMS + 1} more items]")
            truncated = True

    if truncated:
        out["_truncated"] = True

    return out
