"""Tests for apply.py — including the Bug A transition centering fix."""
import pytest

from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    Effect,
    Project,
    RemoveClipOp,
    SetKeyframeOp,
    Timeline,
    MoveClipOp,
    TrimClipOp,
)


# ===== AddClipOp =====

def test_add_clip_creates_track() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="abc", track_id="v1", position_sec=0.0)
    out = apply_operation(timeline, op)
    assert len(out.tracks) == 1
    assert out.tracks[0].track_id == "v1"
    assert len(out.tracks[0].clips) == 1
    assert out.tracks[0].clips[0].asset_hash == "abc"


def test_add_clip_uses_position_sec() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="v1", position_sec=12.5,
    )
    out = apply_operation(timeline, op)
    assert out.tracks[0].clips[0].position_sec == 12.5


def test_add_audio_clip_is_first_class() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="narr",
        track_id="audio_1", track_kind="audio", position_sec=0.0,
    )
    out = apply_operation(timeline, op)
    assert out.tracks[0].kind == "audio"
    assert out.tracks[0].clips[0].track_kind == "audio"


# ===== Bug A: transition centering =====

def test_add_transition_centers_on_cut_not_midpoint() -> None:
    """Bug A regression: transition is placed at clip_a.out_point_sec (the cut),
    not at the midpoint of the two clips' positions.

    Setup: clip_a at [0, 10), clip_b at [10, 20), transition of 2.0s.
    Expected cut = 10.0 (which is clip_a.out_point_sec).
    clip_a.out is back-solved to: cut - duration/2 = 10 - 1 = 9
    clip_b.in is back-solved to: cut + duration/2 = 10 + 1 = 11
    So clip_a now spans [0, 9), clip_b spans [11, 20).
    """
    timeline = Timeline()
    op_a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    op_b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    timeline = apply_operation(timeline, op_a)
    timeline = apply_operation(timeline, op_b)

    op_t = AddTransitionOp(
        author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
        transition_type="luma", duration_sec=2.0,
    )
    out = apply_operation(timeline, op_t)
    clips = out.tracks[0].clips
    # Bug A: clip_a's out_point_sec is back-solved to cut - half
    # clip_b's in_point_sec is back-solved so its asset plays from cut+half
    # The transition is centered on the cut, NOT on the midpoint of clip positions
    # in_point_sec / out_point_sec are asset offsets, not timeline positions
    assert clips[0].out_point_sec == pytest.approx(9.0, abs=0.001)
    assert clips[1].in_point_sec == pytest.approx(1.0, abs=0.001)


def test_add_transition_rejects_duration_larger_than_clips() -> None:
    timeline = Timeline()
    op_a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0,
    )
    op_b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0,
    )
    timeline = apply_operation(timeline, op_a)
    timeline = apply_operation(timeline, op_b)
    op_t = AddTransitionOp(
        author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
        transition_type="luma", duration_sec=12.0,
    )
    with pytest.raises(ValueError, match="duration"):
        apply_operation(timeline, op_t)


def test_add_transition_appends_effect_to_clip_a() -> None:
    timeline = Timeline()
    op_a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    op_b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    timeline = apply_operation(timeline, op_a)
    timeline = apply_operation(timeline, op_b)
    op_t = AddTransitionOp(
        author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
        transition_type="luma", duration_sec=2.0,
    )
    out = apply_operation(timeline, op_t)
    clip_a = out.tracks[0].clips[0]
    assert len(clip_a.effects) == 1
    assert clip_a.effects[0].effect_type == "transition_luma"
    assert clip_a.effects[0].params["clip_b_id"] == op_b.clip_id


