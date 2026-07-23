"""SQLite-backed edit graph store.

One .db file per project. WAL mode for concurrent reads. Stores every
operation ever applied (including reverted/superseded). The durable
record; the source of truth for the IR.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import TypeAdapter

from open_edit.ir.types import OperationUnion, new_id


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
        from open_edit.storage.migrations import ensure_schema

        with self._conn() as conn:
            ensure_schema(conn)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

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
        self, op: OperationUnion, sequence_num: int | None = None,
        command_id: str | None = None,
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
            conn.execute(
                "INSERT INTO edit_status_events "
                "(event_id, edit_id, from_status, to_status, command_id, "
                " reason, changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id(), op.edit_id, None, op.status or "applied",
                    command_id, "append", op.timestamp or self._now_iso(),
                ),
            )
        return sequence_num

    def load_all(self) -> list[OperationUnion]:
        """Load all operations in sequence_num order."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT payload, status, parent_id FROM edits ORDER BY sequence_num"
            )
            ops: list[OperationUnion] = []
            for row in cur.fetchall():
                op = TypeAdapter(OperationUnion).validate_json(row[0])
                op.status = row[1]
                op.parent_id = row[2]
                ops.append(op)
            return ops

    def update_status(
        self, edit_id: str, new_status: str,
        command_id: str | None = None, reason: str | None = None,
    ) -> None:
        """Update an operation's status (e.g. for undo/revert or supersede)."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT status FROM edits WHERE edit_id = ?", (edit_id,)
            )
            row = cur.fetchone()
            from_status = row[0] if row is not None else None
            conn.execute(
                "UPDATE edits SET status = ? WHERE edit_id = ?",
                (new_status, edit_id),
            )
            conn.execute(
                "INSERT INTO edit_status_events "
                "(event_id, edit_id, from_status, to_status, command_id, "
                " reason, changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id(), edit_id, from_status, new_status,
                    command_id, reason, self._now_iso(),
                ),
            )

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
                    self._now_iso(), payload_hash,
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

    def save_timeline_snapshot(
        self, edit_graph_hash: str, project_id: str, timeline_json: str,
    ) -> None:
        """Store a derived timeline snapshot keyed by edit-graph hash."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO timeline_snapshots "
                "(edit_graph_hash, project_id, timeline_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (edit_graph_hash, project_id, timeline_json, self._now_iso()),
            )

    def load_timeline_snapshot(self, edit_graph_hash: str) -> str | None:
        """Return the stored timeline_json for a hash, or None."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT timeline_json FROM timeline_snapshots "
                "WHERE edit_graph_hash = ?",
                (edit_graph_hash,),
            )
            row = cur.fetchone()
            return row[0] if row is not None else None

    def set_edit_graph_hash(self, h: str) -> None:
        """Store the canonical edit-graph hash in project_meta."""
        self.set_project_meta_field("edit_graph_hash", h)

    def delete_op(self, edit_id: str) -> bool:
        """Remove an operation from the edit graph by id.

        Any ops that had ``parent_id == edit_id`` get their parent_id
        cleared (set to NULL) so the graph remains consistent.
        Returns True if an op was found and deleted.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT edit_id FROM edits WHERE edit_id = ?", (edit_id,)
            )
            if cur.fetchone() is None:
                return False
            conn.execute(
                "UPDATE edits SET parent_id = NULL WHERE parent_id = ?",
                (edit_id,),
            )
            conn.execute(
                "DELETE FROM edits WHERE edit_id = ?", (edit_id,)
            )
        return True

    def move_arbitrary(self, edit_id: str, new_sequence_num: int) -> bool:
        """Move an operation to any position in the sequence.

        This is a general reorder operation (not just adjacent swap).
        Returns True if the op was found and moved.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT sequence_num FROM edits WHERE edit_id = ?",
                (edit_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False
            old_pos = row[0]
            if old_pos == new_sequence_num:
                return True
            if old_pos < new_sequence_num:
                conn.execute(
                    "UPDATE edits SET sequence_num = sequence_num - 1 "
                    "WHERE sequence_num > ? AND sequence_num <= ?",
                    (old_pos, new_sequence_num),
                )
            else:
                conn.execute(
                    "UPDATE edits SET sequence_num = sequence_num + 1 "
                    "WHERE sequence_num >= ? AND sequence_num < ?",
                    (new_sequence_num, old_pos),
                )
            conn.execute(
                "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
                (new_sequence_num, edit_id),
            )
        return True

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
