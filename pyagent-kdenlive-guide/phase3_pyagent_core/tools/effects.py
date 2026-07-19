"""Tool defs for effect application."""
from __future__ import annotations

from .project import ToolDef


_APPLY_DESCRIPTION = (
    "Apply an effect to a clip. effect_id must come from the catalog "
    "(use pyagent_list_catalog to look it up). params is {name: value}."
)


APPLY_EFFECT = ToolDef(
    name="pyagent_apply_effect",
    label="Apply effect",
    description=_APPLY_DESCRIPTION,
    op="apply_effect",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_id": {"type": "string", "description": "catalog effect id"},
        "params": {"type": "object", "additionalProperties": True},
    },
    required=("clip_id", "effect_id"),
)


REMOVE_EFFECT = ToolDef(
    name="pyagent_remove_effect",
    label="Remove effect",
    description=(
        "Remove an effect from a clip by its index. effect_index is the "
        "0-based position in the clip's effect list. Call "
        "pyagent_get_timeline_summary first to see what effect indices "
        "exist on the clip."
    ),
    op="remove_effect",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer", "minimum": 0},
    },
    required=("clip_id", "effect_index"),
)


TOOLS = [APPLY_EFFECT, REMOVE_EFFECT]
