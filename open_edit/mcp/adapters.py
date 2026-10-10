"""Map MCP tool calls onto Open Edit pillar dispatch.

``project_path`` is injected server-side — never accepted from the model.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any

from open_edit.kernel.tool_executor import execute_tool, execute_trigger_render
from open_edit.kernel.tool_registry import TOOL_REGISTRY, build_tool_schemas

HELPER_TOOL_NAMES = frozenset({"get_render_job", "cancel_render_job"})


def mcp_tool_schemas() -> list[dict[str, Any]]:
    """Anthropic-shaped schemas for pillars + render helpers."""
    return build_tool_schemas()


def result_to_json(result: Any) -> str:
    """Serialize a tool result for MCP TextContent."""
    # Compact, UTF-8 output: agents pay per token, not per escaped byte.
    return json.dumps(result, default=str, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


async def dispatch_mcp_tool(
    name: str,
    arguments: dict[str, Any] | None,
    project_path: Path,
) -> dict[str, Any]:
    """Execute one MCP tool against the pinned project.

    Returns a JSON-serializable dict (success or structured error).
    """
    if arguments is not None and not isinstance(arguments, dict):
        return {"ok": False, "error": "arguments must be an object", "error_code": "schema_validation_failed"}
    args = dict(arguments or {})

    if name == "trigger_render":
        try:
            return await execute_trigger_render(args, project_path)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "error_code": "render_failed"}

    if name in TOOL_REGISTRY:
        try:
            result = (
                execute_tool(name, args, project_path)
                if name == "cancel_render_job"
                else await asyncio.to_thread(execute_tool, name, args, project_path)
            )
            return await result if inspect.isawaitable(result) else result
        except Exception as exc:
            return {"ok": False, "error": str(exc), "error_code": "tool_failed"}

    return {
        "ok": False,
        "error": f"Unknown tool: {name!r}",
        "error_code": "unknown_tool",
    }
