"""Tests for commutativity of operations (used by reorder)."""
from open_edit.ir.commutativity import can_swap
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, MoveClipOp, RemoveClipOp,
    SetKeyframeOp, TrimClipOp,
)


def _add(asset: str, track: str = "v1", pos: float = 0.0) -> AddClipOp:
    return AddClipOp(author="user", asset_hash=asset, track_id=track, position_sec=pos)


def test_add_clips_on_different_tracks_commute() -> None:
    a = _add("a", "v1", 0.0)
    b = _add("b", "audio_1", 0.0)
    assert can_swap(a, b) is True


def test_add_clips_on_same_track_commute() -> None:
    a = _add("a", "v1", 0.0)
    b = _add("b", "v1", 5.0)
    assert can_swap(a, b) is True


def test_add_clip_and_remove_different_clips_commute() -> None:
    a = _add("a")
    b = RemoveClipOp(author="user", clip_id="other")
    assert can_swap(a, b) is True


def test_add_clip_and_remove_same_clip_does_not_commute() -> None:
    a = _add("a")
    b = RemoveClipOp(author="user", clip_id=a.clip_id)
    assert can_swap(a, b) is False


def test_add_transition_and_unrelated_add_clip_commute() -> None:
    a = AddTransitionOp(
        author="user", clip_a_id="c1", clip_b_id="c2",
        transition_type="luma", duration_sec=1.0,
    )
    b = _add("z", "v2", 0.0)
    assert can_swap(a, b) is True


def test_add_effect_on_clip_and_remove_clip_does_not_commute() -> None:
    a = AddEffectOp(
        author="user", target_kind="clip", target_id="c1",
        effect_type="volume", params={"gain": 0.5},
    )
    b = RemoveClipOp(author="user", clip_id="c1")
    assert can_swap(a, b) is False


def test_set_keyframe_on_different_effects_commute() -> None:
    a = SetKeyframeOp(
        author="user", effect_id="fx1", param="gain",
        keyframes=[(0.0, 1.0, "linear")],
    )
    b = SetKeyframeOp(
        author="user", effect_id="fx2", param="gain",
        keyframes=[(0.0, 0.5, "linear")],
    )
    assert can_swap(a, b) is True
