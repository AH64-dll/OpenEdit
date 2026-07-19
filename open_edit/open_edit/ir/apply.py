"""Apply operations to derive Timeline state. Pure functions.

The Bug A fix lives in `_apply_add_transition`:
- The transition is placed at `cut = clip_a.out_point_sec` (the cut point).
- `clip_a.out_point_sec` is back-solved to `cut - duration_sec / 2`.
- `clip_b.in_point_sec` is back-solved to `cut + duration_sec / 2`.
- This means the transition is centered on the cut, NOT on the midpoint
  of the two clips' original positions.
"""
from __future__ import annotations

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    Clip,
    Effect,
    MoveClipOp,
    OperationUnion,
    Project,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    Timeline,
    Track,
    TrimClipOp,
)


def _get_or_create_track(timeline: Timeline, track_id: str, kind: str) -> Track:
    for track in timeline.tracks:
        if track.track_id == track_id:
            return track
    new_track = Track(track_id=track_id, kind=kind)
    timeline.tracks.append(new_track)
    return new_track


def _find_clip(timeline: Timeline, clip_id: str):
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            if clip.clip_id == clip_id:
                return track, clip, i
    return None, None, None


def _make_clip(op: AddClipOp, out_point_sec: float) -> Clip:
    return Clip(
        clip_id=op.clip_id,
        asset_hash=op.asset_hash,
        track_id=op.track_id,
        track_kind=op.track_kind,
        position_sec=op.position_sec,
        in_point_sec=op.in_point_sec,
        out_point_sec=out_point_sec,
        effects=[],
    )


def apply_operation(timeline: Timeline, op: OperationUnion) -> Timeline:
    """Apply a single operation to a timeline. Returns a new timeline.

    Pure function. Does not mutate the input.
    """
    if op.status != "applied":
        return timeline

    if isinstance(op, AddClipOp):
        track = _get_or_create_track(timeline, op.track_id, op.track_kind)
        out_val = op.out_point_sec if op.out_point_sec is not None else 0.0
        track.clips.append(_make_clip(op, out_val))
        return timeline
    if isinstance(op, RemoveClipOp):
        for track in timeline.tracks:
            track.clips = [c for c in track.clips if c.clip_id != op.clip_id]
        return timeline
    if isinstance(op, MoveClipOp):
        track, clip, i = _find_clip(timeline, op.clip_id)
        if clip is None:
            return timeline
        track.clips.pop(i)
        new_track = _get_or_create_track(timeline, op.new_track_id, clip.track_kind)
        moved = clip.model_copy(update={
            "track_id": op.new_track_id,
            "position_sec": op.new_position_sec,
        })
        new_track.clips.append(moved)
        return timeline
    if isinstance(op, TrimClipOp):
        _, clip, _ = _find_clip(timeline, op.clip_id)
        if clip is None:
            return timeline
        new_clip = clip.model_copy(update={
            "in_point_sec": op.new_in_point_sec,
            "out_point_sec": op.new_out_point_sec,
        })
        for track in timeline.tracks:
            for i, c in enumerate(track.clips):
                if c.clip_id == op.clip_id:
                    track.clips[i] = new_clip
                    return timeline
        return timeline
    if isinstance(op, AddTransitionOp):
        return _apply_add_transition(timeline, op)
    if isinstance(op, AddEffectOp):
        return _apply_add_effect(timeline, op)
    if isinstance(op, SetKeyframeOp):
        return _apply_set_keyframe(timeline, op)
    if isinstance(op, SetAudioGainOp):
        return _apply_set_audio_gain(timeline, op)
    return timeline


