"""RenderSnapshotStore for version-switchable render history.

Per phase4-design-revised.md §3.4 (T4).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class RenderStatus(str, Enum):
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


def _new_version_id() -> str:
    return f"v_{uuid.uuid4().hex[:12]}"


class RenderSnapshot(BaseModel):
    version_id: str = Field(default_factory=_new_version_id)
    project_id: str
    edit_graph_hash: str
    render_path: Path
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: RenderStatus = RenderStatus.rendering
    label: str = ""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS render_snapshots (
    version_id      TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    edit_graph_hash TEXT NOT NULL,
    render_path     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('rendering', 'ready', 'failed')),
    label           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_snapshots_project_created ON render_snapshots(project_id, created_at);
"""


class RenderSnapshotStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.executescript(_SCHEMA)

    def append(self, snapshot: RenderSnapshot) -> str:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO render_snapshots (version_id, project_id, edit_graph_hash, render_path, created_at, status, label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot.version_id, snapshot.project_id, snapshot.edit_graph_hash,
                    str(snapshot.render_path), snapshot.created_at, snapshot.status.value, snapshot.label,
                ),
            )
        return snapshot.version_id

    def list_for_project(self, project_id: str) -> list[RenderSnapshot]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM render_snapshots WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return [
            RenderSnapshot(
                version_id=r["version_id"],
                project_id=r["project_id"],
                edit_graph_hash=r["edit_graph_hash"],
                render_path=Path(r["render_path"]),
                created_at=r["created_at"],
                status=RenderStatus(r["status"]),
                label=r["label"],
            )
            for r in rows
        ]

    def latest_ready(self, project_id: str) -> Optional[RenderSnapshot]:
        snaps = self.list_for_project(project_id)
        ready = [s for s in snaps if s.status == RenderStatus.ready]
        return ready[-1] if ready else None

    def latest_for_project(self, project_id: str) -> Optional[RenderSnapshot]:
        """Return the most recent snapshot for the project, regardless of status.

        Used by the chat UI's `commit_feedback` handler to broadcast
        ``version_ready`` for any new snapshot (per fix M3) — the UI
        needs to see failed renders too (audit H2: failed entries should
        be visible). ``list_for_project`` returns rows ordered by
        ``created_at``, so the last entry is the newest.
        """
        snaps = self.list_for_project(project_id)
        return snaps[-1] if snaps else None

    def update_status(self, version_id: str, status: RenderStatus) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE render_snapshots SET status = ? WHERE version_id = ?",
                (status.value, version_id),
            )

    def evict_oldest_ready(self, max_versions: int) -> None:
        """Per audit M1: evict oldest status=ready; never evict rendering/failed."""
        with sqlite3.connect(self.db_path) as con:
            ready_snaps = con.execute(
                "SELECT version_id FROM render_snapshots WHERE status = 'ready' ORDER BY created_at"
            ).fetchall()
            if len(ready_snaps) <= max_versions:
                return
            to_evict = ready_snaps[:len(ready_snaps) - max_versions]
            for (vid,) in to_evict:
                con.execute("DELETE FROM render_snapshots WHERE version_id = ?", (vid,))
