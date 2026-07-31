"""Effect, keyframe and transition operations. Pure functions.

Transitions (`_apply_add_transition`) are centered on the cut in *timeline*
coordinates. The cut is where clip_a's playback ends and clip_b's begins:

    cut = clip_a.position_sec + (clip_a.out_point_sec - clip_a.in_point_sec)

This is the only correct formulation when clip_a has been trimmed
(in_point_sec > 0): the asset-local out_point_sec is not the cut position.
Each clip's new asset-local in/out points are then back-solved so the
transition spans [cut - duration/2, cut + duration/2] on the timeline:

    new_a_out = clip_a.in_point_sec + (cut - duration/2 - clip_a.position_sec)
    new_b_in  = clip_b.in_point_sec + (cut + duration/2 - clip_b.position_sec)
"""
from __future__ import annotations

from open_edit.ir.apply_common import ApplyError, _find_clip
from open_edit.ir.types import (
    AddEffectOp,
    AddTransitionOp,
    Effect,
    RemoveEffectOp,
    RemoveKeyframeOp,
    RemoveTransitionOp,
    SetEffectParamOp,
    SetKeyframeOp,
    SetTransitionPropertyOp,
    Timeline,
)


def _apply_remove_transition(timeline: Timeline, op: RemoveTransitionOp) -> Timeline:
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            new_effects = []
            for eff in clip.effects:
                is_match = _is_transition_effect(eff, op.transition_id)
                if not is_match:
                    new_effects.append(eff)
            if len(new_effects) != len(clip.effects):
                track.clips[i] = clip.model_copy(update={"effects": new_effects})
    return timeline


def _is_transition_effect(eff: Effect, transition_id: str) -> bool:
    """Return True iff ``eff`` is the transition effect identified by ``transition_id``.

    Canonical id forms (set by ``_apply_add_transition``):
        - bare form:        ``eff.effect_id == transition_id``           (i.e. the
                            AddTransitionOp's own ``edit_id``)
        - prefixed form:    ``eff.effect_id == f"transition_{transition_id}"``

    ``clip_b_id`` is also accepted as a fallback for the rare case where a caller
    identifies a transition by its target clip's id.

    Earlier versions used ``eff.effect_id.endswith(transition_id)``; that matched
    unrelated effects whose id merely shared a suffix (e.g. transition_id="abc"
    matched effect_id="xabc"), so it was removed. Strict equality only.
    """
    return (
        eff.effect_id == transition_id
        or eff.effect_id == f"transition_{transition_id}"
        or eff.params.get("clip_b_id") == transition_id
    )


def _apply_set_transition_property(timeline: Timeline, op: SetTransitionPropertyOp) -> Timeline:
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            effects_changed = False
            new_effects = []
            for eff in clip.effects:
                is_match = _is_transition_effect(eff, op.transition_id)
                if is_match:
                    new_params = {**eff.params, op.prop_name: op.value}
                    new_effects.append(eff.model_copy(update={"params": new_params}))
                    effects_changed = True
                else:
                    new_effects.append(eff)
            if effects_changed:
                track.clips[i] = clip.model_copy(update={"effects": new_effects})
    return timeline


