"""Phase 4.5 W6: SFX placer skill."""
from pathlib import Path

import pytest
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.agent.skills.sfx_placer import place, SfxClip
from open_edit.ir.catalog.loader import EffectCatalog
from open_edit.ir.types import AddEffectOp, Project
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
    # At least one SFX at the hook→turn transition (3.0s)
    assert any(op.params.get("t_start") == 3.0 for op in ops)


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

    project = Project(name="t")
    op = AddEffectOp(
        author="ai",
        target_kind="track",
        target_id="audio_sfx",
        effect_type="sfx",
        params={"sfx_id": "whoosh_01", "t_start": 3.0, "duration_s": 0.5, "gain_db": 0.0},
    )
    errors = validate_op(op, project, catalog=catalog)
    assert errors == [], f"sfx op should validate cleanly; got: {errors}"
