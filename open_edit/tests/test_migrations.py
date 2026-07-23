import sqlite3

from open_edit.storage.migrations import (
    CURRENT_VERSION,
    current_version,
    ensure_schema,
    run_migrations,
)

EXPECTED_TABLES = {"project_meta", "edits", "jobs"}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {r[0] for r in rows}


def test_run_migrations_applies_initial():
    conn = sqlite3.connect(":memory:")
    assert current_version(conn) == 0
    final = run_migrations(conn)
    assert final == CURRENT_VERSION == 2
    assert current_version(conn) == 2
    assert EXPECTED_TABLES <= _tables(conn)


def test_run_migrations_is_idempotent():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    first = current_version(conn)
    second = run_migrations(conn)
    assert second == first == CURRENT_VERSION
    assert current_version(conn) == first


def test_ensure_schema_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    version = ensure_schema(conn)
    assert version == CURRENT_VERSION
    assert EXPECTED_TABLES <= _tables(conn)


def test_ensure_schema_idempotent_across_reopen(tmp_path):
    db = tmp_path / "edit_graph.db"
    conn = sqlite3.connect(str(db))
    ensure_schema(conn)
    conn.close()

    conn2 = sqlite3.connect(str(db))
    version = ensure_schema(conn2)
    assert version == CURRENT_VERSION
    assert EXPECTED_TABLES <= _tables(conn2)
    conn2.close()
