"""Unified review_notes store.

Per phase4-design-revised.md §3.6 (T6): single source of truth for all
'the user or agent flagged this' annotations. Replaces v1's parallel
mark_region and correction_note systems with one store.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class NoteSource(str, Enum):
    typed = "typed"
    voice = "voice"
    region = "region"
    agent = "agent"
    form_correction = "form_correction"


class NoteStatus(str, Enum):
    pending = "pending"
    processed = "processed"
    dismissed = "dismissed"


class TimestampAnchor(BaseModel):
    anchor_type: Literal["timestamp"] = "timestamp"
    t_start: float
    t_end: float


class RegionAnchor(BaseModel):
    anchor_type: Literal["region"] = "region"
    x: float
    y: float
    w: float
    h: float
    t_start: float
    t_end: float


class OpAnchor(BaseModel):
    anchor_type: Literal["op"] = "op"
    op_id: str


NoteAnchor = Annotated[
    Union[TimestampAnchor, RegionAnchor, OpAnchor],
    Field(discriminator="anchor_type"),
]


def _new_id() -> str:
    return f"note_{uuid.uuid4().hex[:12]}"


class ReviewNote(BaseModel):
    note_id: str = Field(default_factory=_new_id)
    project_id: str
    anchor: NoteAnchor
    text: str = ""
    source: NoteSource
    status: NoteStatus = NoteStatus.pending
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    processed_at: Optional[str] = None
    commit_token: Optional[str] = None
    resulting_op_ids: list[str] = []


_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    note_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    anchor_type    TEXT NOT NULL CHECK (anchor_type IN ('timestamp', 'region', 'op')),
    anchor         TEXT NOT NULL,
    text           TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL CHECK (source IN ('typed', 'voice', 'region', 'agent', 'form_correction')),
    status         TEXT NOT NULL CHECK (status IN ('pending', 'processed', 'dismissed')),
    created_at     TEXT NOT NULL,
    processed_at   TEXT,
    commit_token   TEXT,
    resulting_op_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_notes_project_status ON notes(project_id, status);
CREATE INDEX IF NOT EXISTS idx_notes_commit_token ON notes(commit_token);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at);
"""


class NotesStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.executescript(_SCHEMA)

    def _row_to_note(self, row: sqlite3.Row) -> ReviewNote:
        anchor_type = row["anchor_type"]
        anchor_data = json.loads(row["anchor"])
        if anchor_type == "timestamp":
            anchor = TimestampAnchor(**anchor_data)
        elif anchor_type == "region":
            anchor = RegionAnchor(**anchor_data)
        else:
            anchor = OpAnchor(**anchor_data)
        return ReviewNote(
            note_id=row["note_id"],
            project_id=row["project_id"],
            anchor=anchor,
            text=row["text"],
            source=NoteSource(row["source"]),
            status=NoteStatus(row["status"]),
            created_at=row["created_at"],
            processed_at=row["processed_at"],
            commit_token=row["commit_token"],
            resulting_op_ids=json.loads(row["resulting_op_ids"] or "[]"),
        )

    def append(self, note: ReviewNote) -> str:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO notes (note_id, project_id, anchor_type, anchor, text, source, status, created_at, processed_at, commit_token, resulting_op_ids) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note.note_id,
                    note.project_id,
                    note.anchor.anchor_type,
                    note.anchor.model_dump_json(),
                    note.text,
                    note.source.value,
                    note.status.value,
                    note.created_at,
                    note.processed_at,
                    note.commit_token,
                    json.dumps(note.resulting_op_ids),
                ),
            )
        return note.note_id

    def list_all(self, project_id: str, status: Optional[NoteStatus] = None) -> list[ReviewNote]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            if status is None:
                rows = con.execute(
                    "SELECT * FROM notes WHERE project_id = ? ORDER BY created_at",
                    (project_id,),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM notes WHERE project_id = ? AND status = ? ORDER BY created_at",
                    (project_id, status.value),
                ).fetchall()
        return [self._row_to_note(r) for r in rows]

    def list_pending(self, project_id: str) -> list[ReviewNote]:
        return self.list_all(project_id, status=NoteStatus.pending)

    def commit_pending(self, project_id: str, commit_token: str) -> list[ReviewNote]:
        """Per audit H1: stamp commit_token on all pending notes; return them.

        Does NOT mark them processed. The agent run uses the returned list
        to build pending_feedback; mark_processed is called after agent run.
        """
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE notes SET commit_token = ? WHERE project_id = ? AND status = 'pending'",
                (commit_token, project_id),
            )
        return self.list_pending(project_id)

    def mark_processed(self, note_ids: list[str], resulting_op_ids: list[str]) -> None:
        with sqlite3.connect(self.db_path) as con:
            for note_id, op_id in zip(note_ids, resulting_op_ids):
                con.execute(
                    "UPDATE notes SET status = 'processed', processed_at = ?, resulting_op_ids = ? "
                    "WHERE note_id = ?",
                    (datetime.now(timezone.utc).isoformat(), json.dumps([op_id]), note_id),
                )

    def mark_dismissed(self, note_ids: list[str]) -> None:
        with sqlite3.connect(self.db_path) as con:
            for note_id in note_ids:
                con.execute(
                    "UPDATE notes SET status = 'dismissed' WHERE note_id = ?",
                    (note_id,),
                )
