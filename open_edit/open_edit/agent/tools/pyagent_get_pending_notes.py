"""pyagent_get_pending_notes: returns pending notes for the project.

Per audit H3: supports summary_only parameter for token budget.
The first 10 are returned in full; the rest are summarized as a count.
"""
from __future__ import annotations


from open_edit.agent.tools._helpers import _notes_db_path
from open_edit.storage.notes import NotesStore


def get_pending_notes(args: dict, project_path: str) -> dict:
    """List pending notes. Default: first 10 full + count of rest."""
    db_path = _notes_db_path(project_path)
    store = NotesStore(db_path)
    pending = store.list_pending(args["project_id"])
    if args.get("summary_only", False):
        return {
            "notes": [
                {
                    "note_id": n.note_id,
                    "anchor": n.anchor.model_dump(),
                    "text_preview": n.text[:80],
                }
                for n in pending
            ],
        }
    return {
        "notes": [n.model_dump(mode="json") for n in pending[:10]],
        "remaining_count": max(0, len(pending) - 10),
    }
