"""Phase 4 Task 8: notes DB archival on commit_feedback completion."""
import pytest
from datetime import datetime, timezone, timedelta
from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, NoteSource, NoteStatus,
)


def _make_processed_note(text: str, age_days: int) -> ReviewNote:
    return ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text=text,
        source=NoteSource.typed,
        status=NoteStatus.processed,
        created_at=(datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )


def test_archive_old_processed(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    # 5 notes: 2 recent (kept), 3 old (archived)
    for i in range(2):
        store.append(_make_processed_note(f"recent {i}", age_days=5))
    for i in range(3):
        store.append(_make_processed_note(f"old {i}", age_days=45))
    archived = store.archive_old_processed(retention_days=30)
    assert archived == 3
    # Recent notes still in main table
    remaining = store.list_all("p1")
    assert len(remaining) == 2
    assert all("recent" in n.text for n in remaining)
    # Archived notes in archive table
    import sqlite3
    with sqlite3.connect(store.db_path) as con:
        rows = con.execute("SELECT text FROM notes_archive").fetchall()
    assert len(rows) == 3
    assert all("old" in r[0] for r in rows)


def test_pending_never_archived(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    # A pending note that's old should not be archived
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="pending old note",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=(datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
    )
    store.append(note)
    archived = store.archive_old_processed(retention_days=30)
    assert archived == 0
    pending = store.list_pending("p1")
    assert len(pending) == 1
