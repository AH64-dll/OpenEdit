"""Tool defs for clip-edit operations on the timeline."""
from __future__ import annotations

from .project import ToolDef


_T = {"type": "integer", "minimum": 0}
_S = {"type": "string"}
_N = {"type": "number", "minimum": 0}


SLIP_CLIP = ToolDef(
    name="pyagent_slip_clip",
    label="Slip clip",
    description="Slip a clip: shift the source media in/out by `delta_sec` while keeping the timeline window fixed. Use delta_sec > 0 to show later in the source, < 0 to show earlier. The clip's start and duration on the timeline stay the same.",
    op="slip_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "delta_sec": _N},
    required=("clip_id", "delta_sec"),
)


RIPPLE_DELETE_CLIP = ToolDef(
    name="pyagent_ripple_delete_clip",
    label="Ripple delete clip",
    description="Remove a clip from the timeline and close the gap on the same track (all following clips on that track shift left by the deleted duration). Clips on other tracks are unaffected.",
    op="ripple_delete_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S},
    required=("clip_id",),
)


CHANGE_CLIP_SPEED = ToolDef(
    name="pyagent_change_clip_speed",
    label="Change clip speed",
    description="Change the clip's playback rate. rate=1.0 is normal, 2.0 is 2x faster (half duration), 0.5 is 2x slower (double duration). Audio pitch is preserved. Rate must be in [0.1, 10.0].",
    op="change_clip_speed",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "rate": _N},
    required=("clip_id", "rate"),
)


SPLIT_CLIP = ToolDef(
    name="pyagent_split_clip",
    label="Split clip",
    description="Split a clip at a single position. Returns both new clip_ids; the left half keeps the original id, the right half is new. at_sec must be strictly between the clip's timeline start and end.",
    op="split_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "at_sec": _N},
    required=("clip_id", "at_sec"),
)


REPLACE_CLIP_SOURCE = ToolDef(
    name="pyagent_replace_clip_source",
    label="Replace clip source",
    description="Replace the clip's source media. Resets the playback rate to 1.0. The new duration is min(old_duration, new_source_duration).",
    op="replace_clip_source",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "new_source_id": _S},
    required=("clip_id", "new_source_id"),
)


SET_CLIP_SPEED_RAMP = ToolDef(
    name="pyagent_set_clip_speed_ramp",
    label="Set clip speed ramp",
    description=(
        "Add or replace a keyframed speed ramp on a clip. Uses an "
        "<link mlt_service='timeremap'> element on the clip's producer. "
        "The first keyframe MUST be at time_ms=0 and rate=1.0. The ramp "
        "is replaced wholesale; the AI is expected to read get_timeline_summary "
        "or list_keyframes first if it wants to preserve existing keyframes."
    ),
    op="set_clip_speed_ramp",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "keyframes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "time_ms": {"type": "integer", "minimum": 0},
                        "rate": {"type": "number", "exclusiveMinimum": 0, "maximum": 10},
                    },
                    "required": ["time_ms", "rate"],
                },
                "description": "Sorted ascending by time_ms; first must be at time_ms=0 rate=1.0",
            },
        },
        "required": ["clip_id", "keyframes"],
        "additionalProperties": False,
    },
)


TOOLS = [SLIP_CLIP, RIPPLE_DELETE_CLIP, CHANGE_CLIP_SPEED, SPLIT_CLIP, REPLACE_CLIP_SOURCE, SET_CLIP_SPEED_RAMP]
