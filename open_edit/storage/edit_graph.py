"""SQLite-backed edit graph store.

One .db file per project. WAL mode for concurrent reads. Stores every
operation ever applied (including reverted/superseded). The durable
record; the source of truth for the IR.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from open_edit.ir import validate as _ir_validate
from open_edit.ir.ids import now_iso8601
from open_edit.ir.types import OperationUnion, new_id
from open_edit.storage import history as _history
from open_edit.storage import ordering as _ordering
from open_edit.storage.commands import CommandStore
from open_edit.storage.db import open_conn
from open_edit.storage.timeline_cache import TimelineSnapshotStore

_APPEND_LOCK = threading.Lock()


class GraphRevisionConflict(RuntimeError):  # noqa: N818 - public compatibility name
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

    def read_snapshot(self) -> tuple[int, list[OperationUnion]]:
        """Read a revision and its operations from one SQLite snapshot."""
        with self._conn() as conn:
            conn.execute("BEGIN")
            revision = self._revision_in(conn)
            return revision, self._load_all_in(conn)

    def load_authoring_source(self, format: str, revision: int) -> str | None:
        """Read a derived view for an exact snapshot, never for another revision."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT source FROM authoring_views WHERE format = ? AND graph_revision = ?",
                (format, revision),
            ).fetchone()
            return row[0] if row else None

    @staticmethod
    def _save_authoring_source(conn: sqlite3.Connection, view: tuple[str, str] | None) -> None:
        if view is None:
            return
        format, source = view
        revision = EditGraphStore._revision_in(conn)
        conn.execute(
            "INSERT OR REPLACE INTO authoring_views (format, graph_revision, source) VALUES (?, ?, ?)",
            (format, revision, source),
        )
        # Retain a bounded last-good history without growing the operation log.
        conn.execute(
            "DELETE FROM authoring_views WHERE format = ? AND graph_revision NOT IN "
            "(SELECT graph_revision FROM authoring_views WHERE format = ? "
            "ORDER BY graph_revision DESC LIMIT 8)",
            (format, format),
        )

    @property
    def project_id(self) -> str:
        """Return the stable project ID, safely creating it on first access."""
        with self._conn() as conn:
            return self._project_id_in(conn)

    @staticmethod
    def _project_id_in(conn: sqlite3.Connection) -> str:
        row = conn.execute(
            "SELECT value FROM project_meta WHERE key = 'project_id'"
        ).fetchone()
        if row is not None:
            return row[0]
        conn.execute(
            "INSERT OR IGNORE INTO project_meta (key, value) VALUES ('project_id', ?)",
            (new_id(),),
        )
        return conn.execute(
            "SELECT value FROM project_meta WHERE key = 'project_id'"
        ).fetchone()[0]

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
        raw = value if isinstance(value, str) else json.dumps(value)
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
        """Validate and atomically append one operation."""
        return self.append_many(
            [op], command_id=command_id, expected_revision=expected_revision,
            sequence_num=sequence_num,
        )[0]

    def append_many(
        self, ops: list[OperationUnion], *, command_id: str | None = None,
        expected_revision: int | None = None, sequence_num: int | None = None,
        authoring_view: tuple[str, str] | None = None,
        action_label: str | None = None,
    ) -> list[int]:
        """Append a batch in one transaction, or leave the graph unchanged.

        Reference validation uses the same locked SQLite snapshot as the
        inserts, including earlier operations in this batch. This prevents a
        failed late operation or concurrent removal from leaving partial edits.
        """
        from types import SimpleNamespace

        project_id = self.project_id
        sequences: list[int] = []
        with _APPEND_LOCK, self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_revision = self._revision_in(conn)
            if expected_revision is not None and current_revision != expected_revision:
                raise GraphRevisionConflict(expected_revision, current_revision)
            if not ops:
                self._save_authoring_source(conn, authoring_view)
                return []
            current_ops = self._load_all_in(conn)
            view = SimpleNamespace(
                db_path=self.db_path, project_id=project_id,
                load_all=lambda: current_ops,
            )
            next_sequence = sequence_num
            if next_sequence is None:
                next_sequence = conn.execute(
                    "SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits"
                ).fetchone()[0]
            for op in ops:
                errors = _ir_validate.validate_op_for_append(op, view)
                if errors:
                    raise _ir_validate.OpValidationError("; ".join(errors))
                conn.execute(
                    "INSERT INTO edits "
                    "(edit_id, parent_id, kind, author, timestamp, status, "
                    " sequence_num, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (op.edit_id, op.parent_id, op.kind, op.author, op.timestamp,
                     op.status, next_sequence, op.model_dump_json()),
                )
                self._check_and_bump_revision(conn, None)
                conn.execute(
                    "INSERT INTO edit_status_events "
                    "(event_id, edit_id, from_status, to_status, command_id, "
                    " reason, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (new_id(), op.edit_id, None, op.status or "applied",
                     command_id, "append", op.timestamp or now_iso8601()),
                )
                current_ops.append(op)
                sequences.append(next_sequence)
                next_sequence += 1
            self._save_authoring_source(conn, authoring_view)
            _history.record(conn, ops, action_label, current_revision)
        return sequences

    def history(self) -> dict:
        with self._conn() as conn:
            conn.execute('BEGIN')
            return {'graph_revision': self._revision_in(conn), **_history.summary(conn)}

    def history_step(self, direction: str, expected_revision: int) -> dict:
        return _history.step(self, direction, expected_revision)

    @staticmethod
    def _load_all_in(conn: sqlite3.Connection) -> list[OperationUnion]:
        rows = conn.execute(
            "SELECT payload, status, parent_id, sequence_num FROM edits ORDER BY sequence_num"
        )
        adapter = TypeAdapter(OperationUnion)
        ops: list[OperationUnion] = []
        for row in rows:
            op = adapter.validate_json(row[0])
            op.status = row[1]
            op.parent_id = row[2]
            object.__setattr__(op, "sequence_num", row[3])
            ops.append(op)
        return ops

    def load_all(self) -> list[OperationUnion]:
        """Load all operations in sequence_num order.

        Each op carries its ``sequence_num`` as an attribute so the
        edit-graph hash can be order-sensitive (Task 6.5). The attribute is
        intentionally not a pydantic field: it stays out of ``model_dump``
        serializations (API payloads, stored op JSON).
        """
        with self._conn() as conn:
            return self._load_all_in(conn)

    def update_status(
        self, edit_id: str, new_status: str,
        command_id: str | None = None, reason: str | None = None,
        expected_revision: int | None = None,
    ) -> int:
        """Update an operation's status (e.g. for undo/revert or supersede)."""
        if new_status not in ("applied", "reverted", "superseded"):
            raise ValueError(f"invalid operation status: {new_status!r}")
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "SELECT status FROM edits WHERE edit_id = ?", (edit_id,)
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"operation not found: {edit_id}")
            from_status = row[0]
            _history.invalidate(conn)
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
