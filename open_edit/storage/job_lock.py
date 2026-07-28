"""In-flight job lock backed by the SQLite jobs table.

A single lock for all kinds (free_form_python, render, migration). Only
one job runs at a time. Uses a partial unique index for atomic acquire.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from open_edit.storage.edit_graph import EditGraphStore

STALE_LOCK_TIMEOUT_SEC = 3600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobLock:
    """Single-slot lock for sandbox runs, renders, and migrations."""

    def __init__(self, edit_graph: EditGraphStore):
        self.edit_graph = edit_graph
        _ensure_schema(self.edit_graph)

    def try_acquire(self, kind: str) -> Optional[str]:
        _release_stale_locks(self.edit_graph)
        with self.edit_graph._conn() as conn:
            job_id = str(uuid.uuid4())
            try:
                conn.execute(
                    "INSERT INTO jobs (job_id, kind, status, started_at) "
                    "VALUES (?, ?, 'running', ?)",
                    (job_id, kind, _now_iso()),
                )
                return job_id
            except sqlite3.IntegrityError:
                return None

    def release(
        self, job_id: str, status: str, error: str | None = None
    ) -> None:
        with self.edit_graph._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, error = ? "
                "WHERE job_id = ?",
                (status, _now_iso(), error, job_id),
            )

    def list_running(self) -> list[dict]:
        with self.edit_graph._conn() as conn:
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


def _ensure_schema(edit_graph: EditGraphStore) -> None:
    """Add partial unique index for atomic lock acquire (additive migration)."""
    with edit_graph._conn() as conn:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_running "
            "ON jobs(status) WHERE status = 'running'"
        )


def _release_stale_locks(edit_graph: EditGraphStore) -> None:
    """Release locks older than STALE_LOCK_TIMEOUT_SEC."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_LOCK_TIMEOUT_SEC)
    cutoff_iso = cutoff.isoformat()
    with edit_graph._conn() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', finished_at = ?, error = 'stale' "
            "WHERE status = 'running' AND started_at < ?",
            (_now_iso(), cutoff_iso),
        )
