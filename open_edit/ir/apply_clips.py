"""Clip-shape operations: slip, ripple delete, speed, split, source replace
and speed ramp. Pure functions.
"""
from __future__ import annotations

from open_edit.ir.apply_common import ApplyError, _find_clip
from open_edit.ir.types import (
    ChangeClipSpeedOp,
    Effect,
    ReplaceClipSourceOp,
    RippleDeleteClipOp,
    SetClipSpeedRampOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
)


def _apply_slip_clip(
    timeline: Timeline, op: SlipClipOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"SlipClipOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    new_clip = clip.model_copy(update={
        "in_point_sec": clip.in_point_sec + op.delta_sec,
        "out_point_sec": clip.out_point_sec + op.delta_sec,
    })
    track.clips[i] = new_clip
    return timeline


def _apply_ripple_delete_clip(
    timeline: Timeline, op: RippleDeleteClipOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"RippleDeleteClipOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    duration = clip.out_point_sec - clip.in_point_sec
    removed_pos = clip.position_sec
    track.clips.pop(i)
    new_clips = []
    for c in track.clips:
        if c.position_sec > removed_pos:
            shifted_pos = max(0.0, c.position_sec - duration)
            new_clips.append(c.model_copy(update={"position_sec": shifted_pos}))
        else:
            new_clips.append(c)
    track.clips = new_clips
    return timeline


def _apply_change_clip_speed(
    timeline: Timeline, op: ChangeClipSpeedOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"ChangeClipSpeedOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    speed_effect_found = False
    new_effects = []
    for eff in clip.effects:
        if eff.effect_type == "speed":
            new_eff = eff.model_copy(update={"params": {**eff.params, "rate": op.rate}})
            new_effects.append(new_eff)
            speed_effect_found = True
        else:
            new_effects.append(eff)
    if not speed_effect_found:
        new_effects.append(Effect(
            effect_id=op.edit_id,
            effect_type="speed",
            params={"rate": op.rate},
        ))
    track.clips[i] = clip.model_copy(update={"effects": new_effects})
    return timeline


def _apply_split_clip(
    timeline: Timeline, op: SplitClipOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"SplitClipOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    clip_dur = clip.out_point_sec - clip.in_point_sec
    clip_end_timeline = clip.position_sec + clip_dur
    if op.at_sec <= clip.position_sec or op.at_sec >= clip_end_timeline:
        # at_sec out of range is a geometric check, not a reference lookup;
        # leave the silent no-op behavior alone in both strict and non-strict.
        return timeline
    split_offset = op.at_sec - clip.position_sec

    left_effects = [e.model_copy(deep=True) for e in clip.effects]
    right_effects = [e.model_copy(deep=True) for e in clip.effects]
    left_clip = clip.model_copy(update={
        "clip_id": op.left_clip_id,
        "out_point_sec": clip.in_point_sec + split_offset,
        "effects": left_effects,
    })
    right_clip = clip.model_copy(update={
        "clip_id": op.right_clip_id,
        "position_sec": op.at_sec,
        "in_point_sec": clip.in_point_sec + split_offset,
        "effects": right_effects,
    })
    track.clips[i:i + 1] = [left_clip, right_clip]
    return timeline


def _apply_replace_clip_source(
    timeline: Timeline, op: ReplaceClipSourceOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"ReplaceClipSourceOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    track.clips[i] = clip.model_copy(update={"asset_hash": op.new_asset_hash})
    return timeline


def _apply_set_clip_speed_ramp(
    timeline: Timeline, op: SetClipSpeedRampOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"SetClipSpeedRampOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    ramp_effect_found = False
    new_effects = []
    for eff in clip.effects:
        if eff.effect_type == "speed_ramp":
            new_eff = eff.model_copy(update={"params": {"keyframes": op.keyframes}})
            new_effects.append(new_eff)
            ramp_effect_found = True
        else:
            new_effects.append(eff)
    if not ramp_effect_found:
        new_effects.append(Effect(
            effect_id=op.edit_id,
            effect_type="speed_ramp",
            params={"keyframes": op.keyframes},
        ))
    track.clips[i] = clip.model_copy(update={"effects": new_effects})
    return timeline
