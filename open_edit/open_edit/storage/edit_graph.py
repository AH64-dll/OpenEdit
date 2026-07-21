"""SQLite-backed edit graph store.

One .db file per project. WAL mode for concurrent reads. Stores every
operation ever applied (including reverted/superseded). The durable
record; the source of truth for the IR.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pydantic import TypeAdapter

from open_edit.ir.types import OperationUnion


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class EditGraphStore:
    """SQLite store for a project's edit graph + job lock."""

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
        with self._conn() as conn:
            conn.executescript(SCHEMA_PATH.read_text())

    @property
    def project_id(self) -> str:
        """Return the stable project_id for this db file. Generated on first open.

        Phase 3 Task 1: stored in the project_meta table. Stable across reopens.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT value FROM project_meta WHERE key = 'project_id'"
            )
            row = cur.fetchone()
            if row is not None:
                return row[0]
            from open_edit.ir.types import new_id
            pid = new_id()
            conn.execute(
                "INSERT INTO project_meta (key, value) VALUES ('project_id', ?)",
                (pid,),
            )
            return pid

    def get_project_meta(self) -> dict[str, Any]:
        """Return the project_meta table as a dict. Empty if no rows.

        JSON-encoded values are decoded back to their native types (numbers,
        booleans, lists, dicts, null). Plain string values (e.g. the
        project_id) are returned as-is.
        """
        with self._conn() as conn:
            cur = conn.execute("SELECT key, value FROM project_meta")
            out: dict[str, Any] = {}
            for k, v in cur.fetchall():
                if isinstance(v, str) and v:
                    try:
                        out[k] = json.loads(v)
                    except (ValueError, TypeError):
                        out[k] = v
                else:
                    out[k] = v
            return out

    def set_project_meta_field(self, key: str, value: Any) -> None:
        """Set a single project_meta field. Persists immediately.

        Non-string values are JSON-encoded so that the table round-trips
        native types (int, float, list, dict) through TEXT.
        """
        if isinstance(value, str):
            raw = value
        else:
            raw = json.dumps(value)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO project_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, raw),
            )

    def append(
        self, op: OperationUnion, sequence_num: int | None = None
    ) -> int:
        """Append an operation. Returns the assigned sequence_num."""
        with self._conn() as conn:
            if sequence_num is None:
                cur = conn.execute(
                    "SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits"
                )
                sequence_num = cur.fetchone()[0]
            conn.execute(
                "INSERT INTO edits "
                "(edit_id, parent_id, kind, author, timestamp, status, "
                " sequence_num, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    op.edit_id, op.parent_id, op.kind, op.author, op.timestamp,
                    op.status, sequence_num, op.model_dump_json(),
                ),
            )
        return sequence_num

    def load_all(self) -> list[OperationUnion]:
        """Load all operations in sequence_num order."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT payload, status FROM edits ORDER BY sequence_num"
            )
            ops: list[OperationUnion] = []
            for row in cur.fetchall():
                op = TypeAdapter(OperationUnion).validate_json(row[0])
                op.status = row[1]
                ops.append(op)
            return ops

    def update_status(self, edit_id: str, new_status: str) -> None:
        """Update an operation's status (e.g. for undo/revert or supersede)."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE edits SET status = ? WHERE edit_id = ?",
                (new_status, edit_id),
            )

    def reorder(self, edit_id_a: str, edit_id_b: str) -> None:
        """Swap the sequence_num of two adjacent operations.

        Raises ValueError if either id does not exist or if the two ops
        are not adjacent in sequence_num.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT edit_id, sequence_num FROM edits "
                "WHERE edit_id IN (?, ?) ORDER BY sequence_num",
                (edit_id_a, edit_id_b),
            )
            rows = cur.fetchall()
            if len(rows) != 2:
                raise ValueError(f"Both edits must exist; got {len(rows)} rows")
            (id1, seq1), (id2, seq2) = rows
            if abs(seq1 - seq2) != 1:
                raise ValueError(
                    f"Edits must be adjacent to reorder; "
                    f"got sequence_num gap {abs(seq1 - seq2)}"
                )
            conn.execute(
                "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
                (seq2, id1),
            )
            conn.execute(
                "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
                (seq1, id2),
            )
