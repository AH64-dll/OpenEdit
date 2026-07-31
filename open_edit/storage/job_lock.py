"""In-flight job lock backed by the SQLite jobs table.

A single lock for all kinds (free_form_python, render, migration). Only
one job runs at a time. Uses a partial unique index for atomic acquire.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from open_edit.ir.ids import now_iso8601
from open_edit.storage.db import open_conn

if TYPE_CHECKING:
    from open_edit.storage.edit_graph import EditGraphStore

STALE_LOCK_TIMEOUT_SEC = 3600


class JobLock:
    """Single-slot lock for sandbox runs, renders, and migrations."""

    def __init__(self, edit_graph: EditGraphStore):
        self.db_path = edit_graph.db_path
        with open_conn(self.db_path) as conn:
            from open_edit.storage.migrations import ensure_schema

            ensure_schema(conn)

    def try_acquire(self, kind: str) -> Optional[str]:
        _release_stale_locks(self.db_path)
        with open_conn(self.db_path) as conn:
            job_id = str(uuid.uuid4())
            try:
                conn.execute(
                    "INSERT INTO jobs (job_id, kind, status, started_at) "
                    "VALUES (?, ?, 'running', ?)",
                    (job_id, kind, now_iso8601()),
                )
                return job_id
            except sqlite3.IntegrityError:
                return None

    def release(
        self, job_id: str, status: str, error: str | None = None
    ) -> None:
        with open_conn(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, error = ? "
                "WHERE job_id = ?",
                (status, now_iso8601(), error, job_id),
            )

    def list_running(self) -> list[dict]:
        with open_conn(self.db_path) as conn:
            cur = conn.execute(
                "SELECT job_id, kind, status, started_at, finished_at, error "
                "FROM jobs WHERE status = 'running'"
            )
            return [
                {
                    "job_id": row[0], "kind": row[1], "status": row[2],
                    "started_at": row[3], "finished_at": row[4], "error": row[5],
                }
                for row in cur.fetchall()
            ]


def _release_stale_locks(db_path: str | Path) -> None:
    """Release locks older than STALE_LOCK_TIMEOUT_SEC."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_LOCK_TIMEOUT_SEC)
    cutoff_iso = cutoff.isoformat()
    with open_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', finished_at = ?, error = 'stale' "
            "WHERE status = 'running' AND started_at < ?",
            (now_iso8601(), cutoff_iso),
        )
