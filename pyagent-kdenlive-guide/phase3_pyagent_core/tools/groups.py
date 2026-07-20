"""Tool defs for group operations.

Phase 4 Task 7: repointed to IR.group_edits / IR.ungroup_edits.
"""
from __future__ import annotations

from .project import ToolDef


_S = {"type": "string"}
_A = {"type": "array", "items": _S}


GROUP_CLIPS = ToolDef(
    name="pyagent_group_clips",
    label="Group clips",
    description="Create a folder-style group containing the given clip_ids. group_name must be unique across the project.",
    op="group_clips",
    is_mutating=True,
    parameters_schema={"clip_ids": _A, "group_name": _S},
    required=("clip_ids", "group_name"),
)


UNGROUP_CLIPS = ToolDef(
    name="pyagent_ungroup_clips",
    label="Ungroup clips",
    description="Dissolve a group by its group_name. The clips remain on the timeline; only the group is removed.",
    op="ungroup_clips",
    is_mutating=True,
    parameters_schema={"group_name": _S},
    required=("group_name",),
)


LIST_GROUPS = ToolDef(
    name="pyagent_list_groups",
    label="List groups",
    description="List all groups in the project. Read-only.",
    op="list_groups",
    is_mutating=False,
    parameters_schema={},
    required=(),
)


TOOLS = [GROUP_CLIPS, UNGROUP_CLIPS, LIST_GROUPS]


# --- Wrapper functions (Phase 4 Task 7) ---


def group_clips(args: dict, project_path: str) -> dict:
    """Group a set of edit_ids under a label."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    edit_ids = args.get("edit_ids") or args.get("clip_ids") or []
    label = args.get("label") or args["group_name"]
    ir.group_edits(edit_ids=list(edit_ids), label=label)
    return {"status": "ok"}


def ungroup_clips(args: dict, project_path: str) -> dict:
    """Ungroup a labeled group."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    label = args.get("label") or args["group_name"]
    ir.ungroup_edits(label=label)
    return {"status": "ok"}


def list_groups(args: dict, project_path: str) -> dict:
    """Read-back: list all group labels in the project."""
    from open_edit.agent.tools._helpers import load_project
    from open_edit.ir.apply import derive_timeline

    project = load_project(project_path)
    timeline = derive_timeline(project)
    _ = timeline
    labels = []
    for op in project.edit_graph:
        if op.kind == "group_edits":
            labels.append(op.label)
    return {"groups": labels}
