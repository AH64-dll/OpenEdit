"""SQLite-backed command idempotency store.

Tracks tool commands keyed by command_id so a retried request with the same
id does not apply the same operation twice. Shares the project's edit-graph
db file and schema with ``EditGraphStore``.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from open_edit.ir.ids import now_iso8601


class CommandStore:
    """SQLite store for command idempotency records."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        from open_edit.storage.migrations import ensure_schema

        with self._conn() as conn:
            ensure_schema(conn)

    def record_command(
        self, command_id: str, project_id: str, tool_name: str,
        status: str = "pending", payload_hash: str | None = None,
    ) -> None:
        """Record a command for idempotency. No-op if command_id exists."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO commands "
                "(command_id, project_id, tool_name, status, created_at, "
                " payload_hash, result_json) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (
                    command_id, project_id, tool_name, status,
                    now_iso8601(), payload_hash,
                ),
            )

    def command_exists(self, command_id: str) -> bool:
        """Return True if a command with the given id has been recorded."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT 1 FROM commands WHERE command_id = ? LIMIT 1",
                (command_id,),
            )
            return cur.fetchone() is not None

    def finish_command(
        self, command_id: str, status: str = "done",
        result_json: str | None = None,
    ) -> None:
        """Mark a command as finished with a status and optional result."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE commands SET status = ?, result_json = ? "
                "WHERE command_id = ?",
                (status, result_json, command_id),
            )

    def get_command_result(self, command_id: str) -> str | None:
        """Return the stored result_json for a command, or None."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT result_json FROM commands WHERE command_id = ?",
                (command_id,),
            )
            row = cur.fetchone()
            return row[0] if row is not None else None

    def get_command_status(self, command_id: str) -> str | None:
        """Return the stored status for a command, or None."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT status FROM commands WHERE command_id = ?",
                (command_id,),
            )
            row = cur.fetchone()
            return row[0] if row is not None else None
