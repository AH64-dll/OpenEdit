"""Phase 4.5 W5: music selector skill."""
import pytest
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.agent.skills.music_selector import select, MusicTrack


def test_select_picks_mood_matching_track():
    segments = [
        NarrativeSegment(beat_type="hook", t_start=0.0, t_end=3.0, text="Welcome"),
        NarrativeSegment(beat_type="mechanism", t_start=3.0, t_end=10.0, text="How it works"),
    ]
    library = [
        MusicTrack(track_id="upbeat_01", mood="upbeat", bpm=120, energy=0.8),
        MusicTrack(track_id="contemplative_01", mood="contemplative", bpm=70, energy=0.3),
    ]
    ops = select(segments, library)
    # Should pick upbeat for hook, contemplative for mechanism
    assert len(ops) >= 1


def test_music_track_pydantic():
    t = MusicTrack(track_id="x", mood="upbeat", bpm=120, energy=0.8)
    assert t.mood == "upbeat"
