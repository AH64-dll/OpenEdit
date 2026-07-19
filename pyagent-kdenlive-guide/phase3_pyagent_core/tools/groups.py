"""Tool defs for group operations."""
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
