"""Apply operations to derive Timeline state. Pure functions.

``apply_operation`` is the dispatch: a single isinstance tree over the
operation union that delegates each operation family to a sibling module
(:mod:`open_edit.ir.apply_clips`, :mod:`open_edit.ir.apply_effects`,
:mod:`open_edit.ir.apply_audio`) or handles structural ops inline.

Timeline derivation lives in :mod:`open_edit.ir.derive`; the snapshot
cache policy in :mod:`open_edit.storage.timeline_cache`.
"""
from __future__ import annotations

from open_edit.ir.apply_audio import _apply_normalize_audio, _apply_set_audio_gain
from open_edit.ir.apply_clips import (
    _apply_change_clip_speed,
    _apply_replace_clip_source,
    _apply_ripple_delete_clip,
    _apply_set_clip_speed_ramp,
    _apply_slip_clip,
    _apply_split_clip,
)
from open_edit.ir.apply_common import (
    ApplyError,
    _find_clip,
    _get_or_create_track,
    _make_clip,
)
from open_edit.ir.apply_effects import (
    _apply_add_effect,
    _apply_add_transition,
    _apply_remove_effect,
    _apply_remove_keyframe,
    _apply_remove_transition,
    _apply_set_effect_param,
    _apply_set_keyframe,
    _apply_set_transition_property,
)
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddHtmlOverlayOp,
    AddRemotionCompositionOp,
    AddTransitionOp,
    ChangeClipSpeedOp,
    Clip,
    FreeFormCodeOp,
    GroupEditsOp,
    HtmlOverlay,
    MoveClipOp,
    NormalizeAudioOp,
    OperationUnion,
    RawMltXmlOp,
    RemotionComposition,
    RemoveClipOp,
    RemoveEffectOp,
    RemoveGraphicsSourceOp,
    RemoveHtmlOverlayOp,
    RemoveKeyframeOp,
    RemoveRemotionCompositionOp,
    RemoveTransitionOp,
    ReplaceClipSourceOp,
    RippleDeleteClipOp,
    SetAudioGainOp,
    SetClipSpeedRampOp,
    SetEffectParamOp,
    SetGraphicsSourceOp,
    SetKeyframeOp,
    SetTransitionPropertyOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
    TrimClipOp,
    UngroupEditsOp,
)


