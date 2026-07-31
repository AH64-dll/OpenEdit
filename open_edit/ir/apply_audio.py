"""Audio operations: gain and normalize. Pure functions."""
from __future__ import annotations

from open_edit.ir.apply_common import ApplyError, _find_clip
from open_edit.ir.types import Effect, NormalizeAudioOp, SetAudioGainOp, Timeline


def _apply_normalize_audio(
    timeline: Timeline, op: NormalizeAudioOp, strict: bool = False,
) -> Timeline:
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
            if strict:
                raise ApplyError(
                    f"NormalizeAudioOp: clip target_id '{op.target_id}' not found in timeline"
                )
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
        if strict:
            raise ApplyError(
                f"NormalizeAudioOp: track target_id '{op.target_id}' not found in timeline"
            )
        return timeline
    return timeline


def _apply_set_audio_gain(
    timeline: Timeline, op: SetAudioGainOp, strict: bool = False,
) -> Timeline:
    track, clip, i = _find_clip(timeline, op.clip_id)
    if clip is None:
        if strict:
            raise ApplyError(
                f"SetAudioGainOp: clip_id '{op.clip_id}' not found in timeline"
            )
        return timeline
    linear_gain = 10 ** (op.gain_db / 20.0)
    new_effect = Effect(
        effect_id=op.edit_id, effect_type="volume",
        params={"gain": linear_gain},
    )
    new_clip = clip.model_copy(update={"effects": [*clip.effects, new_effect]})
    track.clips[i] = new_clip
    return timeline
