"""Tests for edit graph CRUD API endpoints (Wave 1.4)."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from open_edit.ir.types import AddClipOp
from open_edit.serve.app import app
from open_edit.storage.edit_graph import EditGraphStore

client = TestClient(app)


def test_edit_graph_store_delete_op() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "edit_graph.db"
        store = EditGraphStore(db_path)
        op = AddClipOp(
            edit_id=str(uuid.uuid4()),
            author="ai",
            asset_hash="b" * 64,
            track_id="v1",
            position_sec=0,
            in_point_sec=0,
            out_point_sec=5,
        )
        store.append(op)
        assert len(store.load_all()) == 1
        assert store.delete_op(op.edit_id) is True
        assert len(store.load_all()) == 0
        assert store.delete_op("nonexistent") is False


def test_edit_graph_store_move_arbitrary() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "edit_graph.db"
        store = EditGraphStore(db_path)
        op1 = AddClipOp(
            edit_id="id1",
            author="ai",
            asset_hash="c" * 64,
            track_id="v1",
            position_sec=0,
            in_point_sec=0,
            out_point_sec=5,
        )
        op2 = AddClipOp(
            edit_id="id2",
            author="ai",
            asset_hash="d" * 64,
            track_id="v1",
            position_sec=5,
            in_point_sec=0,
            out_point_sec=5,
        )
        op3 = AddClipOp(
            edit_id="id3",
            author="ai",
            asset_hash="e" * 64,
            track_id="v1",
            position_sec=10,
            in_point_sec=0,
            out_point_sec=5,
        )
        store.append(op1)
        store.append(op2)
        store.append(op3)
        # Move id3 to front (sequence_num 0)
        assert store.move_arbitrary("id3", 0) is True
        ops = store.load_all()
        ids = [o.edit_id for o in ops]
        assert ids == ["id3", "id1", "id2"]


def test_delete_op_clears_parent_references() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "edit_graph.db"
        store = EditGraphStore(db_path)
        parent_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        parent = AddClipOp(
            edit_id=parent_id,
            author="ai",
            asset_hash="f" * 64,
            track_id="v1",
            position_sec=0,
            in_point_sec=0,
            out_point_sec=5,
        )
        child = AddClipOp(
            edit_id=child_id,
            author="ai",
            parent_id=parent_id,
            asset_hash="a" * 64,
            track_id="v2",
            position_sec=5,
            in_point_sec=0,
            out_point_sec=5,
        )
        store.append(parent)
        store.append(child)
        assert store.delete_op(parent_id) is True
        ops = store.load_all()
        assert len(ops) == 1
        assert ops[0].edit_id == child_id
        assert ops[0].parent_id is None
