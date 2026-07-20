"""Phase 4 Task 2: unified notes store."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, RegionAnchor, OpAnchor,
    NoteSource, NoteStatus,
)


def test_append_timestamp_note(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=1.0, t_end=2.0),
        text="feels empty",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    note_id = store.append(note)
    assert note_id == note.note_id
    notes = store.list_all("p1")
    assert len(notes) == 1
    assert notes[0].note_id == note_id
    assert notes[0].anchor.t_start == 1.0


def test_append_region_note(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=RegionAnchor(x=10, y=20, w=100, h=50, t_start=0.5, t_end=1.5),
        text="television overlay",
        source=NoteSource.region,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(note)
    notes = store.list_all("p1")
    assert isinstance(notes[0].anchor, RegionAnchor)
    assert notes[0].anchor.x == 10


def test_append_op_note(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=OpAnchor(op_id="op_42"),
        text="trim 1s off the front",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(note)
    notes = store.list_all("p1")
    assert isinstance(notes[0].anchor, OpAnchor)
    assert notes[0].anchor.op_id == "op_42"


def test_list_pending_filters_correctly(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    for i, status in enumerate([NoteStatus.pending, NoteStatus.processed, NoteStatus.pending]):
        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=float(i), t_end=float(i) + 0.5),
            text=f"note {i}",
            source=NoteSource.typed,
            status=status,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
    pending = store.list_pending("p1")
    assert len(pending) == 2
    assert all(n.status == NoteStatus.pending for n in pending)


def test_commit_pending_marks_with_token(tmp_path):
    """Per audit H1: commit_pending returns notes + stamps commit_token."""
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=float(i), t_end=float(i) + 0.5),
            text=f"note {i}",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
    token = "commit_abc"
    notes = store.commit_pending("p1", token)
    assert len(notes) == 3
    assert all(n.commit_token == token for n in notes)
    # Notes not marked processed yet — only stamped with token.
    pending_after = store.list_pending("p1")
    assert len(pending_after) == 3


def test_mark_processed_only_token_matching(tmp_path):
    """Per audit H1: mark_processed only affects notes with the given token."""
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=float(i), t_end=float(i) + 0.5),
            text=f"note {i}",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
    token = "commit_abc"
    committed = store.commit_pending("p1", token)
    committed_ids = [n.note_id for n in committed]
    # Add a note AFTER commit_pending but BEFORE mark_processed.
    store.append(ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=10.0, t_end=11.0),
        text="note added after commit",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    store.mark_processed(committed_ids, resulting_op_ids=["op_1", "op_2", "op_3"])
    # 3 should be processed, 1 should still be pending.
    pending = store.list_pending("p1")
    assert len(pending) == 1
    assert pending[0].text == "note added after commit"


def test_note_dismissed_is_soft_delete(tmp_path):
    """Per design §3.6: note_delete marks status=dismissed, never hard-deletes."""
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    note_id = store.append(note)
    store.mark_dismissed([note_id])
    all_notes = store.list_all("p1", status=None)
    assert len(all_notes) == 1
    assert all_notes[0].status == NoteStatus.dismissed


def test_project_isolation(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    store.append(ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    store.append(ReviewNote(
        project_id="p2",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    assert len(store.list_all("p1")) == 1
    assert len(store.list_all("p2")) == 1
