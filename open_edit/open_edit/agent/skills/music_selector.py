"""Music selector skill: pick mood-matched tracks for narrative segments.

Per phase4-design-revised.md section 4.4 (W5).
"""
from __future__ import annotations

from pydantic import BaseModel

from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.ir.types import AddEffectOp


class MusicTrack(BaseModel):
    track_id: str
    mood: str  # "upbeat" | "contemplative" | "dramatic" | "corporate" | etc.
    bpm: int
    energy: float  # 0.0 - 1.0


# Per-beat mood mapping
BEAT_MOOD_MAP = {
    "hook": "upbeat",
    "turn": "dramatic",
    "scope": "contemplative",
    "mechanism": "contemplative",
    "cost": "dramatic",
    "tease": "upbeat",
    "button": "upbeat",
}


def select(segments: list[NarrativeSegment], library: list[MusicTrack]) -> list[AddEffectOp]:
    """Pick a music track per segment based on beat mood."""
    ops = []
    for seg in segments:
        target_mood = BEAT_MOOD_MAP.get(seg.beat_type, "contemplative")
        candidates = [t for t in library if t.mood == target_mood]
        if not candidates:
            candidates = library
        if not candidates:
            continue
        chosen = candidates[0]
        ops.append(AddEffectOp(
            author="ai",
            target_kind="track",
            target_id="audio_music",
            effect_type="music_bed",
            params={
                "track_id": chosen.track_id,
                "gain_db": -12.0,
                "t_start": seg.t_start,
                "t_end": seg.t_end,
            },
        ))
    return ops
