# open_edit/tests/test_ir_validation.py
import pytest

from open_edit.ir.types import Timeline, Track, Clip
from open_edit.ir.validate import validate_timeline


def _clip(clip_id, start, in_p, out_p):
    return Clip(
        clip_id=clip_id, asset_hash="h", track_id="V1", track_kind="video",
        position_sec=start, in_point_sec=in_p, out_point_sec=out_p,
    )


def test_validate_timeline_detects_overlap():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 0.0, 5.0),
        _clip("b", 4.0, 0.0, 5.0),  # starts at 4.0 < a's end 5.0 -> overlap
    ])])
    errs = validate_timeline(tl)
    assert any("Overlap" in e for e in errs), errs


def test_validate_timeline_detects_nonpositive_duration():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 5.0, 5.0),  # out == in -> zero duration
    ])])
    errs = validate_timeline(tl)
    assert any("duration" in e.lower() for e in errs), errs


def test_validate_timeline_clean():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 0.0, 5.0),
        _clip("b", 5.0, 0.0, 5.0),  # abuts exactly, no overlap
    ])])
    assert validate_timeline(tl) == []


from open_edit.ir.apply import derive_timeline, TimelineValidationError
from open_edit.ir.types import Project


def _overlapping_project():
    # A project whose derived timeline has two overlapping clips on V1.
    from open_edit.ir.types import AddClipOp
    ops = [
        AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0,
                  in_point_sec=0.0, out_point_sec=5.0, author="ai"),
        AddClipOp(asset_hash="h", track_id="V1", position_sec=4.0,
                  in_point_sec=0.0, out_point_sec=5.0, author="ai"),
    ]
    return Project(project_id="p", name="p", workdir="/tmp", assets={}, edit_graph=ops)


def test_derive_timeline_strict_raises_on_overlap():
    with pytest.raises(TimelineValidationError):
        derive_timeline(_overlapping_project(), strict=True)


def test_derive_timeline_lenient_loads_overlap():
    # Default stays lenient so legacy projects still load.
    tl = derive_timeline(_overlapping_project(), strict=False)
    assert any(len(t.clips) == 2 for t in tl.tracks)