def test_add_transition_with_clip_a_already_trimmed() -> None:
    """Bug-hunt finding: transitions on a clip that was already trimmed by a
    previous transition must still center on the cut (timeline coords), not
    on a stale asset-local coordinate.

    Setup:
      clip_a: position=0, in=0.5, out=2.0 -> asset plays [0.5, 2.0] -> timeline [0, 1.5]
      clip_b: position=2.0, in=0, out=2.0 -> asset plays [0, 2.0] -> timeline [2, 4]
      cut in timeline coords = 1.5 (NOT clip_a.out_point_sec=2.0)
      transition duration 1.0s centered on cut=1.5 -> overlap [1.0, 2.0]
    Expected:
      clip_a.out_point_sec (asset-local) = (1.5 - 0.5) - 0 = 1.0
      clip_b.in_point_sec (asset-local) = (1.5 + 0.5) - 2.0 = 0.0
    """
    timeline = Timeline()
    op_a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.5, out_point_sec=2.0,
    )
    op_b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=2.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    timeline = apply_operation(timeline, op_a)
    timeline = apply_operation(timeline, op_b)
    op_t = AddTransitionOp(
        author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    out = apply_operation(timeline, op_t)
    clip_a = out.tracks[0].clips[0]
    clip_b = out.tracks[0].clips[1]
    assert clip_a.out_point_sec > clip_a.in_point_sec, (
        f"clip_a shrunk past in_point_sec: in={clip_a.in_point_sec}, "
        f"out={clip_a.out_point_sec}"
    )
    assert clip_b.in_point_sec >= 0.0, (
        f"clip_b has negative in_point_sec: {clip_b.in_point_sec}"
    )
    assert clip_a.out_point_sec == pytest.approx(1.0, abs=0.001)
    assert clip_b.in_point_sec == pytest.approx(0.0, abs=0.001)


# ===== Remove / Move / Trim =====

def test_remove_clip_removes_from_track() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    rm = RemoveClipOp(author="user", clip_id=op.clip_id)
    out = apply_operation(timeline, rm)
    assert out.tracks[0].clips == []


def test_remove_clip_for_unknown_id_is_no_op() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    rm = RemoveClipOp(author="user", clip_id="nope")
    out = apply_operation(timeline, rm)
    assert len(out.tracks[0].clips) == 1


def test_move_clip_relocates() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    mv = MoveClipOp(
        author="user", clip_id=op.clip_id,
        new_track_id="v2", new_position_sec=15.0,
    )
    out = apply_operation(timeline, mv)
    assert out.tracks[0].clips == []
    assert len(out.tracks[1].clips) == 1
    assert out.tracks[1].clips[0].position_sec == 15.0


def test_trim_clip_updates_in_and_out() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
    )
    timeline = apply_operation(timeline, op)
    tr = TrimClipOp(
        author="user", clip_id=op.clip_id,
        new_in_point_sec=2.0, new_out_point_sec=8.0,
    )
    out = apply_operation(timeline, tr)
    clip = out.tracks[0].clips[0]
    assert clip.in_point_sec == 2.0
    assert clip.out_point_sec == 8.0


# ===== AddEffect / SetKeyframe =====

def test_add_effect_appends_to_clip() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    eff = AddEffectOp(
        author="user", target_kind="clip", target_id=op.clip_id,
        effect_type="volume", params={"gain": 0.5},
    )
    out = apply_operation(timeline, eff)
    assert len(out.tracks[0].clips[0].effects) == 1


def test_set_keyframe_updates_existing_effect() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    timeline = apply_operation(timeline, op)
    eff = AddEffectOp(
        author="user", target_kind="clip", target_id=op.clip_id,
        effect_type="volume", params={"gain": 1.0},
    )
    timeline = apply_operation(timeline, eff)
    kf = SetKeyframeOp(
        author="user", effect_id=eff.effect_id, param="gain",
        keyframes=[(0.0, 1.0, "linear"), (2.0, 0.0, "linear")],
    )
    out = apply_operation(timeline, kf)
    effects = out.tracks[0].clips[0].effects
    assert effects[0].keyframes["gain"] == [(0.0, 1.0, "linear"), (2.0, 0.0, "linear")]


# ===== Status filtering =====

def test_reverted_op_is_no_op() -> None:
    timeline = Timeline()
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op_reverted = op.model_copy(update={"status": "reverted"})
    out = apply_operation(timeline, op_reverted)
    assert out.tracks == []


# ===== derive_timeline =====

def test_derive_timeline_replays_all_applied_ops() -> None:
    project = Project(name="t")
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0,
    ))
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0,
    ))
    timeline = derive_timeline(project)
    assert len(timeline.tracks) == 1
    assert len(timeline.tracks[0].clips) == 2
    assert timeline.duration_sec == pytest.approx(10.0, abs=0.001)


def test_derive_timeline_skips_reverted_ops() -> None:
    project = Project(name="t")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    op2_reverted = op2.model_copy(update={"status": "reverted"})
    project.edit_graph.append(op1)
    project.edit_graph.append(op2_reverted)
    timeline = derive_timeline(project)
    assert len(timeline.tracks[0].clips) == 1


def test_derive_timeline_computes_duration_from_max_clip_end() -> None:
    project = Project(name="t")
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=3.0,
    ))
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=3.0, in_point_sec=0.0, out_point_sec=8.0,
    ))
    project.edit_graph.append(AddClipOp(
        author="user", asset_hash="c", track_id="v1",
        position_sec=11.0, in_point_sec=0.0, out_point_sec=2.0,
    ))
    timeline = derive_timeline(project)
    assert timeline.duration_sec == pytest.approx(13.0, abs=0.001)
