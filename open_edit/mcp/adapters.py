"""Map MCP tool calls onto Open Edit pillar dispatch.

``project_path`` is injected server-side — never accepted from the model.
"""
from __future__ import annotations

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
    return json.dumps(result, default=str, sort_keys=True)


async def dispatch_mcp_tool(
    name: str,
    arguments: dict[str, Any] | None,
    project_path: Path,
) -> dict[str, Any]:
    """Execute one MCP tool against the pinned project.

    Returns a JSON-serializable dict (success or structured error).
    """
    args = dict(arguments or {})

    if name == "trigger_render":
        try:
            return await execute_trigger_render(args, project_path)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "error_code": "render_failed"}

    if name == "get_render_job":
        job_id = args.get("job_id")
        if not job_id or not isinstance(job_id, str):
            return {
                "ok": False,
                "error": "job_id is required",
                "expected_keys": ["job_id"],
            }
        from open_edit.kernel.render_jobs import (
            DEFAULT_RENDER_JOB_SERVICE,
            public_job,
        )

        job = DEFAULT_RENDER_JOB_SERVICE.get(project_path, job_id)
        if job is None:
            return {"ok": False, "error": f"render job not found: {job_id}"}
        return {"ok": True, **public_job(job)}

    if name == "cancel_render_job":
        job_id = args.get("job_id")
        if not job_id or not isinstance(job_id, str):
            return {
                "ok": False,
                "error": "job_id is required",
                "expected_keys": ["job_id"],
            }
        from open_edit.kernel.render_jobs import (
            DEFAULT_RENDER_JOB_SERVICE,
            public_job,
        )

        job = await DEFAULT_RENDER_JOB_SERVICE.cancel(project_path, job_id)
        if job is None:
            return {"ok": False, "error": f"render job not found: {job_id}"}
        return {"ok": True, **public_job(job)}

    if name in TOOL_REGISTRY:
        try:
            return execute_tool(name, args, project_path)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "error_code": "tool_failed"}

    return {
        "ok": False,
        "error": f"Unknown tool: {name!r}",
        "error_code": "unknown_tool",
    }