def _apply_add_transition(timeline: Timeline, op: AddTransitionOp) -> Timeline:
    """Apply an AddTransitionOp.

    The transition is centered on the cut in TIMELINE coordinates. The cut
    is the timeline position where clip_a's playback ends and clip_b's
    playback begins:

        cut_timeline = clip_a.position_sec + (clip_a.out_point_sec - clip_a.in_point_sec)

    This is the only correct formulation when clip_a has been previously
    trimmed (in_point_sec > 0): the asset-local out_point_sec is not
    the cut position.

    After computing cut_timeline we back-solve each clip's new asset-local
    in/out points so the transition spans [cut - duration/2, cut + duration/2]
    on the timeline.
    """
    track_a, clip_a, _ = _find_clip(timeline, op.clip_a_id)
    if clip_a is None:
        return timeline
    _, clip_b, _ = _find_clip(timeline, op.clip_b_id)
    if clip_b is None:
        return timeline

    cut_timeline = clip_a.position_sec + (clip_a.out_point_sec - clip_a.in_point_sec)
    half = op.duration_sec / 2.0
    clip_b_duration = clip_b.out_point_sec - clip_b.in_point_sec
    clip_b_end_timeline = clip_b.position_sec + clip_b_duration

    if cut_timeline - half < clip_a.position_sec:
        raise ValueError(
            f"AddTransitionOp: duration_sec {op.duration_sec} too large "
            f"for clip_a (cut_timeline={cut_timeline}, "
            f"position={clip_a.position_sec})"
        )
    if cut_timeline + half > clip_b_end_timeline:
        raise ValueError(
            f"AddTransitionOp: duration_sec {op.duration_sec} too large "
            f"for clip_b (end_timeline={clip_b_end_timeline})"
        )

    new_a_out = (cut_timeline - half) - clip_a.position_sec
    new_b_in = (cut_timeline + half) - clip_b.position_sec

    if new_a_out < clip_a.in_point_sec:
        raise ValueError(
            f"AddTransitionOp: clip_a asset range would invert "
            f"(in={clip_a.in_point_sec}, new_out={new_a_out}). "
            f"fix: shorten duration_sec or trim clip_a less."
        )
    if new_b_in > clip_b.out_point_sec:
        raise ValueError(
            f"AddTransitionOp: clip_b asset range would invert "
            f"(out={clip_b.out_point_sec}, new_in={new_b_in}). "
            f"fix: shorten duration_sec or trim clip_b less."
        )

    new_clip_a = clip_a.model_copy(update={"out_point_sec": new_a_out})
    new_clip_b = clip_b.model_copy(update={"in_point_sec": new_b_in})

    transition_effect = Effect(
        effect_id=f"transition_{op.edit_id}",
        effect_type=f"transition_{op.transition_type}",
        params={"clip_b_id": op.clip_b_id, "duration_sec": op.duration_sec},
    )
    new_clip_a = new_clip_a.model_copy(update={
        "effects": [*new_clip_a.effects, transition_effect],
    })

    for track in timeline.tracks:
        for i, c in enumerate(track.clips):
            if c.clip_id == op.clip_a_id:
                track.clips[i] = new_clip_a
            elif c.clip_id == op.clip_b_id:
                track.clips[i] = new_clip_b
    return timeline


def _apply_add_effect(timeline: Timeline, op: AddEffectOp) -> Timeline:
    if op.target_kind == "clip":
        _, clip, _ = _find_clip(timeline, op.target_id)
        if clip is None:
            return timeline
        new_effect = Effect(
            effect_id=op.effect_id, effect_type=op.effect_type, params=op.params,
        )
        new_clip = clip.model_copy(update={"effects": [*clip.effects, new_effect]})
        for track in timeline.tracks:
            for i, c in enumerate(track.clips):
                if c.clip_id == op.target_id:
                    track.clips[i] = new_clip
                    return timeline
    elif op.target_kind == "track":
        for track in timeline.tracks:
            if track.track_id == op.target_id:
                new_effect = Effect(
                    effect_id=op.effect_id, effect_type=op.effect_type, params=op.params,
                )
                new_track = track.model_copy(update={
                    "effects": [*track.effects, new_effect],
                })
                idx = timeline.tracks.index(track)
                timeline.tracks[idx] = new_track
                return timeline
    return timeline


def _apply_set_keyframe(timeline: Timeline, op: SetKeyframeOp) -> Timeline:
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            for j, eff in enumerate(clip.effects):
                if eff.effect_id == op.effect_id:
                    new_eff = eff.model_copy(update={
                        "keyframes": {**eff.keyframes, op.param: op.keyframes},
                    })
                    new_clip = clip.model_copy(update={
                        "effects": [new_eff if k == j else e for k, e in enumerate(clip.effects)],
                    })
                    track.clips[i] = new_clip
                    return timeline
    return timeline


def _apply_set_audio_gain(timeline: Timeline, op: SetAudioGainOp) -> Timeline:
    _, clip, _ = _find_clip(timeline, op.clip_id)
    if clip is None or clip.track_kind != "audio":
        return timeline
    linear_gain = 10 ** (op.gain_db / 20.0)
    new_effect = Effect(
        effect_id=op.edit_id, effect_type="volume",
        params={"gain": linear_gain},
    )
    new_clip = clip.model_copy(update={"effects": [*clip.effects, new_effect]})
    for track in timeline.tracks:
        for i, c in enumerate(track.clips):
            if c.clip_id == op.clip_id:
                track.clips[i] = new_clip
                return timeline
    return timeline


def derive_timeline(project: Project) -> Timeline:
    """Replay all non-reverted, applied operations in sequence order."""
    timeline = Timeline()
    for op in project.edit_graph:
        timeline = apply_operation(timeline, op)
    max_end = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            end = clip.position_sec + (clip.out_point_sec - clip.in_point_sec)
            if end > max_end:
                max_end = end
    timeline.duration_sec = max_end
    return timeline
