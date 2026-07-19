"""ToolDef definitions for the keyframe operations."""
from __future__ import annotations

from .project import ToolDef


LIST_KEYFRAMES = ToolDef(
    name="pyagent_list_keyframes",
    label="List keyframes",
    description=(
        "Return the keyframes on a keyframable effect parameter. "
        "Returns an empty list if the param is not keyframable or has "
        "no keyframes. For simplekeyframe params (5 in the 26.04 catalog), "
        "returns format='simplekeyframe' and an empty keyframes list — "
        "mlt_geometry support is deferred to a later sub-project."
    ),
    op="list_keyframes",
    is_mutating=False,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer"},
        "param_name": {"type": "string"},
    },
    required=("clip_id", "effect_index", "param_name"),
)

SET_KEYFRAME = ToolDef(
    name="pyagent_set_keyframe",
    label="Set keyframe",
    description=(
        "Add a new keyframe at the given frame, or update the value/type "
        "of an existing one. `type` is one of: linear, discrete, hold, "
        "smooth, or 8 ease variants (a, b, c, d, A, B, C, D). Default "
        "is linear. `frame` is 0-based, relative to the clip's in-point."
    ),
    op="set_keyframe",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer"},
        "param_name": {"type": "string"},
        "frame": {"type": "integer", "description": "0-based frame relative to clip's in-point"},
        "value": {"type": "string", "description": "Keyframe value (as string)"},
        "type": {"type": "string", "description": "One of: linear, discrete, hold, smooth, a, b, c, d, A, B, C, D"},
    },
    required=("clip_id", "effect_index", "param_name", "frame", "value"),
)

REMOVE_KEYFRAME = ToolDef(
    name="pyagent_remove_keyframe",
    label="Remove keyframe",
    description=(
        "Remove the keyframe at the given frame. No error if no keyframe "
        "exists there; the response includes removed: false. For "
        "simplekeyframe params, raises simplekeyframe_format_unsupported."
    ),
    op="remove_keyframe",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer"},
        "param_name": {"type": "string"},
        "frame": {"type": "integer"},
    },
    required=("clip_id", "effect_index", "param_name", "frame"),
)


TOOLS = [LIST_KEYFRAMES, SET_KEYFRAME, REMOVE_KEYFRAME]
