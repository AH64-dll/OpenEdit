"""Pillar timeline ops: everyday clip edits without run_script."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import tool_result
from open_edit.agent.tools._helpers import load_project, make_ir
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddHtmlOverlayOp,
    ChangeClipSpeedOp,
    RemoveClipOp,
    ReplaceClipSourceOp,
    SetAudioGainOp,
    TrimClipOp,
    new_id,
)


@tool_result
def add_hyperframes_overlay(args: dict, project_path: str) -> dict[str, Any]:
    template_path = str(args.get("template_path") or "").strip()
    if not template_path:
        return {
            "status": "error",
            "error": "template_path is required",
            "expected_keys": ["template_path", "position_sec", "duration_sec"],
        }
    try:
        position_sec = float(args.get("position_sec", 0.0))
        duration_sec = float(args.get("duration_sec", 0.0))
    except (TypeError, ValueError):
        return {"status": "error", "error": "position_sec and duration_sec must be numbers"}
    if position_sec < 0 or duration_sec <= 0:
        return {"status": "error", "error": "position_sec must be >= 0 and duration_sec must be > 0"}
    project_root = Path(project_path).resolve()
    template = (project_root / template_path).resolve()
    if template_path.startswith(("/", "\\")) or ".." in Path(template_path).parts:
        return {"status": "error", "error": "template_path must stay inside project"}
    if not template.is_relative_to(project_root):
        return {"status": "error", "error": "template_path escapes project"}
    if not template.is_file():
        return {"status": "error", "error": f"template not found: {template_path}"}
    overlay_id = new_id()
    make_ir(project_path, parent_op_id=None)._ops.append(AddHtmlOverlayOp(
        edit_id=new_id(),
        author="ai",
        overlay_id=overlay_id,
        template_path=template_path,
        variables=args.get("variables") if isinstance(args.get("variables"), dict) else {},
        position_sec=position_sec,
        duration_sec=duration_sec,
    ))
    return {
        "status": "ok",
        "kind": "add_html_overlay",
        "overlay_id": overlay_id,
        "engine": "hyperframes",
    }


@tool_result
def add_clip(args: dict, project_path: str) -> dict[str, Any]:
    if "asset_hash" not in args:
        return {"status": "error", "error": "asset_hash is required"}
    if args.get("out_point_sec") is None:
        return {"status": "error", "error": "out_point_sec is required (clip duration)"}
    asset_hash = str(args["asset_hash"])
    # Reject unknown/truncated hashes up front: a bad hash used to surface
    # only at render time as an opaque melt "failed to load producer" error.
    from open_edit.storage.assets import list_assets_from_disk
    from open_edit.storage.paths import ProjectPaths

    project_root = ProjectPaths.for_project(project_path).root
    known = {a.asset_hash for a in list_assets_from_disk(project_root)}
    # Only reject when the project actually HAS assets: an empty project
    # (unit tests, first-use) may legitimately reference a not-yet-ingested
    # hash, and the render-time failure would be opaque either way.
    if known and asset_hash not in known:
        return {
            "status": "error",
            "error": f"asset not found in project: {asset_hash[:24]}... "
                     f"(get the exact hash from list_assets)",
        }
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
        asset_hash=asset_hash,
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


def _snap_edge_to_word(
    alignment: list[Any],
    edge: float,
    *,
    direction: str,
    tolerance_s: float,
    clamp_low: float,
    clamp_high: float,
) -> float:
    """Snap a keep-range edge to the nearest word boundary (video-use rule 6).

    "Never cut inside a word": a start edge snaps DOWN to the nearest word
    start within tolerance (keeps the whole word), an end edge snaps UP to the
    nearest word end within tolerance. Edges already in silence snap to the
    nearest boundary in the outward direction; if nothing is within tolerance
    the edge is returned unchanged.
    """
    best: float | None = None
    best_delta: float = float("inf")
    for w in alignment:
        for boundary in (float(w.t_start), float(w.t_end)):
            delta = boundary - edge
            if direction == "start" and delta > tolerance_s:
                continue
            if direction == "end" and delta < -tolerance_s:
                continue
            if abs(delta) < best_delta:
                best_delta = abs(delta)
                best = boundary
    if best is None:
        return edge
    return max(clamp_low, min(clamp_high, best))


def _pad_and_snap_keeps(
    keeps: list[tuple[float, float]],
    in_point: float,
    out_point: float,
    alignment: list[Any] | None,
    padding_ms: int,
    snap_to_words: bool,
    snap_tolerance_ms: int = 60,
) -> list[tuple[float, float]]:
    """Apply video-use cut-craft: word-boundary snapping + 30-200ms padding.

    Snapping runs first (on the raw keep edges), then padding expands each
    keep outward by ``padding_ms`` so every cut carries a little air, then
    overlaps are merged and everything is clamped to the clip range.
    """
    if not keeps:
        return keeps
    pad_s = padding_ms / 1000.0
    tol_s = snap_tolerance_ms / 1000.0
    snapped: list[tuple[float, float]] = []
    for a, b in keeps:
        a2, b2 = a, b
        if alignment and snap_to_words:
            a2 = _snap_edge_to_word(alignment, a, direction="start", tolerance_s=tol_s,
                                    clamp_low=in_point, clamp_high=b)
            b2 = _snap_edge_to_word(alignment, b, direction="end", tolerance_s=tol_s,
                                    clamp_low=a2, clamp_high=out_point)
        a2 = max(in_point, a2 - pad_s)
        b2 = min(out_point, b2 + pad_s)
        snapped.append((a2, b2))
    snapped.sort()
    merged: list[tuple[float, float]] = []
    for a, b in snapped:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


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

    # video-use merge: optional word-boundary snapping + cut-edge padding
    padding_ms = int(args.get("padding_ms", 0) or 0)
    snap_to_words = bool(args.get("snap_to_words", False))
    snap_tolerance_ms = int(args.get("snap_tolerance_ms", 60) or 60)
    if padding_ms < 0 or padding_ms > 500:
        return {"status": "error", "error": "padding_ms must be in [0, 500]"}
    alignment: list[Any] | None = None
    if snap_to_words or padding_ms:
        from open_edit.storage.assets import list_assets_from_disk
        from open_edit.storage.paths import ProjectPaths

        project_root = ProjectPaths.for_project(project_path).root
        for asset in list_assets_from_disk(project_root):
            if asset.asset_hash == clip.asset_hash:
                alignment = asset.alignment
                break

    keeps = _keep_ranges(clip.in_point_sec, clip.out_point_sec, gaps)
    if not keeps:
        return {"status": "error", "error": "gaps remove the entire clip; refusing"}
    keeps = _pad_and_snap_keeps(
        keeps,
        in_point=clip.in_point_sec,
        out_point=clip.out_point_sec,
        alignment=alignment,
        padding_ms=padding_ms,
        snap_to_words=snap_to_words,
        snap_tolerance_ms=snap_tolerance_ms,
    )
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


@tool_result
def auto_color_grade(args: dict, project_path: str) -> dict[str, Any]:
    """Analyze video clip(s) and append per-clip ``color_grade`` effects.

    Ported from browser-use/video-use ``helpers/grade.py`` auto mode: samples
    ~10 frames of each clip's source range with ffmpeg ``signalstats`` and
    emits a bounded eq correction (contrast/gamma/saturation, each clamped to
    +/-8%) as an ``AddEffectOp`` (MLT ``avfilter.eq``).

    Args:
        clip_ids: optional list (or single string) of clip ids. Defaults to
            ALL video clips in the timeline.
        preset: "auto" (default, per-clip analysis) | "subtle" |
            "neutral_punch" | "warm_cinematic" | "none". Creative presets only
            apply their eq components; curves/colorbalance extras are skipped.
        params: optional explicit {contrast, gamma, saturation} overrides
            (only honored with preset="auto", merged over the analysis).

    Returns per-clip applied effect ids + params.
    """
    from open_edit.render.color_grade import (
        auto_grade_params,
        known_presets,
        preset_eq_params,
    )

    preset = str(args.get("preset") or "auto").strip()
    explicit = args.get("params")
    if explicit is not None and not isinstance(explicit, dict):
        return {"status": "error", "error": "params must be a dict {contrast, gamma, saturation}"}

    raw_ids = args.get("clip_ids")
    clip_ids: list[str] | None
    if isinstance(raw_ids, str):
        clip_ids = [raw_ids]
    elif isinstance(raw_ids, list) and raw_ids:
        clip_ids = [str(x) for x in raw_ids]
    else:
        clip_ids = None  # all video clips

    if preset != "auto" and preset not in known_presets():
        return {
            "status": "error",
            "error": f"unknown preset {preset!r}; use 'auto' or one of {known_presets()}",
        }

    project = load_project(project_path)
    timeline = derive_timeline(project)

    # load_project deliberately keeps assets empty; pull the CAS index here.
    from open_edit.storage.assets import list_assets_from_disk
    from open_edit.storage.paths import ProjectPaths

    project_root = ProjectPaths.for_project(project_path).root
    asset_index = {a.asset_hash: a for a in list_assets_from_disk(project_root)}

    targets: list[Any] = []
    for t in timeline.tracks:
        for c in t.clips:
            if c.track_kind != "video":
                continue
            if clip_ids is None or c.clip_id in clip_ids:
                targets.append((t, c))
    if not targets:
        return {"status": "error", "error": "no matching video clips in timeline"}

    ir = make_ir(project_path, parent_op_id=None)
    applied: list[dict[str, Any]] = []
    for _track, clip in targets:
        asset = asset_index.get(clip.asset_hash)
        if asset is None or not (asset.stored_path or asset.original_path):
            continue
        src = Path(asset.stored_path or asset.original_path)
        if not Path(src).is_file():
            continue

        if explicit:
            # Merge explicit overrides over auto analysis
            params = auto_grade_params(
                Path(src),
                start=float(clip.in_point_sec),
                duration=max(float(clip.out_point_sec) - float(clip.in_point_sec), 0.1),
            )
            for key in ("contrast", "gamma", "saturation"):
                if key in explicit:
                    try:
                        params[key] = float(explicit[key])
                    except (TypeError, ValueError):
                        return {"status": "error", "error": f"params.{key} must be numeric"}
        elif preset == "auto":
            params = auto_grade_params(
                Path(src),
                start=float(clip.in_point_sec),
                duration=max(float(clip.out_point_sec) - float(clip.in_point_sec), 0.1),
            )
        else:
            params = preset_eq_params(preset)
        if not params:
            continue  # preset "none" (skip)

        effect_id = new_id()
        ir._ops.append(
            AddEffectOp(
                edit_id=new_id(),
                author="ai",
                parent_id=None,
                effect_id=effect_id,
                target_kind="clip",
                target_id=clip.clip_id,
                effect_type="color_grade",
                params=params,
            )
        )
        applied.append({
            "clip_id": clip.clip_id,
            "effect_id": effect_id,
            "params": params,
        })

    if not applied:
        return {"status": "error", "error": "no gradeable clips found (missing asset paths)"}
    return {"status": "ok", "kind": "auto_color_grade", "applied": applied, "preset": preset}
