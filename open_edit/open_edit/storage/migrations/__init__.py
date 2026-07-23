"""Lightweight, safe SQLite migration runner for the edit-graph store.

Schema evolves via versioned SQL files in this package instead of ad-hoc
``CREATE TABLE IF NOT EXISTS`` scattered through the code. Each migration is a
``NNNN_name.sql`` file; its numeric prefix is its version id. The database's
``PRAGMA user_version`` tracks the highest applied migration.

Notes
-----
This is implemented as a *package* (``migrations/__init__.py``) rather than a
module named ``migrations.py`` on purpose: a ``migrations.py`` module and a
``migrations/`` package cannot coexist in the same directory (the package
shadows the module and the ``.py`` becomes unreachable). The import path
``open_edit.storage.migrations`` and the public API are identical either way.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

CURRENT_VERSION: int = 2

MIGRATIONS_DIR = Path(__file__).parent
_LEGACY_SCHEMA_PATH = MIGRATIONS_DIR.parent / "schema.sql"
_MIGRATION_RE = re.compile(r"^(\d{4})_.*\.sql$")

__all__ = [
    "CURRENT_VERSION",
    "run_migrations",
    "current_version",
    "ensure_schema",
]


def current_version(conn: sqlite3.Connection) -> int:
    """Return the schema version recorded in ``PRAGMA user_version``."""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _migration_files() -> dict[int, Path]:
    """Map migration id -> SQL file path, discovered from this directory."""
    out: dict[int, Path] = {}
    for path in MIGRATIONS_DIR.glob("*.sql"):
        m = _MIGRATION_RE.match(path.name)
        if m:
            out[int(m.group(1))] = path
    return out


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending migrations up to ``CURRENT_VERSION``.

    Reads ``PRAGMA user_version`` and, for each migration id greater than the
    current version up to ``CURRENT_VERSION``, executes the corresponding SQL
    file and bumps ``user_version`` atomically. Idempotent: re-running when the
    database is already current is a no-op. Returns the final version.
    """
    version = current_version(conn)
    if version >= CURRENT_VERSION:
        return version

    files = _migration_files()
    for mid in range(version + 1, CURRENT_VERSION + 1):
        path = files.get(mid)
        if path is None:
            raise FileNotFoundError(
                f"Missing migration file for version {mid} in {MIGRATIONS_DIR}"
            )
        sql = path.read_text()
        try:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {int(mid)}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        version = mid
    return version


def ensure_schema(conn: sqlite3.Connection) -> int:
    """Ensure the full schema exists.

    Runs the versioned migrations, then, as a safety net, re-applies the legacy
    ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS`` statements
    from ``schema.sql``. This guarantees behavior is unchanged even if a
    migration file is missing. Returns the current schema version.
    """
    run_migrations(conn)
    if _LEGACY_SCHEMA_PATH.exists():
        conn.executescript(_LEGACY_SCHEMA_PATH.read_text())
        conn.commit()
    return current_version(conn)
