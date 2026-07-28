"""Map MCP tool calls onto Open Edit pillar dispatch.

``project_path`` is injected server-side — never accepted from the model.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from open_edit.kernel.tool_executor import execute_tool, execute_trigger_render
from open_edit.kernel.tool_registry import TOOL_REGISTRY, build_tool_schemas


_GET_RENDER_JOB_SCHEMA: dict[str, Any] = {
    "name": "get_render_job",
    "description": (
        "Poll a durable render job by job_id. Use after trigger_render "
        "when you need status without blocking, or to inspect a prior job."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Render job id"},
        },
        "required": ["job_id"],
        "additionalProperties": False,
    },
}

_CANCEL_RENDER_JOB_SCHEMA: dict[str, Any] = {
    "name": "cancel_render_job",
    "description": (
        "Cancel a queued or running render job by job_id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Render job id"},
        },
        "required": ["job_id"],
        "additionalProperties": False,
    },
}

HELPER_TOOL_NAMES = frozenset({"get_render_job", "cancel_render_job"})


def mcp_tool_schemas() -> list[dict[str, Any]]:
    """Anthropic-shaped schemas for pillars + render helpers."""
    return [*build_tool_schemas(), _GET_RENDER_JOB_SCHEMA, _CANCEL_RENDER_JOB_SCHEMA]


def result_to_json(result: Any) -> str:
    """Serialize a tool result for MCP TextContent."""
    return json.dumps(result, default=str, sort_keys=True)


def _job_to_dict(job: Any) -> dict[str, Any]:
    data = asdict(job) if hasattr(job, "__dataclass_fields__") else dict(job)
    return {"ok": True, **data}


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
        from open_edit.kernel.render_service import DEFAULT_RENDER_SERVICE

        job = DEFAULT_RENDER_SERVICE.get(project_path, job_id)
        if job is None:
            return {"ok": False, "error": f"render job not found: {job_id}"}
        return _job_to_dict(job)

    if name == "cancel_render_job":
        job_id = args.get("job_id")
        if not job_id or not isinstance(job_id, str):
            return {
                "ok": False,
                "error": "job_id is required",
                "expected_keys": ["job_id"],
            }
        from open_edit.kernel.render_service import DEFAULT_RENDER_SERVICE

        job = await DEFAULT_RENDER_SERVICE.cancel(project_path, job_id)
        if job is None:
            return {"ok": False, "error": f"render job not found: {job_id}"}
        return _job_to_dict(job)

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