def apply_operation(
    timeline: Timeline, op: OperationUnion, strict: bool = False,
) -> Timeline:
    """Apply a single operation to a timeline. Returns a new timeline.

    Pure function. Does not mutate the input.

    ``strict=False`` (default) keeps the historical behavior of silently
    no-oping on unknown references; this is what ``derive_timeline`` needs
    to remain idempotent on a graph where some ops may have been superseded
    or never actually took effect. ``strict=True`` makes the helpers raise
    :class:`ApplyError` on unknown references, so direct callers (e.g. an
    agent that just appended an op) get immediate feedback instead of a
    silently-wrong timeline.
    """
    timeline = timeline.model_copy(deep=True)
    if op.status != "applied":
        return timeline

    if isinstance(op, SetGraphicsSourceOp):
        old = timeline.graphics_documents.get(op.document_id)
        timeline.graphics_documents[op.document_id] = {
            'source': op.source, 'duration_sec': op.duration_sec, 'fps': op.fps,
            'enabled': op.enabled, 'label': op.label, 'clip_id': op.clip_id,
        }
        _, original, _ = _find_clip(timeline, op.clip_id)
        if original is not None and (original.document_id not in (None, op.document_id) or
                                     (original.document_id is None and not op.adopt_clip)):
            raise ApplyError('Graphics document would replace a different clip')
        instances = [(track, clip, index) for track in timeline.tracks for index, clip in enumerate(track.clips)
                     if clip.document_id == op.document_id or (clip is original and op.adopt_clip)]
        for track, clip, index in instances:
            full = clip.in_point_sec == 0 and old is not None and abs(clip.out_point_sec - old['duration_sec']) < 1e-6
            if not full and clip.out_point_sec > op.duration_sec + 1e-6:
                raise ApplyError('Graphics source is shorter than its explicit clip trim')
            track.clips[index] = clip.model_copy(update={
                'document_id': op.document_id, 'asset_hash': f'studio:{op.document_id}',
                'out_point_sec': op.duration_sec if full else clip.out_point_sec,
            })
        if not instances and old is None:
            track = _get_or_create_track(timeline, op.track_id, 'video')
            track.clips.append(Clip(clip_id=op.clip_id, document_id=op.document_id,
                                    asset_hash=f'studio:{op.document_id}', track_id=op.track_id,
                                    track_kind='video', position_sec=op.position_sec,
                                    in_point_sec=0, out_point_sec=op.duration_sec))
        return timeline
    if isinstance(op, RemoveGraphicsSourceOp):
        timeline.graphics_documents.pop(op.document_id, None)
        for track in timeline.tracks:
            track.clips = [clip for clip in track.clips if clip.document_id != op.document_id]
        return timeline

    if isinstance(op, AddClipOp):
        track = _get_or_create_track(timeline, op.track_id, op.track_kind)
        out_val = op.out_point_sec if op.out_point_sec is not None else 0.0
        track.clips.append(_make_clip(op, out_val))
        return timeline
    if isinstance(op, RemoveClipOp):
        # RemoveClipOp is a no-op for unknown clip_ids by design (matches
        # ``validate_op`` which deliberately lets the reference pass). Strict
        # mode also leaves it alone — callers should validate the project
        # graph separately if they need rejection of unknown clip_ids.
        for track in timeline.tracks:
            track.clips = [c for c in track.clips if c.clip_id != op.clip_id]
        return timeline
    if isinstance(op, MoveClipOp):
        track, clip, i = _find_clip(timeline, op.clip_id)
        if clip is None:
            if strict:
                raise ApplyError(
                    f"MoveClipOp: clip_id '{op.clip_id}' not found in timeline"
                )
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
            if strict:
                raise ApplyError(
                    f"TrimClipOp: clip_id '{op.clip_id}' not found in timeline"
                )
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
        return _apply_add_transition(timeline, op, strict=strict)
    if isinstance(op, RemoveTransitionOp):
        return _apply_remove_transition(timeline, op)
    if isinstance(op, SetTransitionPropertyOp):
        return _apply_set_transition_property(timeline, op)
    if isinstance(op, AddEffectOp):
        return _apply_add_effect(timeline, op, strict=strict)
    if isinstance(op, RemoveEffectOp):
        return _apply_remove_effect(timeline, op, strict=strict)
    if isinstance(op, SetEffectParamOp):
        return _apply_set_effect_param(timeline, op, strict=strict)
    if isinstance(op, SetKeyframeOp):
        return _apply_set_keyframe(timeline, op, strict=strict)
    if isinstance(op, RemoveKeyframeOp):
        return _apply_remove_keyframe(timeline, op, strict=strict)
    if isinstance(op, SlipClipOp):
        return _apply_slip_clip(timeline, op, strict=strict)
    if isinstance(op, RippleDeleteClipOp):
        return _apply_ripple_delete_clip(timeline, op, strict=strict)
    if isinstance(op, ChangeClipSpeedOp):
        return _apply_change_clip_speed(timeline, op, strict=strict)
    if isinstance(op, SplitClipOp):
        return _apply_split_clip(timeline, op, strict=strict)
    if isinstance(op, ReplaceClipSourceOp):
        return _apply_replace_clip_source(timeline, op, strict=strict)
    if isinstance(op, SetClipSpeedRampOp):
        return _apply_set_clip_speed_ramp(timeline, op, strict=strict)
    if isinstance(op, SetAudioGainOp):
        return _apply_set_audio_gain(timeline, op, strict=strict)
    if isinstance(op, NormalizeAudioOp):
        return _apply_normalize_audio(timeline, op, strict=strict)
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
    if isinstance(op, AddRemotionCompositionOp):
        if op.duration_sec <= 0:
            raise ApplyError(
                f"add_remotion_composition duration_sec must be > 0; got {op.duration_sec}"
            )
        composition = RemotionComposition(
            composition_uid=op.composition_uid,
            entry_point=op.entry_point,
            composition_id=op.composition_id,
            props=op.props,
            position_sec=op.position_sec,
            duration_sec=op.duration_sec,
            track_id=op.track_id,
            alpha=op.alpha,
            clip_id=op.clip_id,
        )
        timeline.remotion_compositions.append(composition)
        timeline.remotion_compositions.sort(key=lambda c: c.position_sec)
        return timeline
    if isinstance(op, RemoveRemotionCompositionOp):
        timeline.remotion_compositions = [
            c for c in timeline.remotion_compositions
            if c.composition_uid != op.composition_uid
        ]
        return timeline
    return timeline
