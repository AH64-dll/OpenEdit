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


def test_update_text_and_status(tmp_path):
    """I1: NotesStore.update supports `text` and `status` with Pydantic validation."""
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="original",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    note_id = store.append(note)

    store.update(note_id, text="edited")
    after_text = store.list_all("p1")[0]
    assert after_text.text == "edited"
    assert after_text.status == NoteStatus.pending

    store.update(note_id, status=NoteStatus.dismissed)
    after_status = store.list_all("p1")[0]
    assert after_status.status == NoteStatus.dismissed
    assert after_status.text == "edited"


def test_update_rejects_unknown_field(tmp_path):
    """I1: NotesStore.update rejects fields outside the allowed Pydantic set."""
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="t",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    note_id = store.append(note)
    with pytest.raises(Exception):
        store.update(note_id, project_id="p2")  # not an allowed field


def test_update_unknown_note_id_is_noop(tmp_path):
    """I1: update on a missing note_id does not raise and changes nothing."""
    store = NotesStore(tmp_path / "notes.db")
    store.update("note_does_not_exist", text="orphan")


def test_commit_pending_race_safety(tmp_path):
    """Per audit H1: parallel commit_pending calls must not double-stamp rows.

    Two callers that race commit_pending with different tokens must see
    disjoint sets of notes: the first gets all N pending, the second gets 0
    (since every row already has commit_token != NULL). Adding a fresh note
    after the first call must surface in the second call's result.
    """
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
    first = store.commit_pending("p1", "token_a")
    second = store.commit_pending("p1", "token_b")
    assert len(first) == 3
    assert {n.commit_token for n in first} == {"token_a"}
    assert second == [], (
        "second commit_pending must not re-stamp rows already stamped; "
        f"got {len(second)} notes: {[n.commit_token for n in second]}"
    )
    # New note added after the first commit should be visible to the next caller.
    store.append(ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=99.0, t_end=100.0),
        text="post-commit note",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    third = store.commit_pending("p1", "token_c")
    assert len(third) == 1
    assert third[0].commit_token == "token_c"
    assert third[0].text == "post-commit note"


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


def test_clear_commit_token_resets_to_null(tmp_path):
    """Per fix I2: clear_commit_token resets commit_token to NULL on the
    given notes. Used by commit_feedback when the agent run fails — the
    T2 commit_pending filter `AND commit_token IS NULL` would otherwise
    leave claimed-but-unprocessed notes un-claimable on the next click
    (silent data loss)."""
    store = NotesStore(tmp_path / "notes.db")
    n1 = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="note 1",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    n2 = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=1.0, t_end=2.0),
        text="note 2",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(n1)
    store.append(n2)
    store.commit_pending("p1", "token_abc")

    # Before clear: both stamped.
    notes = store.list_all("p1")
    assert all(n.commit_token == "token_abc" for n in notes)

    # Clear only n1.
    store.clear_commit_token([n1.note_id])
    notes = store.list_all("p1")
    by_id = {n.note_id: n for n in notes}
    assert by_id[n1.note_id].commit_token is None
    assert by_id[n2.note_id].commit_token == "token_abc"

    # n1 re-claimable; n2 still stamped (still un-claimable).
    re_claimed = store.commit_pending("p1", "token_retry")
    assert len(re_claimed) == 1
    assert re_claimed[0].note_id == n1.note_id


def test_clear_commit_token_empty_list_is_noop(tmp_path):
    """clear_commit_token on an empty list is a no-op (no DB call needed)."""
    store = NotesStore(tmp_path / "notes.db")
    n = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(n)
    store.commit_pending("p1", "token_x")
    # No exception raised.
    store.clear_commit_token([])
    notes = store.list_all("p1")
    assert notes[0].commit_token == "token_x"
