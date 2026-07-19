"""Tool defs for effect application."""
from __future__ import annotations

from .project import ToolDef


APPLY_EFFECT = ToolDef(
    name="pyagent_apply_effect",
    label="Apply effect",
    description=(
        "Apply an effect to a clip. effect_id must come from the catalog "
        "(use pyagent_list_catalog to look it up). params is {name: value}."
    ),
    op="apply_effect",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_id": {"type": "string", "description": "catalog effect id"},
        "params": {"type": "object", "additionalProperties": True},
    },
    required=("clip_id", "effect_id"),
)


TOOLS = [APPLY_EFFECT]
