"""Phase 4 Task 1: originating_note_id on Operation + IR API + sandbox_bridge."""
import json
import pytest
from pathlib import Path

from open_edit.ir.types import (
    AddClipOp, AddEffectOp, SetKeyframeOp, Operation, Project, Asset,
)
from open_edit.ir.api import IR
from open_edit.storage.edit_graph import EditGraphStore


def _make_buffer() -> list:
    return []


def test_operation_default_none():
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    assert op.originating_note_id is None


def test_operation_explicit_set():
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_42",
    )
    assert op.originating_note_id == "note_42"


def test_operation_serializes_with_field():
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_42",
    )
    data = json.loads(op.model_dump_json())
    assert data["originating_note_id"] == "note_42"


def test_operation_back_compat_no_field_in_payload():
    """Existing fixtures that don't set the field must still serialize/deserialize."""
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    data = json.loads(op.model_dump_json())
    assert data["originating_note_id"] is None
    # Round-trip
    op2 = AddClipOp.model_validate(data)
    assert op2.originating_note_id is None


def test_ir_add_clip_stamps_originating_note_id(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    buf = _make_buffer()
    ir = IR(buf, project_id="p1", parent_op_id=None)
    clip_id = ir.add_clip(
        asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_99",
    )
    assert len(buf) == 1
    assert buf[0].originating_note_id == "note_99"
    assert buf[0].clip_id == clip_id


def test_ir_add_clip_default_none(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    buf = _make_buffer()
    ir = IR(buf, project_id="p1", parent_op_id=None)
    ir.add_clip(asset_hash="abc", track_id="t1", position_sec=0.0)
    assert buf[0].originating_note_id is None


def test_ir_add_effect_stamps(tmp_path):
    buf = _make_buffer()
    ir = IR(buf, project_id="p1", parent_op_id=None)
    ir.add_effect(
        target_kind="clip", target_id="c1", effect_type="volume",
        params={"gain": 0.5}, originating_note_id="note_5",
    )
    assert buf[0].originating_note_id == "note_5"


def test_edit_graph_store_round_trip(tmp_path):
    """EditGraphStore reads/writes the payload JSON; originating_note_id is preserved."""
    store = EditGraphStore(tmp_path / "edit_graph.db")
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_42",
    )
    seq = store.append(op)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].originating_note_id == "note_42"
