"""Pure timeline controls with stable clip, track and effect identities."""
from __future__ import annotations

import math

from open_edit.ir.apply_common import ApplyError, _find_clip, _get_or_create_track
from open_edit.ir.types import (
    ControlEffectOp,
    DuplicateClipOp,
    RemoveTrackOp,
    SetClipPropertiesOp,
    SetTrackPropertiesOp,
    Timeline,
)

STUDIO_OPERATIONS = (DuplicateClipOp, SetTrackPropertiesOp, RemoveTrackOp, SetClipPropertiesOp, ControlEffectOp)


def effect_ids(timeline):
    return {e.effect_id for t in timeline.tracks for e in
            [*t.effects, *[e for c in t.clips for e in c.effects]]}


def references(op, timeline: Timeline) -> list[str]:
    tracks = {t.track_id: t for t in timeline.tracks}
    clips = {c.clip_id: c for t in timeline.tracks for c in t.clips}
    if isinstance(op, SetTrackPropertiesOp):
        track = tracks.get(op.track_id)
        if not track and not op.track_kind:
            return ['Creating a track requires video or audio track_kind']
        if track and op.track_kind and track.kind != op.track_kind:
            return ['A track must retain its media kind']
        if op.index is not None and op.index >= len(tracks) + (not track):
            return ['Track index is out of range']
    elif isinstance(op, RemoveTrackOp):
        if op.track_id not in tracks:
            return ['Track does not exist']
        if tracks[op.track_id].clips or tracks[op.track_id].effects:
            return ['Move or delete the clips and effects before removing a track']
    elif isinstance(op, (SetClipPropertiesOp, DuplicateClipOp)):
        if op.clip_id not in clips:
            return ['Clip does not exist']
        if isinstance(op, DuplicateClipOp):
            original = clips[op.clip_id]
            if not op.new_clip_id or op.new_clip_id in clips:
                return ['A duplicate needs a new stable clip ID']
            if op.new_track_id in tracks and tracks[op.new_track_id].kind != original.track_kind:
                return ['Use a compatible track for the duplicated clip']
            ids = effect_ids(timeline)
            if (set(op.effect_ids) != {e.effect_id for e in original.effects} or
                    len(set(op.effect_ids.values())) != len(op.effect_ids) or
                    any(not value or value in ids for value in op.effect_ids.values())):
                return ['A duplicate needs a new stable ID for each copied effect']
    elif isinstance(op, ControlEffectOp):
        target = (clips if op.target_kind == 'clip' else tracks).get(op.target_id)
        if target is None:
            return ['Effect owner does not exist']
        effect = next((e for e in target.effects if e.effect_id == op.effect_id), None)
        if not effect:
            return ['Effect does not exist on this owner']
        if op.action == 'duplicate':
            all_ids = effect_ids(timeline)
            if not op.new_effect_id or op.new_effect_id in all_ids:
                return ['A duplicate needs a new stable effect ID']
        if effect.effect_type.startswith('transition_'):
            return ['Use the transition controls to change or remove this transition']
        if op.action == 'move' and (op.index is None or op.index >= len(target.effects)):
            return ['Effect index is out of range']
        if op.action not in ('update', 'reset') and (op.params or op.enabled is not None):
            return ['This effect action does not change parameters or bypass']
        if op.action == 'reset' and op.params:
            return ['Reset restores the catalog defaults; use update to set parameters']
        if op.action in ('update', 'reset'):
            from open_edit.ir.validate import _get_default_catalog

            spec = _get_default_catalog().get(effect.effect_type)
            if op.params and spec is None:
                return ['This advanced effect has no supported parameter schema']
            for name, value in op.params.items():
                param = spec.params.get(name) if spec else None
                if param is None:
                    return [f'Unknown effect parameter {name}']
                if param.type in ('float', 'int'):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        return [f'{name} must be finite']
                    if param.type == 'int' and not isinstance(value, int):
                        return [f'{name} must be an integer']
                    if param.range and not param.range[0] <= value <= param.range[1]:
                        return [f'{name} must be within {param.range}']
                elif param.type == 'bool' and type(value) is not bool:
                    return [f'{name} must be boolean']
                elif param.type == 'str' and (not isinstance(value, str) or len(value) > 10000):
                    return [f'{name} must be a bounded string']
    return []


def apply(timeline: Timeline, op) -> Timeline:
    errors = references(op, timeline)
    if errors:
        raise ApplyError('; '.join(errors))
    if isinstance(op, SetTrackPropertiesOp):
        track = next((t for t in timeline.tracks if t.track_id == op.track_id), None)
        if track is None:
            track = _get_or_create_track(timeline, op.track_id, op.track_kind)
        for field in ('label', 'locked', 'muted', 'hidden', 'solo'):
            if getattr(op, field) is not None:
                setattr(track, field, getattr(op, field))
        if op.index is not None:
            timeline.tracks.remove(track)
            timeline.tracks.insert(op.index, track)
    elif isinstance(op, RemoveTrackOp):
        timeline.tracks = [t for t in timeline.tracks if t.track_id != op.track_id]
    elif isinstance(op, SetClipPropertiesOp):
        _, clip, _ = _find_clip(timeline, op.clip_id)
        for field in ('label', 'locked', 'muted', 'hidden'):
            if getattr(op, field) is not None:
                setattr(clip, field, getattr(op, field))
    elif isinstance(op, DuplicateClipOp):
        _, original, _ = _find_clip(timeline, op.clip_id)
        track = _get_or_create_track(timeline, op.new_track_id or original.track_id, original.track_kind)
        copy = original.model_copy(deep=True, update={'clip_id': op.new_clip_id, 'track_id': track.track_id,
                                                    'position_sec': op.position_sec, 'locked': False})
        for effect in copy.effects:
            effect.effect_id = op.effect_ids[effect.effect_id]
        track.clips.append(copy)
    elif isinstance(op, ControlEffectOp):
        target = (_find_clip(timeline, op.target_id)[1] if op.target_kind == 'clip'
                  else next(t for t in timeline.tracks if t.track_id == op.target_id))
        i = next(i for i, e in enumerate(target.effects) if e.effect_id == op.effect_id)
        effect = target.effects[i]
        if op.action == 'remove':
            target.effects.pop(i)
        elif op.action == 'move':
            target.effects.pop(i)
            target.effects.insert(op.index, effect)
        elif op.action == 'duplicate':
            target.effects.insert(i + 1, effect.model_copy(deep=True, update={'effect_id': op.new_effect_id}))
        else:
            effect.params = dict(op.params) if op.action == 'reset' else {**effect.params, **op.params}
            if op.action == 'reset':
                from open_edit.ir.validate import _get_default_catalog

                spec = _get_default_catalog().get(effect.effect_type)
                effect.params = {name: p.default for name, p in spec.params.items() if p.default is not None} if spec else {}
                effect.keyframes = {}
                effect.enabled = True
            if op.enabled is not None:
                effect.enabled = op.enabled
    return timeline
