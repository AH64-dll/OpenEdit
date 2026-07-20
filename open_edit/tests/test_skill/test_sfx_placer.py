"""Phase 4.5 W6: SFX placer skill."""
from pathlib import Path

import pytest
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.agent.skills.sfx_placer import place, SfxClip
from open_edit.ir.catalog.loader import EffectCatalog
from open_edit.ir.types import Project
from open_edit.ir.validate import validate_op


def test_place_at_beat_transitions():
    segments = [
        NarrativeSegment(beat_type="hook", t_start=0.0, t_end=3.0, text="Welcome"),
        NarrativeSegment(beat_type="turn", t_start=3.0, t_end=7.0, text="But..."),
    ]
    library = [
        SfxClip(sfx_id="whoosh_01", kind="whoosh", duration_s=0.5),
        SfxClip(sfx_id="impact_01", kind="impact", duration_s=0.3),
    ]
    ops = place(segments, music_downbeats=[], library=library)
    # Two segments → exactly one transition (hook→turn)
    assert len(ops) == 1
    # The hook→turn transition maps to kind="whoosh" (TRANSITION_SFX_MAP);
    # a broken implementation that always returns the first library item
    # would pick impact_01 (t_start=3.0 happens to match, so a t_start-only
    # assertion would silently pass).
    assert ops[0].params.get("sfx_id") == "whoosh_01"
    assert ops[0].params.get("t_start") == 3.0
    assert ops[0].params.get("duration_s") == 0.5


def test_sfx_clip_pydantic():
    s = SfxClip(sfx_id="x", kind="whoosh", duration_s=0.5)
    assert s.kind == "whoosh"


def test_sfx_in_catalog_and_validates():
    """Regression: sfx must be in the effect catalog and the ops the sfx
    placer emits must pass validate_op. Without a catalog entry, validate_op
    rejects effect_type='sfx' (validate.py:142-148).
    """
    bundled_catalog = Path(__file__).parent.parent.parent / "open_edit" / "ir" / "catalog"
    catalog = EffectCatalog(bundled_catalog)
    assert catalog.is_known("sfx"), (
        "sfx missing from bundled catalog; "
        f"known: {sorted(catalog.known_names())}"
    )

    # Feed place()'s actual output through validate_op rather than constructing
    # an op by hand — this closes the loop between the placer and the catalog
    # (catches drift if place() ever starts emitting params the catalog doesn't
    # know about, while still verifying the kind-selection logic above).
    segments = [
        NarrativeSegment(beat_type="hook", t_start=0.0, t_end=3.0, text="Welcome"),
        NarrativeSegment(beat_type="turn", t_start=3.0, t_end=7.0, text="But..."),
    ]
    library = [
        SfxClip(sfx_id="whoosh_01", kind="whoosh", duration_s=0.5),
        SfxClip(sfx_id="impact_01", kind="impact", duration_s=0.3),
    ]
    ops = place(segments, music_downbeats=[], library=library)
    project = Project(name="t")
    for op in ops:
        errors = validate_op(op, project, catalog=catalog)
        assert errors == [], f"sfx op should validate cleanly; got: {errors}"
