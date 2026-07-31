"""Pillar timeline ops: everyday clip edits without run_script."""
from __future__ import annotations

import math
from typing import Any

from open_edit.agent.tools._contract import tool_result
from open_edit.agent.tools._helpers import load_project, make_ir
from open_edit.ir.apply import derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    ChangeClipSpeedOp,
    RemoveClipOp,
    ReplaceClipSourceOp,
    SetAudioGainOp,
    TrimClipOp,
    new_id,
)


@tool_result
def add_clip(args: dict, project_path: str) -> dict[str, Any]:
    if "asset_hash" not in args:
        return {"status": "error", "error": "asset_hash is required"}
    if args.get("out_point_sec") is None:
        return {"status": "error", "error": "out_point_sec is required (clip duration)"}
    ir = make_ir(project_path, parent_op_id=None)
    clip_id = new_id()
    track_kind = args.get("track_kind", "video")
    if track_kind not in ("video", "audio"):
        track_kind = "video"
    op = AddClipOp(
        edit_id=new_id(),
        author="ai",
        parent_id=None,
        clip_id=clip_id,
        asset_hash=str(args["asset_hash"]),
        track_id=str(args.get("track_id", "v1")),
        track_kind=track_kind,
        position_sec=float(args.get("position_sec", 0.0)),
        in_point_sec=float(args.get("in_point_sec", 0.0)),
        out_point_sec=float(args["out_point_sec"]),
    )
    ir._ops.append(op)
    return {"status": "ok", "clip_id": clip_id, "kind": "add_clip"}


@tool_result
def trim_clip(args: dict, project_path: str) -> dict[str, Any]:
    if "clip_id" not in args:
        return {"status": "error", "error": "clip_id is required"}
    out_raw = args.get("out_point_sec")
    if out_raw is None:
        return {"status": "error", "error": "out_point_sec is required"}
    in_raw = args.get("in_point_sec", 0.0)
    ir = make_ir(project_path, parent_op_id=None)
    op = TrimClipOp(
        edit_id=new_id(),
        author="ai",
        parent_id=None,
        clip_id=str(args["clip_id"]),
        new_in_point_sec=float(in_raw),
        new_out_point_sec=float(out_raw),
    )
    ir._ops.append(op)
    return {"status": "ok", "clip_id": args["clip_id"], "kind": "trim_clip"}


@tool_result
def replace_clip_source(args: dict, project_path: str) -> dict[str, Any]:
    ir = make_ir(project_path, parent_op_id=None)
    op = ReplaceClipSourceOp(
        edit_id=new_id(),
        author="ai",
        parent_id=None,
        clip_id=str(args["clip_id"]),
        new_asset_hash=str(args["new_asset_hash"]),
    )
    ir._ops.append(op)
    return {"status": "ok", "clip_id": args["clip_id"], "kind": "replace_clip_source"}


@tool_result
def change_clip_speed(args: dict, project_path: str) -> dict[str, Any]:
    ir = make_ir(project_path, parent_op_id=None)
    rate = float(args.get("rate", 1.0))
    op = ChangeClipSpeedOp(
        edit_id=new_id(),
        author="ai",
        parent_id=None,
        clip_id=str(args["clip_id"]),
        rate=rate,
    )
    ir._ops.append(op)
    return {"status": "ok", "clip_id": args["clip_id"], "kind": "change_clip_speed", "rate": rate}


@tool_result
def remove_clip(args: dict, project_path: str) -> dict[str, Any]:
    if "clip_id" not in args:
        return {"status": "error", "error": "clip_id is required"}
    ir = make_ir(project_path, parent_op_id=None)
    op = RemoveClipOp(
        edit_id=new_id(),
        author="ai",
        parent_id=None,
        clip_id=str(args["clip_id"]),
    )
    ir._ops.append(op)
    return {"status": "ok", "clip_id": args["clip_id"], "kind": "remove_clip"}


