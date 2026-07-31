"""Timeline snapshot cache policy over an ``EditGraphStore``.

``derive_or_load_timeline`` returns a project's Timeline, using a cached
snapshot when the edit graph's canonical hash matches a stored one. The
store is duck-typed (any object with ``load_timeline_snapshot`` /
``save_timeline_snapshot``); any storage error degrades gracefully to a
fresh derive.

``TimelineSnapshotStore`` owns the ``timeline_snapshots`` table CRUD,
sharing the project's edit-graph db file and schema.
"""
from __future__ import annotations

import contextlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from open_edit.ir.derive import derive_timeline
from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.ids import now_iso8601
from open_edit.ir.types import Project, Timeline


class TimelineSnapshotStore:
    """SQLite store for derived timeline snapshots keyed by edit-graph hash."""

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

    def save_timeline_snapshot(
        self, edit_graph_hash: str, project_id: str, timeline_json: str,
    ) -> None:
        """Store a derived timeline snapshot keyed by edit-graph hash."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO timeline_snapshots "
                "(edit_graph_hash, project_id, timeline_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (edit_graph_hash, project_id, timeline_json, now_iso8601()),
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


def derive_or_load_timeline(project: Project, store=None, strict: bool = False) -> Timeline:
    """Return the Timeline for ``project``, using a cached snapshot when the
    edit graph's canonical hash matches a stored snapshot.

    If ``store`` (an EditGraphStore) is provided and a snapshot exists for the
    current ``compute_edit_graph_hash(project.edit_graph)``, deserialize and
    return it. Otherwise derive via ``derive_timeline``, and if ``store`` is
    given, persist the snapshot keyed by that hash. If ``store`` is None,
    always derive. Any storage error degrades gracefully to a fresh derive.
    """
    h = compute_edit_graph_hash(project.edit_graph)

    if store is not None:
        try:
            snap = store.load_timeline_snapshot(h)
            if snap is not None:
                return Timeline.model_validate_json(snap)
        except Exception:
            pass

    tl = derive_timeline(project, strict=strict)

    if store is not None:
        with contextlib.suppress(Exception):
            store.save_timeline_snapshot(h, project.project_id, tl.model_dump_json())

    return tl
