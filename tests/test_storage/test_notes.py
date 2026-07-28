"""Phase 4 Task 2: unified notes store."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, RegionAnchor, OpAnchor,
    NoteSource, NoteStatus,
)


class TestNotesStore(unittest.TestCase):
    """Unit tests for NotesStore."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_append_timestamp_note(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
        note = ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=1.0, t_end=2.0),
            text="feels empty",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        note_id = store.append(note)
        self.assertEqual(note_id, note.note_id)
        notes = store.list_all("p1")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].note_id, note_id)
        self.assertEqual(notes[0].anchor.t_start, 1.0)

    def test_append_region_note(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertIsInstance(notes[0].anchor, RegionAnchor)
        self.assertEqual(notes[0].anchor.x, 10)

    def test_append_op_note(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertIsInstance(notes[0].anchor, OpAnchor)
        self.assertEqual(notes[0].anchor.op_id, "op_42")

    def test_list_pending_filters_correctly(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertEqual(len(pending), 2)
        self.assertTrue(all(n.status == NoteStatus.pending for n in pending))

    def test_commit_pending_marks_with_token(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertEqual(len(notes), 3)
        self.assertTrue(all(n.commit_token == token for n in notes))
        pending_after = store.list_pending("p1")
        self.assertEqual(len(pending_after), 3)

    def test_mark_processed_only_token_matching(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=10.0, t_end=11.0),
            text="note added after commit",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
        store.mark_processed(committed_ids, resulting_op_ids=["op_1", "op_2", "op_3"])
        pending = store.list_pending("p1")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].text, "note added after commit")

    def test_note_dismissed_is_soft_delete(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertEqual(len(all_notes), 1)
        self.assertEqual(all_notes[0].status, NoteStatus.dismissed)

    def test_update_text_and_status(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertEqual(after_text.text, "edited")
        self.assertEqual(after_text.status, NoteStatus.pending)

        store.update(note_id, status=NoteStatus.dismissed)
        after_status = store.list_all("p1")[0]
        self.assertEqual(after_status.status, NoteStatus.dismissed)
        self.assertEqual(after_status.text, "edited")

    def test_update_rejects_unknown_field(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
        note = ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
            text="t",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        note_id = store.append(note)
        with self.assertRaises(Exception):
            store.update(note_id, project_id="p2")

    def test_update_unknown_note_id_is_noop(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
        store.update("note_does_not_exist", text="orphan")

    def test_commit_pending_race_safety(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertEqual(len(first), 3)
        self.assertEqual({n.commit_token for n in first}, {"token_a"})
        self.assertEqual(second, [])

        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=99.0, t_end=100.0),
            text="post-commit note",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
        third = store.commit_pending("p1", "token_c")
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0].commit_token, "token_c")
        self.assertEqual(third[0].text, "post-commit note")

    def test_project_isolation(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        self.assertEqual(len(store.list_all("p1")), 1)

    def test_clear_commit_token_resets_to_null(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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

        notes = store.list_all("p1")
        self.assertTrue(all(n.commit_token == "token_abc" for n in notes))

        store.clear_commit_token([n1.note_id])
        notes = store.list_all("p1")
        by_id = {n.note_id: n for n in notes}
        self.assertIsNone(by_id[n1.note_id].commit_token)
        self.assertEqual(by_id[n2.note_id].commit_token, "token_abc")

        re_claimed = store.commit_pending("p1", "token_retry")
        self.assertEqual(len(re_claimed), 1)
        self.assertEqual(re_claimed[0].note_id, n1.note_id)

    def test_clear_commit_token_empty_list_is_noop(self) -> None:
        store = NotesStore(self.tmp_path / "notes.db")
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
        store.clear_commit_token([])
        notes = store.list_all("p1")
        self.assertEqual(notes[0].commit_token, "token_x")


if __name__ == "__main__":
    unittest.main()
