"""Phase 4 Task 6: commit_feedback race condition (audit H1).

A note added after commit_pending but before mark_processed should remain
pending. This is the core of audit H1: commit_pending is the atomic
"claim" — anything that arrives after it is left for the next round, and
the UI surfaces a "your last note arrived after you clicked Send" toast.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, NoteSource, NoteStatus,
)


def _make_note(project_id: str, text: str) -> ReviewNote:
    return ReviewNote(
        project_id=project_id,
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text=text,
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_race_note_added_after_commit_pending(tmp_path):
    """Per audit H1: a note appended after commit_pending must NOT be
    included in the returned list, and must remain status=pending after
    mark_processed is called on the original notes only."""
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(_make_note("p1", f"note {i}"))

    # Simulate commit_pending (T6 already does this).
    token = "token_abc"
    notes = store.commit_pending("p1", token)

    # Simulate a note added between commit_pending and mark_processed.
    store.append(_make_note("p1", "late note"))

    # Mark only the original 3 processed.
    store.mark_processed(
        [n.note_id for n in notes],
        resulting_op_ids=[f"op_{i}" for i in range(3)],
    )

    # The late note must still be pending.
    pending = store.list_pending("p1")
    assert len(pending) == 1
    assert pending[0].text == "late note"


def test_handler_leaves_late_note_pending(tmp_path, monkeypatch):
    """End-to-end: the handler's mark_processed call must use the note
    ids from the commit_pending result, so a note added after commit but
    before mark_processed is left alone."""
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
            store = NotesStore(db_path)
            store.append(_make_note("p1", "first"))

            # Mock the agent client. We append a "late note" right after
            # the agent run starts — this mirrors the race: the user
            # adds a note WHILE the agent is processing. commit_pending
            # has already claimed the original note, so the late one
            # must remain pending.
            client = MagicMock()

            async def fake_run_prompt(text, image_paths=None):
                store.append(_make_note("p1", "late note"))
                yield MagicMock(kind="done")

            client.run_prompt = fake_run_prompt

            handler = MagicMock()
            handler.active_tasks = {}
            handler.get_workdir = lambda pid: tmp_path

            ws = AsyncMock()
            broadcast = AsyncMock()

            monkeypatch.setattr(ws_handlers, "_read_edit_graph_ops", lambda w: [])

            def fake_render_project(**kwargs):
                from open_edit.render.orchestrator import RenderResult
                return RenderResult(ok=True, output_path=str(tmp_path / "out.mp4"))

            monkeypatch.setattr(
                "open_edit.render.orchestrator.render_project",
                fake_render_project,
            )

            await ws_handlers.handle_commit_feedback(
                handler=handler,
                ws=ws,
                project_id="p1",
                msg={"creativity_level": "balanced"},
                broadcast=broadcast,
                client=client,
            )

            # After the handler returns, the original note must be processed
            # and the late note must still be pending.
            pending = store.list_pending("p1")
            assert len(pending) == 1
            assert pending[0].text == "late note"

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original_db
        ws_module.handlers.get_snapshots_db_path = original_snap
