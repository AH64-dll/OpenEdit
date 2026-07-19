"""Tests for op validation (schema + referential + asset-exists)."""
import pytest

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    Asset,
    MoveClipOp,
    Project,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    TrimClipOp,
)
from open_edit.ir.validate import validate_op


def _asset(asset_hash: str) -> Asset:
    return Asset(
        asset_hash=asset_hash,
        original_path=f"/tmp/{asset_hash}.mp4",
        stored_path=f"/tmp/{asset_hash}.mp4",
        type="video", duration_sec=2.0,
    )


def test_valid_add_clip_returns_no_errors() -> None:
    project = Project(name="t", assets={"abc": _asset("abc")})
    op = AddClipOp(author="user", asset_hash="abc", track_id="v1", position_sec=0.0)
    assert validate_op(op, project) == []


def test_add_clip_rejects_unknown_asset_hash() -> None:
    project = Project(name="t", assets={})
    op = AddClipOp(author="user", asset_hash="missing", track_id="v1", position_sec=0.0)
    errors = validate_op(op, project)
    assert any("missing" in e for e in errors)
    assert any("fix:" in e for e in errors)


def test_remove_clip_with_unknown_clip_id_warns_but_no_error() -> None:
    project = Project(name="t")
    op = RemoveClipOp(author="user", clip_id="nonexistent")
    assert validate_op(op, project) == []


def test_move_clip_with_unknown_clip_id_is_error() -> None:
    project = Project(name="t")
    op = MoveClipOp(
        author="user", clip_id="nonexistent",
        new_track_id="v1", new_position_sec=0.0,
    )
    errors = validate_op(op, project)
    assert any("nonexistent" in e for e in errors)


def test_trim_clip_with_unknown_clip_id_is_error() -> None:
    project = Project(name="t")
    op = TrimClipOp(
        author="user", clip_id="nope",
        new_in_point_sec=0.0, new_out_point_sec=1.0,
    )
    errors = validate_op(op, project)
    assert any("nope" in e for e in errors)


def test_add_transition_requires_existing_clips() -> None:
    project = Project(name="t")
    op = AddTransitionOp(
        author="user", clip_a_id="a", clip_b_id="b",
        transition_type="luma", duration_sec=1.0,
    )
    errors = validate_op(op, project)
    assert len(errors) == 2


def test_add_transition_with_known_clips_returns_no_errors() -> None:
    project = Project(name="t")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    project.edit_graph.append(op1)
    project.edit_graph.append(op2)
    op3 = AddTransitionOp(
        author="user", clip_a_id=op1.clip_id, clip_b_id=op2.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    assert validate_op(op3, project) == []


def test_add_effect_with_unknown_target_is_error() -> None:
    project = Project(name="t")
    op = AddEffectOp(
        author="user", target_kind="clip", target_id="missing",
        effect_type="volume", params={"gain": 1.0},
    )
    errors = validate_op(op, project)
    assert any("missing" in e for e in errors)


def test_set_keyframe_with_unknown_effect_id_is_error() -> None:
    project = Project(name="t")
    op = SetKeyframeOp(
        author="user", effect_id="nope", param="gain",
        keyframes=[(0.0, 1.0, "linear")],
    )
    errors = validate_op(op, project)
    assert any("nope" in e for e in errors)


def test_set_audio_gain_with_unknown_clip_is_error() -> None:
    project = Project(name="t")
    op = SetAudioGainOp(author="user", clip_id="nope", gain_db=-6.0)
    errors = validate_op(op, project)
    assert any("nope" in e for e in errors)
