"""Tests for the Pydantic operation types."""
import uuid

import pytest
from pydantic import TypeAdapter, ValidationError

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    FreeFormCodeOp,
    GroupEditsOp,
    MoveClipOp,
    NormalizeAudioOp,
    Operation,
    OperationUnion,
    Project,
    RawMltXmlOp,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    TrimClipOp,
    new_id,
    now_iso8601,
)


# ===== Helpers =====

def test_new_id_returns_uuid_string() -> None:
    aid = new_id()
    uuid.UUID(aid)


def test_new_id_is_unique() -> None:
    assert new_id() != new_id()


def test_now_iso8601_returns_string() -> None:
    ts = now_iso8601()
    assert isinstance(ts, str)
    assert "T" in ts


# ===== Base Operation =====

def test_operation_default_edit_id_is_unique() -> None:
    a = Operation(author="user", kind="test")
    b = Operation(author="user", kind="test")
    assert a.edit_id != b.edit_id


def test_operation_default_status_is_applied() -> None:
    op = Operation(author="user", kind="test")
    assert op.status == "applied"


def test_operation_default_parent_id_is_none() -> None:
    op = Operation(author="user", kind="test")
    assert op.parent_id is None


def test_operation_status_must_be_valid_literal() -> None:
    with pytest.raises(ValidationError):
        Operation(author="user", kind="test", status="deleted")


def test_operation_author_must_be_ai_or_user() -> None:
    with pytest.raises(ValidationError):
        Operation(author="robot", kind="test")


# ===== AddClipOp =====

def test_add_clip_op_minimal() -> None:
    op = AddClipOp(
        author="ai", asset_hash="abc123", track_id="video_1", position_sec=0.0,
    )
    assert op.kind == "add_clip"
    assert op.track_kind == "video"
    assert op.in_point_sec == 0.0
    assert op.out_point_sec is None
    assert op.clip_id != op.edit_id


def test_add_clip_op_track_kind_must_be_video_or_audio() -> None:
    with pytest.raises(ValidationError):
        AddClipOp(
            author="ai", asset_hash="abc", track_id="t",
            position_sec=0.0, track_kind="text",
        )


# ===== AddTransitionOp =====

def test_add_transition_op_fields() -> None:
    op = AddTransitionOp(
        author="ai", clip_a_id="c1", clip_b_id="c2",
        transition_type="luma", duration_sec=1.0,
    )
    assert op.kind == "add_transition"
    assert op.transition_type == "luma"


def test_add_transition_op_type_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        AddTransitionOp(
            author="ai", clip_a_id="c1", clip_b_id="c2",
            transition_type="star_wipe", duration_sec=1.0,
        )


# ===== AddEffectOp =====

def test_add_effect_op_minimal() -> None:
    op = AddEffectOp(
        author="ai", target_kind="clip", target_id="c1",
        effect_type="volume", params={"gain": 1.0},
    )
    assert op.kind == "add_effect"
    assert op.effect_id != op.edit_id


# ===== SetKeyframeOp =====

def test_set_keyframe_op_fields() -> None:
    op = SetKeyframeOp(
        author="ai", effect_id="fx1", param="gain",
        keyframes=[(0.0, 1.0, "linear"), (2.0, 0.0, "linear")],
    )
    assert op.kind == "set_keyframe"
    assert op.keyframes[0] == (0.0, 1.0, "linear")


# ===== Audio ops =====

def test_set_audio_gain_op() -> None:
    op = SetAudioGainOp(author="ai", clip_id="c1", gain_db=-6.0)
    assert op.kind == "set_audio_gain"
    assert op.gain_db == -6.0


def test_normalize_audio_op_defaults() -> None:
    op = NormalizeAudioOp(
        author="ai", target_kind="track", target_id="audio_1",
    )
    assert op.target_dbfs == -16.0


# ===== Grouping =====

def test_group_edits_op() -> None:
    op = GroupEditsOp(author="ai", edit_ids=["e1", "e2"], label="AI: add intro music")
    assert op.kind == "group_edits"
    assert op.edit_ids == ["e1", "e2"]


# ===== Escape hatches =====

def test_raw_mlt_xml_op() -> None:
    op = RawMltXmlOp(
        author="ai", xml="<filter/>", description="Vintage",
    )
    assert op.kind == "raw_mlt_xml"


def test_free_form_code_op() -> None:
    op = FreeFormCodeOp(author="ai", code="ir.add_clip('abc', 'v1', 0.0)")
    assert op.kind == "free_form_code"


# ===== Remove/Move/Trim =====

def test_remove_clip_op() -> None:
    op = RemoveClipOp(author="ai", clip_id="c1")
    assert op.kind == "remove_clip"


def test_move_clip_op() -> None:
    op = MoveClipOp(author="ai", clip_id="c1", new_track_id="v2", new_position_sec=10.0)
    assert op.kind == "move_clip"


def test_trim_clip_op() -> None:
    op = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=2.0, new_out_point_sec=5.0)
    assert op.kind == "trim_clip"


# ===== Discriminated union =====

def test_operation_union_validates_by_kind() -> None:
    payload = {
        "kind": "add_clip", "author": "ai", "asset_hash": "abc",
        "track_id": "v1", "position_sec": 0.0, "edit_id": "x",
        "parent_id": None, "timestamp": "2026-07-20T00:00:00Z", "status": "applied",
    }
    op = TypeAdapter(OperationUnion).validate_python(payload)
    assert isinstance(op, AddClipOp)
    assert op.edit_id == "x"


def test_operation_union_rejects_unknown_kind() -> None:
    payload = {"kind": "unknown_op", "author": "ai"}
    with pytest.raises(ValidationError):
        TypeAdapter(OperationUnion).validate_python(payload)


# ===== Serialization round-trip =====

def test_operation_json_round_trip() -> None:
    op = AddClipOp(author="ai", asset_hash="abc", track_id="v1", position_sec=0.0)
    json_str = op.model_dump_json()
    restored = AddClipOp.model_validate_json(json_str)
    assert restored.edit_id == op.edit_id
    assert restored.asset_hash == op.asset_hash


def test_project_has_assets_and_edit_graph() -> None:
    p = Project(name="test")
    assert p.assets == {}
    assert p.edit_graph == []
    assert p.project_id
