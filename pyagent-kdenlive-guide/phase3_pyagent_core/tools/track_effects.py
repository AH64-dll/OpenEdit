"""Tool defs for track-level effect operations."""
from __future__ import annotations

from .project import ToolDef


ADD_EFFECT_TO_TRACK = ToolDef(
    name="pyagent_add_effect_to_track",
    label="Add effect to track",
    description=(
        "Add a Kdenlive effect to a track (not a clip). The effect is "
        "added as a filter on the track's tractor, so it applies to "
        "every clip on the track. Video effects cannot be added to "
        "audio tracks and vice versa."
    ),
    op="add_effect_to_track",
    is_mutating=True,
    parameters_schema={
        "track_index": {"type": "integer", "description": "0-based track index"},
        "effect_id": {"type": "string", "description": "Kdenlive effect id (e.g. 'volume', 'blur')"},
        "params": {"type": "object", "description": "Optional parameter overrides (defaults from catalog if omitted)"},
    },
    required=("track_index", "effect_id"),
)


LIST_TRACK_EFFECTS = ToolDef(
    name="pyagent_list_track_effects",
    label="List track effects",
    description=(
        "Return the effect stack of a track. Each entry includes the "
        "effect_id, enabled state, and current parameter values."
    ),
    op="list_track_effects",
    is_mutating=False,
    parameters_schema={
        "type": "object",
        "properties": {
            "track_index": {"type": "integer"},
        },
        "required": ["track_index"],
        "additionalProperties": False,
    },
)


TOOLS = [ADD_EFFECT_TO_TRACK, LIST_TRACK_EFFECTS]
