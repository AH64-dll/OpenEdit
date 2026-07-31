"""SQLite-backed edit graph store.

One .db file per project. WAL mode for concurrent reads. Stores every
operation ever applied (including reverted/superseded). The durable
record; the source of truth for the IR.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pydantic import TypeAdapter

from open_edit.ir import validate as _ir_validate
from open_edit.ir.ids import now_iso8601
from open_edit.ir.types import OperationUnion, new_id
from open_edit.storage import ordering as _ordering
from open_edit.storage.commands import CommandStore
from open_edit.storage.db import open_conn
from open_edit.storage.timeline_cache import TimelineSnapshotStore

_APPEND_LOCK = threading.Lock()


class GraphRevisionConflict(RuntimeError):
    """Raised when a mutation was composed against an obsolete graph revision."""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"stale graph revision: expected {expected}, current {actual}")


class EditGraphStore:
    """SQLite store for a project's edit graph + job lock."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.commands = CommandStore(self.db_path)
        self.snapshots = TimelineSnapshotStore(self.db_path)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with open_conn(self.db_path) as conn:
            yield conn

    def _init_schema(self) -> None:
        from open_edit.storage.migrations import ensure_schema

        with self._conn() as conn:
            ensure_schema(conn)

    @staticmethod
    def _revision_in(conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT value FROM project_meta WHERE key = 'graph_revision'").fetchone()
        return int(row[0]) if row is not None else 0

    @classmethod
    def _check_and_bump_revision(cls, conn: sqlite3.Connection, expected_revision: int | None) -> int:
        """Atomically reject a stale mutation and advance the graph revision."""
        current = cls._revision_in(conn)
        if expected_revision is not None and expected_revision != current:
            raise GraphRevisionConflict(expected_revision, current)
        next_revision = current + 1
        conn.execute(
            "INSERT INTO project_meta (key, value) VALUES ('graph_revision', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(next_revision),),
        )
        return next_revision

    def graph_revision(self) -> int:
        """Return the monotonic revision for applied edit-graph mutations."""
        with self._conn() as conn:
            return self._revision_in(conn)

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
        command_id: str | None = None, expected_revision: int | None = None,
    ) -> int:
        """Append an operation. Returns the assigned sequence_num.

        Validates the op against the current project state (shape +
        references) before persisting. Raises OpValidationError on failure;
        the op is NOT written.
        """
        errors = _ir_validate.validate_op_for_append(op, self)
        if errors:
            raise _ir_validate.OpValidationError("; ".join(errors))
        with _APPEND_LOCK:
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
                self._check_and_bump_revision(conn, expected_revision)
                conn.execute(
                    "INSERT INTO edit_status_events "
                    "(event_id, edit_id, from_status, to_status, command_id, "
                    " reason, changed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id(), op.edit_id, None, op.status or "applied",
                        command_id, "append", op.timestamp or now_iso8601(),
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
        expected_revision: int | None = None,
    ) -> int:
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
                    command_id, reason, now_iso8601(),
                ),
            )
            return self._check_and_bump_revision(conn, expected_revision)

    def record_command(
        self, command_id: str, project_id: str, tool_name: str,
        status: str = "pending", payload_hash: str | None = None,
    ) -> None:
        """Record a command for idempotency. No-op if command_id exists."""
        self.commands.record_command(
            command_id, project_id, tool_name,
            status=status, payload_hash=payload_hash,
        )

    def command_exists(self, command_id: str) -> bool:
        """Return True if a command with the given id has been recorded."""
        return self.commands.command_exists(command_id)

    def finish_command(
        self, command_id: str, status: str = "done",
        result_json: str | None = None,
    ) -> None:
        """Mark a command as finished with a status and optional result."""
        self.commands.finish_command(
            command_id, status=status, result_json=result_json,
        )

    def get_command_result(self, command_id: str) -> str | None:
        """Return the stored result_json for a command, or None."""
        return self.commands.get_command_result(command_id)

    def get_command_status(self, command_id: str) -> str | None:
        """Return the stored status for a command, or None."""
        return self.commands.get_command_status(command_id)

    def save_timeline_snapshot(
        self, edit_graph_hash: str, project_id: str, timeline_json: str,
    ) -> None:
        """Store a derived timeline snapshot keyed by edit-graph hash."""
        self.snapshots.save_timeline_snapshot(
            edit_graph_hash, project_id, timeline_json,
        )

    def load_timeline_snapshot(self, edit_graph_hash: str) -> str | None:
        """Return the stored timeline_json for a hash, or None."""
        return self.snapshots.load_timeline_snapshot(edit_graph_hash)

    def set_edit_graph_hash(self, h: str) -> None:
        """Store the canonical edit-graph hash in project_meta."""
        self.set_project_meta_field("edit_graph_hash", h)

    def delete_op(self, edit_id: str, expected_revision: int | None = None) -> bool:
        """Remove an operation from the edit graph by id.

        Any ops that had ``parent_id == edit_id`` get their parent_id
        cleared (set to NULL) so the graph remains consistent.
        Returns True if an op was found and deleted.
        """
        return _ordering.delete_op(self, edit_id, expected_revision=expected_revision)

    def move_arbitrary(self, edit_id: str, new_sequence_num: int, expected_revision: int | None = None) -> bool:
        """Move an operation to any position in the sequence.

        This is a general reorder operation (not just adjacent swap).
        Returns True if the op was found and moved.
        """
        return _ordering.move_arbitrary(
            self, edit_id, new_sequence_num, expected_revision=expected_revision,
        )

    def reorder_all(self, edit_ids: list[str], expected_revision: int | None = None) -> int:
        """Atomically replace the complete edit ordering.

        Callers must supply every edit exactly once.  Validating the
        permutation before changing any sequence number prevents partial
        reorder state when a browser sends a duplicate, omits an operation,
        or contains an unknown id.
        """
        return _ordering.reorder_all(
            self, edit_ids, expected_revision=expected_revision,
        )

    def reorder(self, edit_id_a: str, edit_id_b: str, expected_revision: int | None = None) -> int:
        """Swap the sequence_num of two adjacent operations.

        Raises ValueError if either id does not exist or if the two ops
        are not adjacent in sequence_num.
        """
        return _ordering.reorder(
            self, edit_id_a, edit_id_b, expected_revision=expected_revision,
        )
