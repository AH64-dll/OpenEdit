"""In-flight job lock backed by the SQLite jobs table.

A single lock for all kinds (free_form_python, render, migration). Only
one job runs at a time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from open_edit.storage.edit_graph import EditGraphStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobLock:
    """Single-slot lock for sandbox runs, renders, and migrations."""

    def __init__(self, edit_graph: EditGraphStore):
        self.edit_graph = edit_graph

    def try_acquire(self, kind: str) -> Optional[str]:
        with self.edit_graph._conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'running'"
            )
            if cur.fetchone()[0] > 0:
                return None
            job_id = str(uuid.uuid4())
            try:
                conn.execute(
                    "INSERT INTO jobs (job_id, kind, status, started_at) "
                    "VALUES (?, ?, 'running', ?)",
                    (job_id, kind, _now_iso()),
                )
                return job_id
            except Exception:
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
