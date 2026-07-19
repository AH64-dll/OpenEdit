"""Tests for the EditGraphStore (SQLite-backed edit graph)."""
from pathlib import Path

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
