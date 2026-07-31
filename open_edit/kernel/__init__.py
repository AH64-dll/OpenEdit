"""Shared editing kernel — tool dispatch, render jobs, pillar schemas.

Used by the MCP plugin and the review/agent HTTP server. No LLM or UI here.
"""
from __future__ import annotations

from .edit_graph_service import EditGraphCommandError, apply_command
from .pillar_tools import dispatch_edit, dispatch_generate, dispatch_query
from .render_jobs import (
    DEFAULT_RENDER_JOB_SERVICE,
    RenderEnqueueError,
    RenderJobService,
)
from .schema_validator import validate_or_error
from .tool_executor import execute_tool, execute_trigger_render
from .tool_registry import build_tool_schemas
from .tool_schemas import TOOL_SCHEMAS

__all__ = [
    "DEFAULT_RENDER_JOB_SERVICE",
    "RenderEnqueueError",
    "RenderJobService",
    "EditGraphCommandError",
    "apply_command",
    "build_tool_schemas",
    "dispatch_edit",
    "dispatch_generate",
    "dispatch_query",
    "execute_tool",
    "execute_trigger_render",
    "validate_or_error",
    "TOOL_SCHEMAS",
]
