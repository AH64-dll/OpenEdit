"""Phase 3 Task 4: IR API real implementation (12 methods, parent_id stamped)."""
import pytest
from pydantic import ValidationError

from open_edit.ir.api import IR
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, FreeFormCodeOp,
    GroupEditsOp, MoveClipOp, NormalizeAudioOp, RawMltXmlOp,
    RemoveClipOp, SetAudioGainOp, SetKeyframeOp, TrimClipOp,
)


@pytest.fixture
def ir_instance():
    return IR(ops_buffer=[], project_id="proj1", parent_op_id="e_parent")


def test_add_clip_returns_clip_id_and_appends(ir_instance):
    cid = ir_instance.add_clip(
        asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    assert isinstance(cid, str) and len(cid) > 0
    assert len(ir_instance._ops) == 1
    op = ir_instance._ops[0]
    assert isinstance(op, AddClipOp)
    assert op.parent_id == "e_parent"
    assert op.asset_hash == "abc"
    assert op.track_id == "t1"
    assert op.position_sec == 0.0
    assert op.clip_id == cid


def test_trim_clip_stamps_parent(ir_instance):
    ir_instance.trim_clip(clip_id="c1", in_point_sec=1.0, out_point_sec=2.0)
    op = ir_instance._ops[0]
    assert isinstance(op, TrimClipOp)
    assert op.parent_id == "e_parent"
    assert op.clip_id == "c1"


def test_move_clip_stamps_parent(ir_instance):
    ir_instance.move_clip(clip_id="c1", new_track_id="t2", new_position_sec=5.0)
    op = ir_instance._ops[0]
    assert isinstance(op, MoveClipOp)
    assert op.parent_id == "e_parent"
    assert op.clip_id == "c1"
    assert op.new_track_id == "t2"
    assert op.new_position_sec == 5.0


def test_remove_clip_stamps_parent(ir_instance):
    ir_instance.remove_clip(clip_id="c1")
    op = ir_instance._ops[0]
    assert isinstance(op, RemoveClipOp)
    assert op.parent_id == "e_parent"
    assert op.clip_id == "c1"


def test_add_transition_stamps_parent(ir_instance):
    ir_instance.add_transition(
        clip_a_id="c1", clip_b_id="c2",
        transition_type="luma", duration_sec=0.5,
    )
    op = ir_instance._ops[0]
    assert isinstance(op, AddTransitionOp)
    assert op.parent_id == "e_parent"
    assert op.clip_a_id == "c1"
    assert op.clip_b_id == "c2"
    assert op.duration_sec == 0.5


def test_add_effect_stamps_parent(ir_instance):
    ir_instance.add_effect(
        target_kind="clip", target_id="c1", effect_type="volume",
        params={"gain": 0.5},
    )
    op = ir_instance._ops[0]
    assert isinstance(op, AddEffectOp)
    assert op.parent_id == "e_parent"
    assert op.target_kind == "clip"
    assert op.target_id == "c1"
    assert op.effect_type == "volume"
    assert op.params == {"gain": 0.5}


def test_set_keyframe_stamps_parent(ir_instance):
    ir_instance.set_keyframe(
        effect_id="fx1", param="gain",
        keyframes=[(0.0, 1.0, "linear"), (1.0, 0.0, "linear")],
    )
    op = ir_instance._ops[0]
    assert isinstance(op, SetKeyframeOp)
    assert op.parent_id == "e_parent"
    assert op.effect_id == "fx1"
    assert op.param == "gain"
    assert op.keyframes == [(0.0, 1.0, "linear"), (1.0, 0.0, "linear")]


def test_set_audio_gain_stamps_parent(ir_instance):
    ir_instance.set_audio_gain(clip_id="c1", gain_db=-3.0)
    op = ir_instance._ops[0]
    assert isinstance(op, SetAudioGainOp)
    assert op.parent_id == "e_parent"
    assert op.clip_id == "c1"
    assert op.gain_db == -3.0


def test_normalize_audio_stamps_parent(ir_instance):
    ir_instance.normalize_audio(
        target_kind="track", target_id="t1", target_dbfs=-14.0,
    )
    op = ir_instance._ops[0]
    assert isinstance(op, NormalizeAudioOp)
    assert op.parent_id == "e_parent"
    assert op.target_kind == "track"
    assert op.target_id == "t1"
    assert op.target_dbfs == -14.0


def test_group_edits_stamps_parent(ir_instance):
    ir_instance.group_edits(edit_ids=["e1", "e2"], label="group_a")
    op = ir_instance._ops[0]
    assert isinstance(op, GroupEditsOp)
    assert op.parent_id == "e_parent"
    assert op.edit_ids == ["e1", "e2"]
    assert op.label == "group_a"


def test_raw_mlt_xml_stamps_parent(ir_instance):
    ir_instance.raw_mlt_xml(xml="<mlt><tractor/></mlt>", description="raw_a")
    op = ir_instance._ops[0]
    assert isinstance(op, RawMltXmlOp)
    assert op.parent_id == "e_parent"
    assert op.xml == "<mlt><tractor/></mlt>"
    assert op.description == "raw_a"


def test_free_form_code_stamps_parent(ir_instance):
    ir_instance.free_form_code(code="print('hello')")
    op = ir_instance._ops[0]
    assert isinstance(op, FreeFormCodeOp)
    assert op.parent_id == "e_parent"
    assert op.code == "print('hello')"


def test_ir_works_with_list_subclass():
    """H10: the buffer is a SupportsAppend; works with any list-like."""
    class MyBuf(list):
        def append(self, x):
            super().append(x)

    ir = IR(ops_buffer=MyBuf(), project_id="p", parent_op_id="e")
    ir.add_clip(asset_hash="x", track_id="t", position_sec=0.0)
    assert len(ir._ops) == 1
    assert isinstance(ir._ops[0], AddClipOp)


def test_pydantic_validation_error_on_bad_input(ir_instance):
    """Schema errors fail at build time (Pydantic ValidationError)."""
    with pytest.raises(ValidationError):
        ir_instance.add_transition(
            clip_a_id="c1", clip_b_id="c2",
            transition_type="star_wipe", duration_sec=0.5,
        )
