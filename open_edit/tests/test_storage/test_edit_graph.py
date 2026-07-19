"""Tests for the EditGraphStore (SQLite-backed edit graph)."""
from pathlib import Path

from open_edit.ir.types import AddClipOp
from open_edit.storage.edit_graph import EditGraphStore


def test_init_creates_db_file(tmp_path: Path) -> None:
    db_path = tmp_path / "project.db"
    EditGraphStore(db_path)
    assert db_path.exists()


def test_init_creates_edits_table(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='edits'"
        )
        assert cur.fetchone() is not None


def test_init_creates_jobs_table(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        )
        assert cur.fetchone() is not None


def test_init_enables_wal_mode(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode.lower() == "wal"


def test_init_enables_foreign_keys(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "project.db")
    with store._conn() as conn:
        cur = conn.execute("PRAGMA foreign_keys")
        enabled = cur.fetchone()[0]
        assert enabled == 1


def test_append_assigns_increasing_sequence_num(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    seq1 = store.append(op1)
    seq2 = store.append(op2)
    assert seq1 == 0
    assert seq2 == 1


def test_load_all_returns_ops_in_sequence_order(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    store.append(op1)
    store.append(op2)
    ops = store.load_all()
    assert len(ops) == 2
    assert ops[0].asset_hash == "a"
    assert ops[1].asset_hash == "b"


def test_update_status_marks_reverted(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    store.append(op)
    store.update_status(op.edit_id, "reverted")
    ops = store.load_all()
    assert ops[0].status == "reverted"


def test_reorder_swaps_adjacent_ops(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=10.0)
    store.append(op1)
    store.append(op2)
    store.append(op3)
    store.reorder(op1.edit_id, op2.edit_id)
    ops = store.load_all()
    assert ops[0].asset_hash == "b"
    assert ops[1].asset_hash == "a"
    assert ops[2].asset_hash == "c"


def test_reorder_rejects_non_adjacent_ops(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
    op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=10.0)
    store.append(op1)
    store.append(op2)
    store.append(op3)
    import pytest
    with pytest.raises(ValueError, match="adjacent"):
        store.reorder(op1.edit_id, op3.edit_id)


def test_reorder_rejects_missing_ops(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
    store.append(op1)
    import pytest
    with pytest.raises(ValueError, match="exist"):
        store.reorder(op1.edit_id, "nonexistent-id")
