"""SFX placer skill: place sound effects at narrative beat transitions.

Per phase4-design-revised.md section 4.5 (W6).
"""
from __future__ import annotations

from pydantic import BaseModel

from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.ir.types import AddEffectOp


class SfxClip(BaseModel):
    sfx_id: str
    kind: str  # "whoosh" | "impact" | "riser" | "pop" | "ding" | etc.
    duration_s: float


# Beat transition → SFX kind mapping
TRANSITION_SFX_MAP = {
    ("hook", "turn"): "whoosh",
    ("turn", "scope"): "riser",
    ("scope", "mechanism"): "impact",
    ("mechanism", "cost"): "impact",
    ("cost", "tease"): "riser",
    ("tease", "button"): "impact",
}


def place(segments: list[NarrativeSegment], music_downbeats: list[float], library: list[SfxClip]) -> list[AddEffectOp]:
    """Place duration-fit SFX at transitions, aligned to music when possible."""
    ops = []
    for prev, curr in zip(segments, segments[1:]):
        kind = TRANSITION_SFX_MAP.get((prev.beat_type, curr.beat_type), "impact")
        candidates = [s for s in library if s.kind == kind]
        if not candidates:
            candidates = library
        if not candidates:
            continue
        gap_s = max(0.0, curr.t_start - prev.t_end)
        chosen = min(
            candidates,
            key=lambda s: (
                abs(s.duration_s - gap_s) if gap_s else s.duration_s,
                s.sfx_id,
            ),
        )
        start_s = curr.t_start
        if music_downbeats:
            # Snap only to nearby, non-negative downbeats; a nearby beat may
            # precede the transition, but never becomes negative or distant.
            max_snap_s = 0.5
            candidates_beats = [
                b for b in music_downbeats
                if isinstance(b, (int, float)) and b >= 0.0
            ]
            if candidates_beats:
                nearest = min(candidates_beats, key=lambda beat: abs(beat - curr.t_start))
                if abs(nearest - curr.t_start) <= max_snap_s:
                    start_s = float(nearest)
        ops.append(AddEffectOp(
            author="ai",
            target_kind="track",
            target_id="audio_sfx",
            effect_type="sfx",
            params={
                "sfx_id": chosen.sfx_id,
                "t_start": start_s,
                "duration_s": chosen.duration_s,
                "gain_db": 0.0,
            },
        ))
    return ops
