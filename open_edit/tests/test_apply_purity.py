from copy import deepcopy
from open_edit.ir.types import Timeline, Track, Clip, AddClipOp
from open_edit.ir.apply import apply_operation

def test_apply_operation_does_not_mutate_input():
    base = Timeline(tracks=[])
    original = deepcopy(base)

    op = AddClipOp(
        edit_id="e1",
        author="ai",
        timestamp="2026-01-01T00:00:00",
        asset_hash="abc123",
        track_id="t1",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=10.0,
    )

    result = apply_operation(base, op)
    assert base == original, "apply_operation mutated the input timeline"
