"""Tool defs for project-level reads.

Also defines the `ToolDef` dataclass that every other tools/*.py module
re-uses. Keep it here so the dataclass has a single home.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDef:
    name: str
    label: str
    description: str
    is_mutating: bool
    parameters_schema: dict  # JSON Schema dict
    op: str = ""  # backend op name to dispatch to; "" for tools that call phase6 directly


GET_PROJECT_INFO = ToolDef(
    name="pyagent_get_project_info",
    label="Get project info",
    description="Get the current .kdenlive project's metadata (name, fps, dimensions, duration, etc).",
    op="get_project_info",
    is_mutating=False,
    parameters_schema={"type": "object", "properties": {}},
)


GET_TIMELINE_SUMMARY = ToolDef(
    name="pyagent_get_timeline_summary",
    label="Get timeline summary",
    description=(
        "Get the current timeline: tracks, clips, transitions, markers. "
        "Call this BEFORE planning any edit (per the system prompt rules)."
    ),
    op="get_timeline_summary",
    is_mutating=False,
    parameters_schema={"type": "object", "properties": {}},
)


TOOLS = [GET_PROJECT_INFO, GET_TIMELINE_SUMMARY]
