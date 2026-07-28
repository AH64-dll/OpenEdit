"""pyagent_add_marker: agent-initiated flag, writes to NotesStore with source=agent.

Per audit resolution: markers are notes, not IR ops. Restored from v1's drop.
"""
from __future__ import annotations

from open_edit.agent.tools._helpers import _notes_db_path
from open_edit.storage.notes import (
    NoteSource,
    NotesStore,
    ReviewNote,
    TimestampAnchor,
)


def add_marker(args: dict, project_path: str) -> dict:
    """Append a ReviewNote with source=agent at the given timestamp."""
    try:
        db_path = _notes_db_path(project_path)
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
    except Exception as e:
        return {"status": "error", "error": str(e)}
