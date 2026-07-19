"""Tests for phase2_project_engine.ops.clips_edit — set_clip_speed_ramp.

Uses the real testdata clip (CLIP_SHORT); skips if missing. The clip id
is captured from insert_clip's return value (never hardcoded).
"""
from __future__ import annotations

import pytest

from phase2_project_engine.tests.ops_fixtures import make_minimal_tree, CLIP_SHORT


def _import_source(tree, source):
    from phase2_project_engine.ops.bin import import_media
    return import_media(tree, [str(source)])[0]


def _insert_clip(tree, source, src_id):
    from phase2_project_engine.ops.clips import insert_clip
    return insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src_id,
        source_in_sec=0.0, source_out_sec=3.0,
    )


def test_set_clip_speed_ramp_basic():
    """A 3-keyframe ramp 0→1s @1x, 1→2s @2x, 2→3s @1x writes a timeremap link."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips_edit import set_clip_speed_ramp
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    result = set_clip_speed_ramp(tree, kid, [
        {"time_ms": 0, "rate": 1.0},
        {"time_ms": 1000, "rate": 2.0},
        {"time_ms": 2000, "rate": 1.0},
    ])
    assert result["keyframes_added"] == 3
    assert result["min_rate"] == 1.0
    assert result["max_rate"] == 2.0


def test_set_clip_speed_ramp_time_monotonic_violation():
    from phase2_project_engine.errors import ValidationError
    from phase2_project_engine.ops.clips_edit import set_clip_speed_ramp
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    with pytest.raises(ValidationError, match="time_monotonic_violation"):
        set_clip_speed_ramp(tree, kid, [
            {"time_ms": 0, "rate": 1.0},
            {"time_ms": 1000, "rate": 2.0},
            {"time_ms": 1000, "rate": 1.0},  # duplicate time
        ])
