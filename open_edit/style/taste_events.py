"""Taste events for the Style Memory system (Phase 4).

Phase 4 reads these, aggregates into a bounded style profile, and
injects a tag-gated slice into each agent turn.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal, Optional

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TasteEvent(BaseModel):
    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=_now_iso)
    project_id: Optional[str] = None
    op_type: str
    proposed_params: dict = Field(default_factory=dict)
    final_params: dict = Field(default_factory=dict)
    action: Literal["applied_unmodified", "applied_modified", "reverted"]
    correction_note: Optional[str] = None
    weight: int = 0


SCHEMA = """
CREATE TABLE IF NOT EXISTS taste_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    project_id TEXT,
    op_type TEXT NOT NULL,
    proposed_params TEXT NOT NULL,
    final_params TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('applied_unmodified', 'applied_modified', 'reverted')),
    correction_note TEXT,
    weight INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_taste_events_ts ON taste_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_taste_events_project ON taste_events(project_id);
"""


class TasteEventStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def append(self, event: TasteEvent) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO taste_events "
                "(id, timestamp, project_id, op_type, proposed_params, "
                " final_params, action, correction_note, weight) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id, event.timestamp, event.project_id, event.op_type,
                    json.dumps(event.proposed_params, sort_keys=True, separators=(",", ":")),
                    json.dumps(event.final_params, sort_keys=True, separators=(",", ":")),
                    event.action, event.correction_note, event.weight,
                ),
            )

    def pull(
        self,
        project_id: Optional[str] = None,
        window_days: int = 90,
        max_events: int = 200,
    ) -> list[TasteEvent]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        with self._conn() as conn:
            if project_id is None:
                cur = conn.execute(
                    "SELECT id, timestamp, project_id, op_type, proposed_params, "
                    "final_params, action, correction_note, weight "
                    "FROM taste_events WHERE timestamp >= ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (cutoff, max_events),
                )
            else:
                cur = conn.execute(
                    "SELECT id, timestamp, project_id, op_type, proposed_params, "
                    "final_params, action, correction_note, weight "
                    "FROM taste_events WHERE project_id = ? AND timestamp >= ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (project_id, cutoff, max_events),
                )
            return [
                TasteEvent(
                    id=row[0], timestamp=row[1], project_id=row[2], op_type=row[3],
                    proposed_params=json.loads(row[4]),
                    final_params=json.loads(row[5]),
                    action=row[6], correction_note=row[7], weight=row[8],
                )
                for row in cur.fetchall()
            ]

    def purge(
        self,
        ids: list[str] | None = None,
        project_id: Optional[str] = None,
    ) -> None:
        with self._conn() as conn:
            if ids:
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"DELETE FROM taste_events WHERE id IN ({placeholders})",
                    ids,
                )
            elif project_id is not None:
                conn.execute(
                    "DELETE FROM taste_events WHERE project_id = ?",
                    (project_id,),
                )
