"""Tool defs for clip operations on the timeline.

Phase 4 Task 7: repointed to IR.add_clip / IR.move_clip / IR.trim_clip /
IR.remove_clip.
"""
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
        "track_index": _T, "position_sec": _N, "source_id": _S,
        "source_in_sec": _N, "source_out_sec": _N,
        "video_only": _B, "audio_only": _B,
    },
    required=("track_index", "position_sec", "source_id"),
)


APPEND_CLIP = ToolDef(
    name="pyagent_append_clip",
    label="Append clip",
    description="Append a clip from the bin to the end of the given track. Pass `source_id` as the bin source id: either the `source_id` field from get_timeline_summary(), or a `clip_id` from that same summary, or the id returned by import_media().",
    op="append_clip",
    is_mutating=True,
    parameters_schema={
        "track_index": _T, "source_id": _S,
        "source_in_sec": _N, "source_out_sec": _N,
        "video_only": _B, "audio_only": _B,
    },
    required=("track_index", "source_id"),
)


MOVE_CLIP = ToolDef(
    name="pyagent_move_clip",
    label="Move clip",
    description="Move a clip to a different track and/or position.",
    op="move_clip",
    is_mutating=True,
    parameters_schema={
        "clip_id": _S, "new_track": _T, "new_position_sec": _N,
    },
    required=("clip_id", "new_track", "new_position_sec"),
)


TRIM_CLIP = ToolDef(
    name="pyagent_trim_clip",
    label="Trim clip",
    description="Trim a clip's in/out points. Both in_sec and out_sec are required and must be within the source clip's range.",
    op="trim_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "new_in_sec": _N, "new_out_sec": _N},
    required=("clip_id", "new_in_sec", "new_out_sec"),
)


DELETE_CLIP = ToolDef(
    name="pyagent_delete_clip",
    label="Delete clip",
    description="Remove a clip from the timeline.",
    op="delete_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S},
    required=("clip_id",),
)


TOOLS = [INSERT_CLIP, APPEND_CLIP, MOVE_CLIP, TRIM_CLIP, DELETE_CLIP]


# --- Wrapper functions (Phase 4 Task 7) ---


def _track_id(track_index: int) -> str:
    return f"track_{int(track_index)}"


def insert_clip(args: dict, project_path: str) -> dict:
    """Add a clip to the timeline at the given position."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    asset_hash = args.get("asset_hash") or args.get("source_id")
    track_id = args.get("track_id") or _track_id(args["track_index"])
    position_sec = float(args.get("position_sec", 0.0))
    in_point_sec = float(args.get("in_point_sec", args.get("source_in_sec", 0.0)))
    out_point_sec = args.get("out_point_sec")
    if out_point_sec is None and args.get("source_out_sec") is not None:
        out_point_sec = float(args["source_out_sec"])
    clip_id = ir.add_clip(
        asset_hash=asset_hash,
        track_id=track_id,
        position_sec=position_sec,
        in_point_sec=in_point_sec,
        out_point_sec=out_point_sec,
    )
    return {"clip_id": clip_id}


def append_clip(args: dict, project_path: str) -> dict:
    """Append a clip to the end of the given track."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    asset_hash = args.get("asset_hash") or args.get("source_id")
    track_id = args.get("track_id") or _track_id(args["track_index"])
    in_point_sec = float(args.get("in_point_sec", args.get("source_in_sec", 0.0)))
    out_point_sec = args.get("out_point_sec")
    if out_point_sec is None and args.get("source_out_sec") is not None:
        out_point_sec = float(args["source_out_sec"])
    clip_id = ir.add_clip(
        asset_hash=asset_hash,
        track_id=track_id,
        position_sec=0.0,
        in_point_sec=in_point_sec,
        out_point_sec=out_point_sec,
    )
    return {"clip_id": clip_id}


def move_clip(args: dict, project_path: str) -> dict:
    """Move a clip to a new track/position."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    new_track_id = args.get("new_track_id") or _track_id(args["new_track"])
    ir.move_clip(
        clip_id=args["clip_id"],
        new_track_id=new_track_id,
        new_position_sec=float(args["new_position_sec"]),
    )
    return {"status": "ok"}


def trim_clip(args: dict, project_path: str) -> dict:
    """Trim a clip's in/out points."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    in_point_sec = float(
        args.get("in_point_sec")
        or args.get("new_in_point_sec")
        or args.get("new_in_sec")
    )
    out_point_sec = float(
        args.get("out_point_sec")
        or args.get("new_out_point_sec")
        or args.get("new_out_sec")
    )
    ir.trim_clip(
        clip_id=args["clip_id"],
        in_point_sec=in_point_sec,
        out_point_sec=out_point_sec,
    )
    return {"status": "ok"}


def delete_clip(args: dict, project_path: str) -> dict:
    """Remove a clip from the timeline."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    ir.remove_clip(clip_id=args["clip_id"])
    return {"status": "ok"}
