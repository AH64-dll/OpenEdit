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
    AddHtmlOverlayOp,
    AddTransitionOp,
    ChangeClipSpeedOp,
    Clip,
    Effect,
    FreeFormCodeOp,
    GroupEditsOp,
    HtmlOverlay,
    MoveClipOp,
    NormalizeAudioOp,
    OperationUnion,
    Project,
    RawMltXmlOp,
    RemoveClipOp,
    RemoveEffectOp,
    RemoveHtmlOverlayOp,
    RemoveKeyframeOp,
    RemoveTransitionOp,
    ReplaceClipSourceOp,
    RippleDeleteClipOp,
    SetAudioGainOp,
    SetClipSpeedRampOp,
    SetEffectParamOp,
    SetKeyframeOp,
    SetTransitionPropertyOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
    Track,
    TrimClipOp,
    UngroupEditsOp,
)


class ApplyError(Exception):
    """Raised when an op cannot be applied to the timeline."""


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
    if isinstance(op, RemoveTransitionOp):
        return _apply_remove_transition(timeline, op)
    if isinstance(op, SetTransitionPropertyOp):
        return _apply_set_transition_property(timeline, op)
    if isinstance(op, AddEffectOp):
        return _apply_add_effect(timeline, op)
    if isinstance(op, RemoveEffectOp):
        return _apply_remove_effect(timeline, op)
    if isinstance(op, SetEffectParamOp):
        return _apply_set_effect_param(timeline, op)
    if isinstance(op, SetKeyframeOp):
        return _apply_set_keyframe(timeline, op)
    if isinstance(op, RemoveKeyframeOp):
        return _apply_remove_keyframe(timeline, op)
    if isinstance(op, SlipClipOp):
        return _apply_slip_clip(timeline, op)
    if isinstance(op, RippleDeleteClipOp):
        return _apply_ripple_delete_clip(timeline, op)
    if isinstance(op, ChangeClipSpeedOp):
        return _apply_change_clip_speed(timeline, op)
    if isinstance(op, SplitClipOp):
        return _apply_split_clip(timeline, op)
    if isinstance(op, ReplaceClipSourceOp):
        return _apply_replace_clip_source(timeline, op)
    if isinstance(op, SetClipSpeedRampOp):
        return _apply_set_clip_speed_ramp(timeline, op)
    if isinstance(op, SetAudioGainOp):
        return _apply_set_audio_gain(timeline, op)
    if isinstance(op, NormalizeAudioOp):
        return _apply_normalize_audio(timeline, op)
    if isinstance(op, (GroupEditsOp, UngroupEditsOp, RawMltXmlOp, FreeFormCodeOp)):
        return timeline
    if isinstance(op, AddHtmlOverlayOp):
        overlay = HtmlOverlay(
            overlay_id=op.overlay_id,
            template_path=op.template_path,
            variables=op.variables,
            position_sec=op.position_sec,
            duration_sec=op.duration_sec,
        )
        timeline.overlays.append(overlay)
        timeline.overlays.sort(key=lambda o: o.position_sec)
        return timeline
    if isinstance(op, RemoveHtmlOverlayOp):
        timeline.overlays = [
            o for o in timeline.overlays if o.overlay_id != op.overlay_id
        ]
        return timeline
    return timeline


def _apply_remove_transition(timeline: Timeline, op: RemoveTransitionOp) -> Timeline:
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            new_effects = []
            for eff in clip.effects:
                is_match = (
                    eff.effect_id == op.transition_id
                    or eff.effect_id == f"transition_{op.transition_id}"
                    or eff.params.get("clip_b_id") == op.transition_id
                    or eff.effect_id.endswith(op.transition_id)
                )
                if not is_match:
                    new_effects.append(eff)
            if len(new_effects) != len(clip.effects):
                track.clips[i] = clip.model_copy(update={"effects": new_effects})
    return timeline


def _apply_set_transition_property(timeline: Timeline, op: SetTransitionPropertyOp) -> Timeline:
    for track in timeline.tracks:
        for i, clip in enumerate(track.clips):
            effects_changed = False
            new_effects = []
            for eff in clip.effects:
                is_match = (
                    eff.effect_id == op.transition_id
                    or eff.effect_id == f"transition_{op.transition_id}"
                    or eff.params.get("clip_b_id") == op.transition_id
                    or eff.effect_id.endswith(op.transition_id)
                )
                if is_match:
                    new_params = {**eff.params, op.prop_name: op.value}
                    new_effects.append(eff.model_copy(update={"params": new_params}))
                    effects_changed = True
                else:
                    new_effects.append(eff)
            if effects_changed:
                track.clips[i] = clip.model_copy(update={"effects": new_effects})
    return timeline


