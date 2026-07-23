# open_edit/tests/test_ir_validation.py
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
