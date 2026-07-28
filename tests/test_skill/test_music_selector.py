"""Phase 4.5 W5: music selector skill."""
from pathlib import Path

import pytest
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.agent.skills.music_selector import select, MusicTrack
from open_edit.ir.catalog.loader import EffectCatalog
from open_edit.ir.types import AddEffectOp, Project
from open_edit.ir.validate import validate_op


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
    # Tightened: verify per-segment mood matching, not just non-empty.
    # hook -> upbeat, mechanism -> contemplative.
    assert len(ops) == 2
    assert ops[0].params["track_id"] == "upbeat_01"
    assert ops[1].params["track_id"] == "contemplative_01"


def test_music_track_pydantic():
    t = MusicTrack(track_id="x", mood="upbeat", bpm=120, energy=0.8)
    assert t.mood == "upbeat"


def test_music_bed_in_catalog_and_validates():
    """Regression: music_bed must be in the effect catalog and the ops
    the music selector emits must pass validate_op. Without a catalog
    entry, validate_op rejects effect_type='music_bed' (validate.py:142-148).
    """
    bundled_catalog = Path(__file__).parent.parent.parent / "open_edit" / "ir" / "catalog"
    catalog = EffectCatalog(bundled_catalog)
    assert catalog.is_known("music_bed"), (
        "music_bed missing from bundled catalog; "
        f"known: {sorted(catalog.known_names())}"
    )

    project = Project(name="t")
    op = AddEffectOp(
        author="ai",
        target_kind="track",
        target_id="audio_music",
        effect_type="music_bed",
        params={"track_id": "upbeat_01", "gain_db": -12.0, "t_start": 0.0, "t_end": 3.0},
    )
    errors = validate_op(op, project, catalog=catalog)
    assert errors == [], f"music_bed op should validate cleanly; got: {errors}"