def _apply_remove_effect(timeline: Timeline, op: RemoveEffectOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        return timeline
    if 0 <= op.effect_index < len(clip.effects):
        new_effects = [eff for idx, eff in enumerate(clip.effects) if idx != op.effect_index]
        track.clips[i] = clip.model_copy(update={"effects": new_effects})
    return timeline


def _apply_set_effect_param(timeline: Timeline, op: SetEffectParamOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
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
    return timeline


def _apply_remove_keyframe(timeline: Timeline, op: RemoveKeyframeOp) -> Timeline:
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
    return timeline


def _apply_slip_clip(timeline: Timeline, op: SlipClipOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        return timeline
    new_clip = clip.model_copy(update={
        "in_point_sec": clip.in_point_sec + op.delta_sec,
        "out_point_sec": clip.out_point_sec + op.delta_sec,
    })
    track.clips[i] = new_clip
    return timeline


def _apply_ripple_delete_clip(timeline: Timeline, op: RippleDeleteClipOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
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


def _apply_change_clip_speed(timeline: Timeline, op: ChangeClipSpeedOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
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


def _apply_split_clip(timeline: Timeline, op: SplitClipOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        return timeline
    clip_dur = clip.out_point_sec - clip.in_point_sec
    clip_end_timeline = clip.position_sec + clip_dur
    if op.at_sec <= clip.position_sec or op.at_sec >= clip_end_timeline:
        return timeline
    split_offset = op.at_sec - clip.position_sec

    left_clip = clip.model_copy(update={
        "clip_id": op.left_clip_id,
        "out_point_sec": clip.in_point_sec + split_offset,
    })
    right_clip = clip.model_copy(update={
        "clip_id": op.right_clip_id,
        "position_sec": op.at_sec,
        "in_point_sec": clip.in_point_sec + split_offset,
    })
    track.clips[i:i + 1] = [left_clip, right_clip]
    return timeline


def _apply_replace_clip_source(timeline: Timeline, op: ReplaceClipSourceOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        return timeline
    track.clips[i] = clip.model_copy(update={"asset_hash": op.new_asset_hash})
    return timeline


def _apply_set_clip_speed_ramp(timeline: Timeline, op: SetClipSpeedRampOp) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
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


def _apply_normalize_audio(timeline: Timeline, op: NormalizeAudioOp) -> Timeline:
    """Add a 'volume' effect tagged with the target_dbfs to the target.

    Without a real LUFS measurement at apply time, we cannot compute the
    linear gain needed to hit op.target_dbfs. The effect is tagged with
    target_dbfs and a `normalize: true` flag so the future render
    pipeline (Phase 4) can compute the actual gain during audio analysis
    and override the placeholder before melt runs.
    """
    if op.target_kind == "clip":
        _, clip, _ = _find_clip(timeline, op.target_id)
        if clip is None:
            return timeline
        new_effect = Effect(
            effect_id=op.edit_id, effect_type="volume",
            params={
                "gain": 1.0,
                "target_dbfs": op.target_dbfs,
                "normalize": True,
            },
        )
        new_clip = clip.model_copy(update={"effects": [*clip.effects, new_effect]})
        for track in timeline.tracks:
            for i, c in enumerate(track.clips):
                if c.clip_id == op.target_id:
                    track.clips[i] = new_clip
                    return timeline
        return timeline
    if op.target_kind == "track":
        for track in timeline.tracks:
            if track.track_id == op.target_id:
                new_effect = Effect(
                    effect_id=op.edit_id, effect_type="volume",
                    params={
                        "gain": 1.0,
                        "target_dbfs": op.target_dbfs,
                        "normalize": True,
                    },
                )
                new_track = track.model_copy(update={
                    "effects": [*track.effects, new_effect],
                })
                idx = timeline.tracks.index(track)
                timeline.tracks[idx] = new_track
                return timeline
        return timeline
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
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        return timeline
    linear_gain = 10 ** (op.gain_db / 20.0)
    new_effect = Effect(
        effect_id=op.edit_id, effect_type="volume",
        params={"gain": linear_gain},
    )
    new_clip = clip.model_copy(update={"effects": [*clip.effects, new_effect]})
    track.clips[i] = new_clip
    return timeline


def _apply_free_form_code(op: FreeFormCodeOp, project: Project) -> Project:
    """Run a free-form Python script in the sandbox and append its child ops.

    Each child op has parent_id == op.edit_id (stamped by IR at build time).

    Not invoked from `apply_operation` because that function is timeline-derive
    code (pure: Timeline → Timeline). Free-form intake mutates a Project's
    edit_graph; call this directly when processing a user-submitted script.
    The dispatch in `apply_operation` is a no-op so `derive_timeline` can
    safely replay a `FreeFormCodeOp` from the graph without re-running it.
    """
    from open_edit.agent.sandbox_bridge import run_free_form
    result = run_free_form(
        code=op.code,
        workdir=project.workdir,
        project_id=project.project_id,
        parent_op_id=op.edit_id,
        timeout=op.timeout_sec,
        mem_mb=op.mem_mb,
        originating_note_id=op.originating_note_id,
    )
    if not result.success:
        raise ApplyError(f"free-form run failed: {result.reason}: {result.detail}")
    project.edit_graph.extend(result.ops)
    return project


def derive_timeline(project: Project) -> Timeline:
    """Replay all non-reverted, applied operations in sequence order."""
    timeline = Timeline()
    if not project.edit_graph:
        return timeline

    op_by_id = {op.edit_id: op for op in project.edit_graph}

    for op in project.edit_graph:
        if op.status != "applied":
            continue

        curr_parent = op.parent_id
        parent_reverted = False
        while curr_parent:
            parent_op = op_by_id.get(curr_parent)
            if parent_op is not None and parent_op.status != "applied":
                parent_reverted = True
                break
            curr_parent = parent_op.parent_id if parent_op else None

        if parent_reverted:
            continue

        timeline = apply_operation(timeline, op)

    max_end = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            end = clip.position_sec + (clip.out_point_sec - clip.in_point_sec)
            if end > max_end:
                max_end = end
    for overlay in timeline.overlays:
        end = overlay.position_sec + overlay.duration_sec
        if end > max_end:
            max_end = end
    timeline.duration_sec = max_end
    return timeline
