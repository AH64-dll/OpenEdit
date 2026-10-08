"""Non-destructive, centered visual transitions with explicit source windows."""
from __future__ import annotations

import math

from open_edit.ir.types import Timeline, VisualTransition


def resolve_transitions(timeline: Timeline) -> list[VisualTransition]:
    result = []
    for index, track in enumerate(timeline.tracks):
        clips = {c.clip_id: c for c in track.clips}
        for a in track.clips:
            for effect in a.effects:
                if effect.params.get('layout') != 'centered':
                    continue
                b = clips.get(effect.params.get('clip_b_id'))
                if b is None:
                    continue  # deleting a clip leaves a removable source entry
                duration = float(effect.params['duration_sec'])
                end = a.position_sec + a.out_point_sec - a.in_point_sec
                if (not math.isfinite(duration) or duration <= 0 or duration > min(
                    a.out_point_sec - a.in_point_sec, b.out_point_sec - b.in_point_sec) or
                        abs(end - b.position_sec) > 1e-6):
                    raise ValueError('Remove or resize the transition before changing its cut or clip duration')
                if not effect.enabled or track.hidden or a.hidden or b.hidden or effect.effect_type == 'transition_cut':
                    continue
                result.append(VisualTransition(transition_id=effect.effect_id, kind=effect.effect_type.removeprefix('transition_'),
                    clip_a=a.model_copy(deep=True), clip_b=b.model_copy(deep=True), track_effects=track.effects,
                    z_index=index, duration_sec=duration, position_sec=end-duration/2, visible_duration_sec=duration))
    return result