def _apply_remove_effect(
    timeline: Timeline, op: RemoveEffectOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"RemoveEffectOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    if 0 <= op.effect_index < len(clip.effects):
        new_effects = [eff for idx, eff in enumerate(clip.effects) if idx != op.effect_index]
        track.clips[i] = clip.model_copy(update={"effects": new_effects})
    elif strict:
        raise ApplyError(
            f"RemoveEffectOp: effect_index {op.effect_index} out of range "
            f"for clip_id '{op.clip_id}' (has {len(clip.effects)} effects)"
        )
    return timeline


def _apply_set_effect_param(
    timeline: Timeline, op: SetEffectParamOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"SetEffectParamOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    target_idx = None
    if op.effect_id:
        for idx, eff in enumerate(clip.effects):
            if eff.effect_id == op.effect_id:
                target_idx = idx
                break
    if target_idx is None and 0 <= op.effect_index < len(clip.effects):
        target_idx = op.effect_index

    if target_idx is not None and 0 <= target_idx < len(clip.effects):
        eff = clip.effects[target_idx]
        new_params = {**eff.params, op.param_name: op.value}
        new_eff = eff.model_copy(update={"params": new_params})
        new_effects = [*clip.effects]
        new_effects[target_idx] = new_eff
        track.clips[i] = clip.model_copy(update={"effects": new_effects})
    elif strict:
        raise ApplyError(
            f"SetEffectParamOp: effect_id='{op.effect_id}' / "
            f"effect_index={op.effect_index} not found on clip_id '{op.clip_id}'"
        )
    return timeline


def _apply_set_keyframe(
    timeline: Timeline, op: SetKeyframeOp, strict: bool = False,
) -> Timeline:
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
    if strict:
        raise ApplyError(
            f"SetKeyframeOp: effect_id '{op.effect_id}' not found in any clip or track"
        )
    return timeline


def _apply_remove_keyframe(
    timeline: Timeline, op: RemoveKeyframeOp, strict: bool = False,
) -> Timeline:
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            for j, eff in enumerate(clip.effects):
                if eff.effect_id == op.effect_id:
                    if op.param in eff.keyframes:
                        new_kfs = [
                            kf for kf in eff.keyframes[op.param]
                            if abs(kf[0] - op.frame) >= 1e-6
                        ]
                        updated_keyframes = {**eff.keyframes, op.param: new_kfs}
                        new_eff = eff.model_copy(update={"keyframes": updated_keyframes})
                        new_effects = [*clip.effects]
                        new_effects[j] = new_eff
                        track.clips[i] = clip.model_copy(update={"effects": new_effects})
                        return timeline
        for j, eff in enumerate(track.effects):
            if eff.effect_id == op.effect_id:
                if op.param in eff.keyframes:
                    new_kfs = [
                        kf for kf in eff.keyframes[op.param]
                        if abs(kf[0] - op.frame) >= 1e-6
                    ]
                    updated_keyframes = {**eff.keyframes, op.param: new_kfs}
                    new_eff = eff.model_copy(update={"keyframes": updated_keyframes})
                    new_effects = [*track.effects]
                    new_effects[j] = new_eff
                    idx = timeline.tracks.index(track)
                    timeline.tracks[idx] = track.model_copy(update={"effects": new_effects})
                    return timeline
    if strict:
        raise ApplyError(
            f"RemoveKeyframeOp: effect_id '{op.effect_id}' not found in any clip or track"
        )
    return timeline


def _apply_add_transition(
    timeline: Timeline, op: AddTransitionOp, strict: bool = False,
) -> Timeline:
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
    _, clip_a, _ = _find_clip(timeline, op.clip_a_id)
    if clip_a is None:
        if strict:
            raise ApplyError(
                f"AddTransitionOp: clip_a_id '{op.clip_a_id}' not found in timeline"
            )
        return timeline
    _, clip_b, _ = _find_clip(timeline, op.clip_b_id)
    if clip_b is None:
        if strict:
            raise ApplyError(
                f"AddTransitionOp: clip_b_id '{op.clip_b_id}' not found in timeline"
            )
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

    new_a_out = clip_a.in_point_sec + (cut_timeline - half - clip_a.position_sec)
    new_b_in = clip_b.in_point_sec + (cut_timeline + half - clip_b.position_sec)

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


def _apply_add_effect(
    timeline: Timeline, op: AddEffectOp, strict: bool = False,
) -> Timeline:
    if op.target_kind == "clip":
        _, clip, _ = _find_clip(timeline, op.target_id)
        if clip is None:
            if strict:
                raise ApplyError(
                    f"AddEffectOp: target clip '{op.target_id}' not found in timeline"
                )
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
        if strict:
            raise ApplyError(
                f"AddEffectOp: target track '{op.target_id}' not found in timeline"
            )
    return timeline