@tool_result
def set_audio_gain(args: dict, project_path: str) -> dict[str, Any]:
    """Set clip gain. Prefer ``gain_db``; ``gain`` is linear (0.0 = mute)."""
    if "clip_id" not in args:
        return {"status": "error", "error": "clip_id is required"}
    if args.get("gain_db") is not None:
        gain_db = float(args["gain_db"])
    elif args.get("gain") is not None:
        gain = float(args["gain"])
        if gain <= 0.0:
            gain_db = -120.0
        else:
            gain_db = 20.0 * math.log10(gain)
    else:
        return {"status": "error", "error": "gain or gain_db is required"}
    ir = make_ir(project_path, parent_op_id=None)
    op = SetAudioGainOp(
        edit_id=new_id(),
        author="ai",
        parent_id=None,
        clip_id=str(args["clip_id"]),
        gain_db=gain_db,
    )
    ir._ops.append(op)
    return {
        "status": "ok",
        "clip_id": args["clip_id"],
        "kind": "set_audio_gain",
        "gain_db": gain_db,
    }


def _normalize_gaps(raw_gaps: Any) -> list[tuple[float, float]]:
    gaps: list[tuple[float, float]] = []
    if not isinstance(raw_gaps, list):
        return gaps
    for g in raw_gaps:
        if isinstance(g, (list, tuple)) and len(g) >= 2:
            start, end = float(g[0]), float(g[1])
        elif isinstance(g, dict):
            start = float(g.get("t_start", g.get("start_sec", g.get("start", 0))))
            end = float(g.get("t_end", g.get("end_sec", g.get("end", 0))))
        else:
            continue
        if end > start:
            gaps.append((start, end))
    gaps.sort(key=lambda x: x[0])
    return gaps


def _keep_ranges(
    in_point: float, out_point: float, gaps: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Invert silence gaps into keep ranges inside [in_point, out_point]."""
    keeps: list[tuple[float, float]] = []
    cursor = in_point
    for start, end in gaps:
        g0 = max(start, in_point)
        g1 = min(end, out_point)
        if g1 <= g0:
            continue
        if g0 > cursor:
            keeps.append((cursor, g0))
        cursor = max(cursor, g1)
    if cursor < out_point:
        keeps.append((cursor, out_point))
    return [(a, b) for a, b in keeps if b - a > 1e-4]


@tool_result
def apply_silence_gaps(args: dict, project_path: str) -> dict[str, Any]:
    """Replace a clip with keep-segments after removing silence gaps.

    Gaps are source-time intervals (same as ``generate=silence_cuts``).
    """
    clip_id = args.get("clip_id")
    if not clip_id:
        return {"status": "error", "error": "clip_id is required"}
    gaps = _normalize_gaps(args.get("gaps"))
    if not gaps:
        return {"status": "error", "error": "gaps must be a non-empty list"}

    project = load_project(project_path)
    timeline = derive_timeline(project)
    track = None
    clip = None
    for t in timeline.tracks:
        for c in t.clips:
            if c.clip_id == clip_id:
                track, clip = t, c
                break
        if clip is not None:
            break
    if clip is None or track is None:
        return {"status": "error", "error": f"clip_id {clip_id!r} not found"}

    keeps = _keep_ranges(clip.in_point_sec, clip.out_point_sec, gaps)
    if not keeps:
        return {"status": "error", "error": "gaps remove the entire clip; refusing"}

    ir = make_ir(project_path, parent_op_id=None)
    ir._ops.append(
        RemoveClipOp(
            edit_id=new_id(),
            author="ai",
            parent_id=None,
            clip_id=str(clip_id),
        )
    )

    new_ids: list[str] = []
    pos = float(clip.position_sec)
    for inn, outt in keeps:
        nid = new_id()
        new_ids.append(nid)
        ir._ops.append(
            AddClipOp(
                edit_id=new_id(),
                author="ai",
                parent_id=None,
                clip_id=nid,
                asset_hash=str(clip.asset_hash),
                track_id=str(track.track_id),
                track_kind=track.kind,
                position_sec=pos,
                in_point_sec=float(inn),
                out_point_sec=float(outt),
            )
        )
        pos += float(outt) - float(inn)

    return {
        "status": "ok",
        "kind": "apply_silence_gaps",
        "removed_clip_id": clip_id,
        "new_clip_ids": new_ids,
        "keep_count": len(keeps),
    }
