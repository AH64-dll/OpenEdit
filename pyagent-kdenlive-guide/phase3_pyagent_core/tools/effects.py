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


GET_EFFECT_PARAM = ToolDef(
    name="pyagent_get_effect_param",
    label="Get effect param",
    description=(
        "Read the current value of an effect parameter on a clip. "
        "For keyframable params, also returns the parsed keyframes list. "
        "WARNING: this does NOT validate that the clip's effect stack "
        "matches the catalog; the returned 'effect_id' is read from the "
        "kdenlive:id property in the file. To change a param's value, "
        "use set_effect_param."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string", "description": "Target clip id"},
            "effect_index": {"type": "integer", "description": "0-based effect index in the clip's filter list"},
            "param_name": {"type": "string", "description": "Parameter name (e.g. 'opacity', 'level')"},
        },
        "required": ["clip_id", "effect_index", "param_name"],
        "additionalProperties": False,
    },
    op="get_effect_param",
    is_mutating=False,
)

SET_EFFECT_PARAM = ToolDef(
    name="pyagent_set_effect_param",
    label="Set effect param",
    description=(
        "Set an effect parameter to a static value. "
        "WARNING: if the param is keyframable, this REPLACES the entire "
        "animation string. The response includes 'is_keyframable' and "
        "'previous_value' so the caller can detect the case and use "
        "set_keyframe instead. For non-keyframable params, the value is "
        "coerced to the catalog's type."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "effect_index": {"type": "integer"},
            "param_name": {"type": "string"},
            "value": {"type": "string", "description": "New value (as string; coerced to type)"},
        },
        "required": ["clip_id", "effect_index", "param_name", "value"],
        "additionalProperties": False,
    },
    op="set_effect_param",
    is_mutating=True,
)


TOOLS = [APPLY_EFFECT, REMOVE_EFFECT, GET_EFFECT_PARAM, SET_EFFECT_PARAM]
