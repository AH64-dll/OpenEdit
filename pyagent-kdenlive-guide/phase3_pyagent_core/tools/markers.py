"""Tool defs for timeline markers and project save.

`save_project` is grouped here because it shares the "non-clip domain"
slot and the file-level tool count is locked at 19 with no spare slot.

Phase 4 Task 7: `pyagent_add_marker` was moved to open_edit/agent/tools/
(writes to NotesStore). `pyagent_save_project` is a no-op now because
the IR is already persisted to edit_graph.db on every op.
"""
from __future__ import annotations

from .project import ToolDef


SAVE_PROJECT = ToolDef(
    name="pyagent_save_project",
    label="Save project",
    description="Write the .kdenlive file to disk. Use this when you are done editing.",
    op="save",
    is_mutating=True,
    parameters_schema={"path": {"type": "string"}},
    required=(),
)


TOOLS = [SAVE_PROJECT]


def save_project(args: dict, project_path: str) -> dict:
    """No-op: Open Edit persists every op to edit_graph.db on append."""
    return {"status": "ok", "saved": True}
