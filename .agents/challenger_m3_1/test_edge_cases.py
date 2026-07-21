"""Detailed edge-case analysis script for apply.py."""
import sys
import traceback

sys.path.insert(0, "/home/ah64/apps/mlt-pipeline/open_edit")

from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    ChangeClipSpeedOp,
    MoveClipOp,
    Project,
    RemoveClipOp,
    RemoveEffectOp,
    RemoveKeyframeOp,
    RemoveTransitionOp,
    RippleDeleteClipOp,
    SetEffectParamOp,
    SetKeyframeOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
    TrimClipOp,
)


def run_edge_case_tests():
    print("=== RUNNING EDGE CASE INVESTIGATIONS ===")

    # Edge Case 1: Inverted Trim (in > out)
    t = Timeline()
    op_add = AddClipOp(author="user", asset_hash="a1", track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0)
    t = apply_operation(t, op_add)
    op_inv_trim = TrimClipOp(author="user", clip_id=op_add.clip_id, new_in_point_sec=15.0, new_out_point_sec=5.0)
    t_inv_trim = apply_operation(t, op_inv_trim)
    clip = t_inv_trim.tracks[0].clips[0]
    print(f"Edge Case 1 - Inverted Trim: in={clip.in_point_sec}, out={clip.out_point_sec}")
    print(f"  Duration contribution: {clip.out_point_sec - clip.in_point_sec}")

    # Edge Case 2: Slip clip producing negative in_point_sec
    t = Timeline()
    op_add = AddClipOp(author="user", asset_hash="a1", track_id="v1", position_sec=0.0, in_point_sec=1.0, out_point_sec=5.0)
    t = apply_operation(t, op_add)
    op_slip = SlipClipOp(author="user", clip_id=op_add.clip_id, delta_sec=-10.0)
    t_slip = apply_operation(t, op_slip)
    clip_slip = t_slip.tracks[0].clips[0]
    print(f"Edge Case 2 - Slip into negative asset time: in={clip_slip.in_point_sec}, out={clip_slip.out_point_sec}")

    # Edge Case 3: Move clip on same track (order perturbation)
    t = Timeline()
    op_a = AddClipOp(author="user", clip_id="c1", asset_hash="a1", track_id="v1", position_sec=0.0, out_point_sec=5.0)
    op_b = AddClipOp(author="user", clip_id="c2", asset_hash="a2", track_id="v1", position_sec=10.0, out_point_sec=15.0)
    t = apply_operation(t, op_a)
    t = apply_operation(t, op_b)
    # Move c1 to same track at new position
    op_move_c1 = MoveClipOp(author="user", clip_id="c1", new_track_id="v1", new_position_sec=20.0)
    t_moved = apply_operation(t, op_move_c1)
    clip_ids = [c.clip_id for c in t_moved.tracks[0].clips]
    print(f"Edge Case 3 - Move clip on same track clip list order: {clip_ids}")

    # Edge Case 4: Move clip across track kinds (audio vs video)
    t = Timeline()
    op_a = AddClipOp(author="user", clip_id="c1", asset_hash="a1", track_id="v1", track_kind="video", position_sec=0.0, out_point_sec=5.0)
    t = apply_operation(t, op_a)
    op_move_cross = MoveClipOp(author="user", clip_id="c1", new_track_id="a1", new_position_sec=0.0)
    t_cross = apply_operation(t, op_move_cross)
    for tr in t_cross.tracks:
        print(f"Edge Case 4 - Track {tr.track_id} kind={tr.kind}, clips={[c.clip_id + ' (track_kind=' + c.track_kind + ')' for c in tr.clips]}")

    # Edge Case 5: Change speed rate = 0 or negative
    t = Timeline()
    op_a = AddClipOp(author="user", clip_id="c1", asset_hash="a1", track_id="v1", position_sec=0.0, out_point_sec=5.0)
    t = apply_operation(t, op_a)
    op_speed0 = ChangeClipSpeedOp(author="user", clip_id="c1", rate=0.0)
    t_speed0 = apply_operation(t, op_speed0)
    print(f"Edge Case 5 - Speed 0 effect params: {t_speed0.tracks[0].clips[0].effects[0].params}")


if __name__ == "__main__":
    run_edge_case_tests()
