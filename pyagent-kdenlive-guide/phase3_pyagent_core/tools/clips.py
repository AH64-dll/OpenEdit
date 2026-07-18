"""Tool defs for clip operations on the timeline."""
from __future__ import annotations

from .project import ToolDef


_T = {"type": "integer", "minimum": 0}
_S = {"type": "string"}
_N = {"type": "number", "minimum": 0}
_B = {"type": "boolean"}


INSERT_CLIP = ToolDef(
    name="pyagent_insert_clip",
    label="Insert clip",
    description="Insert a clip from the bin onto the timeline at the given position. Pass `source_id` as the bin source id (see get_timeline_summary()'s source_id field, or a clip_id from that summary, or import_media()'s return).",
    op="insert_clip",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {
            "track_index": _T, "position_sec": _N, "source_id": _S,
            "source_in_sec": _N, "source_out_sec": _N,
            "video_only": _B, "audio_only": _B,
        },
        "required": ["track_index", "position_sec", "source_id"],
    },
)


APPEND_CLIP = ToolDef(
    name="pyagent_append_clip",
    label="Append clip",
    description="Append a clip from the bin to the end of the given track. Pass `source_id` as the bin source id: either the `source_id` field from get_timeline_summary(), or a `clip_id` from that same summary, or the id returned by import_media().",
    op="append_clip",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {
            "track_index": _T, "source_id": _S,
            "source_in_sec": _N, "source_out_sec": _N,
            "video_only": _B, "audio_only": _B,
        },
        "required": ["track_index", "source_id"],
    },
)


MOVE_CLIP = ToolDef(
    name="pyagent_move_clip",
    label="Move clip",
    description="Move a clip to a different track and/or position.",
    op="move_clip",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {
            "clip_id": _S, "new_track": _T, "new_position_sec": _N,
        },
        "required": ["clip_id", "new_track", "new_position_sec"],
    },
)


TRIM_CLIP = ToolDef(
    name="pyagent_trim_clip",
    label="Trim clip",
    description="Trim a clip's in/out points. Both in_sec and out_sec are required and must be within the source clip's range.",
    op="trim_clip",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {"clip_id": _S, "new_in_sec": _N, "new_out_sec": _N},
        "required": ["clip_id", "new_in_sec", "new_out_sec"],
    },
)


DELETE_CLIP = ToolDef(
    name="pyagent_delete_clip",
    label="Delete clip",
    description="Remove a clip from the timeline.",
    op="delete_clip",
    is_mutating=True,
    parameters_schema={"type": "object", "properties": {"clip_id": _S}, "required": ["clip_id"]},
)


TOOLS = [INSERT_CLIP, APPEND_CLIP, MOVE_CLIP, TRIM_CLIP, DELETE_CLIP]
