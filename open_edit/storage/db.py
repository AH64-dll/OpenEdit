"""Shared SQLite connection helper for the storage layer.

All stores open the project's .db file through :func:`open_conn`: WAL mode
for concurrent readers, ``foreign_keys=ON``, rows as :class:`sqlite3.Row`,
and a commit-on-success / rollback-on-error context manager.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def open_conn(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open a connection to ``db_path`` with the canonical store settings.

    Commits on normal exit, rolls back on exception, always closes.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
