"""Tool defs for timeline markers and project save.

`save_project` is grouped here because it shares the "non-clip domain"
slot and the file-level tool count is locked at 19 with no spare slot.
"""
from __future__ import annotations

from .project import ToolDef


ADD_MARKER = ToolDef(
    name="pyagent_add_marker",
    label="Add marker",
    description="Add a marker (or guide/chapter) at the given position.",
    op="add_marker",
    is_mutating=True,
    parameters_schema={
        "position_sec": {"type": "number", "minimum": 0},
        "label": {"type": "string"},
        "kind": {"type": "string", "enum": ["marker", "guide", "chapter"]},
    },
    required=("position_sec", "label"),
)


SAVE_PROJECT = ToolDef(
    name="pyagent_save_project",
    label="Save project",
    description="Write the .kdenlive file to disk. Use this when you are done editing.",
    op="save",
    is_mutating=True,
    parameters_schema={"path": {"type": "string"}},
    required=(),
)


TOOLS = [ADD_MARKER, SAVE_PROJECT]
