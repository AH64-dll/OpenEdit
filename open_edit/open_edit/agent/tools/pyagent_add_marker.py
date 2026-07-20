"""pyagent_add_marker: agent-initiated flag, writes to NotesStore with source=agent.

Per audit resolution: markers are notes, not IR ops. Restored from v1's drop.
"""
from __future__ import annotations

from open_edit.agent.tools._helpers import _db_path
from open_edit.storage.notes import (
    NoteSource,
    NotesStore,
    ReviewNote,
    TimestampAnchor,
)


def add_marker(args: dict, project_path: str) -> dict:
    """Append a ReviewNote with source=agent at the given timestamp."""
    db_path = _db_path(project_path).parent / "notes.db"
    store = NotesStore(db_path)
    note = ReviewNote(
        project_id=args["project_id"],
        anchor=TimestampAnchor(
            t_start=float(args["t_start"]),
            t_end=float(args.get("t_end", args["t_start"])),
        ),
        text=args.get("text", ""),
        source=NoteSource.agent,
    )
    store.append(note)
    return {"status": "ok", "note_id": note.note_id}
