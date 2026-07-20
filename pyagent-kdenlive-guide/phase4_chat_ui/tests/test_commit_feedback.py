"""Phase 4 Task 6: commit_feedback batch trigger.

These tests pin the NotesStore contract the commit_feedback handler relies on:
- commit_pending returns the stamped notes
- commit_pending with zero notes returns an empty list
- mark_processed transitions notes to status=processed

The handler itself is wired in `ws/handlers.py`; these tests document the
storage contract that handler flow depends on (TDD-style pin against the
T6 NotesStore that already implements it).
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, NoteSource, NoteStatus,
)


def _make_note(project_id: str, text: str = "test", age_seconds: int = 0) -> ReviewNote:
    return ReviewNote(
        project_id=project_id,
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text=text,
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=(datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat(),
    )


def test_commit_feedback_assembles_pending_notes(tmp_path):
    """commit_pending returns all pending notes for the project and stamps
    each one with the supplied commit_token. The handler uses this list to
    build the `pending_feedback` block sent to the agent."""
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(_make_note("p1", text=f"note {i}"))
    notes = store.commit_pending("p1", "token_abc")
    assert len(notes) == 3
    assert all(n.commit_token == "token_abc" for n in notes)


def test_commit_feedback_zero_notes(tmp_path):
    """When there are no pending notes, commit_pending returns an empty list.
    The handler surfaces this as `error: no pending notes to commit`."""
    store = NotesStore(tmp_path / "notes.db")
    notes = store.commit_pending("p1", "token_abc")
    assert len(notes) == 0


def test_commit_feedback_marks_processed(tmp_path):
    """After the agent run, the handler calls mark_processed with the note
    ids and the resulting op ids. This transitions the notes out of `pending`
    so they are not re-sent on the next commit."""
    store = NotesStore(tmp_path / "notes.db")
    note_ids = []
    for i in range(3):
        n = _make_note("p1", text=f"note {i}")
        store.append(n)
        note_ids.append(n.note_id)
    store.commit_pending("p1", "token_abc")
    store.mark_processed(note_ids, resulting_op_ids=[f"op_{i}" for i in range(3)])
    pending = store.list_pending("p1")
    assert len(pending) == 0


def test_commit_feedback_handler_returns_error_when_no_notes(tmp_path):
    """The handler must short-circuit with an error message when there are
    no pending notes — the user clicked Send with nothing to send."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers

    # Isolate the notes db to tmp_path (default uses the home dir).
    db_path = tmp_path / "notes.db"

    def fake_db_path(project_id: str) -> Path:
        return db_path

    original = ws_module.handlers.get_notes_db_path
    ws_module.handlers.get_notes_db_path = fake_db_path
    try:
        async def run() -> None:
            ws = AsyncMock()
            broadcast = AsyncMock()
            await ws_handlers.handle_commit_feedback(
                handler=MagicMock(),
                ws=ws,
                project_id="p1",
                msg={"creativity_level": "balanced"},
                broadcast=broadcast,
            )
            ws.send_json.assert_awaited_once()
            sent = ws.send_json.await_args.args[0]
            assert sent["type"] == "error"
            assert "no pending notes" in sent["message"]
            broadcast.assert_not_awaited()
        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original


def test_commit_feedback_handler_broadcasts_version_ready(tmp_path, monkeypatch):
    """After a successful agent run + render, the handler must broadcast
    `version_ready` to the project's sockets so the UI re-requests the
    version list (per T5 Important #1)."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers

    db_path = tmp_path / "notes.db"
    snapshots_db = tmp_path / "snapshots.db"

    def fake_db_path(project_id: str) -> Path:
        return db_path

    def fake_snapshots_db_path(project_id: str) -> Path:
        return snapshots_db

    original_db = ws_module.handlers.get_notes_db_path
    original_snap = ws_module.handlers.get_snapshots_db_path
    ws_module.handlers.get_notes_db_path = fake_db_path
    ws_module.handlers.get_snapshots_db_path = fake_snapshots_db_path
    try:
        async def run() -> None:
            # Seed a pending note
            store = NotesStore(db_path)
            store.append(_make_note("p1", text="hello"))

            # Mock the agent client so it doesn't actually run pi.
            client = MagicMock()

            async def fake_run_prompt(text, image_paths=None):
                # Simulate one tool call + done.
                yield MagicMock(kind="tool", tool="pyagent_add_clip", args={}, result=None, error=None)
                yield MagicMock(kind="done")

            client.run_prompt = fake_run_prompt

            handler = MagicMock()
            handler.active_tasks = {}
            # Make the chat UI's "get workdir" path resolve to tmp_path.
            handler.get_workdir = lambda pid: tmp_path

            ws = AsyncMock()
            broadcast = AsyncMock()

            # Render orchestrator returns ok; orchestrator records a snapshot.
            def fake_render_project(**kwargs):
                from open_edit.storage.render_snapshots import (
                    RenderSnapshot, RenderSnapshotStore, RenderStatus,
                )
                snap_store = RenderSnapshotStore(snapshots_db)
                snap = RenderSnapshot(
                    project_id=kwargs["project_id"],
                    edit_graph_hash="h1",
                    render_path=tmp_path / "out.mp4",
                    status=RenderStatus.ready,
                    label="v1",
                )
                snap_store.append(snap)
                from open_edit.render.orchestrator import RenderResult
                return RenderResult(ok=True, output_path=str(tmp_path / "out.mp4"))

            monkeypatch.setattr(
                "open_edit.render.orchestrator.render_project",
                fake_render_project,
            )

            # Stub the edit_graph read so we don't need a real DB.
            def fake_read_ops(workdir):
                return []  # no new ops; just verify the wiring
            monkeypatch.setattr(ws_handlers, "_read_edit_graph_ops", fake_read_ops)

            await ws_handlers.handle_commit_feedback(
                handler=handler,
                ws=ws,
                project_id="p1",
                msg={"creativity_level": "balanced"},
                broadcast=broadcast,
                client=client,
            )

            # The handler must have broadcast `version_ready` (T5 carry-over).
            version_ready_calls = [
                c for c in broadcast.await_args_list
                if c.args[1].get("type") == "version_ready"
            ]
            assert len(version_ready_calls) == 1
            payload = version_ready_calls[0].args[1]
            assert "version_id" in payload

            # The note must have been marked processed.
            pending = store.list_pending("p1")
            assert len(pending) == 0

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original_db
        ws_module.handlers.get_snapshots_db_path = original_snap
