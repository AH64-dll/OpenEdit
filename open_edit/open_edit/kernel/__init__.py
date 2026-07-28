"""Shared editing kernel — tool dispatch, render jobs, pillar schemas.

Used by the MCP plugin and the review/agent HTTP server. No LLM or UI here.
"""
from __future__ import annotations

__all__ = [
    "DEFAULT_RENDER_SERVICE",
    "RenderEnqueueError",
    "RenderService",
    "apply_command",
    "build_tool_schemas",
    "dispatch_edit",
    "dispatch_generate",
    "dispatch_query",
    "execute_tool",
    "execute_trigger_render",
    "validate_or_error",
]
