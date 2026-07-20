"""Phase 4 Task 6: commit_feedback batch trigger.

These tests pin the NotesStore contract the commit_feedback handler relies on:
- commit_pending returns the stamped notes
- commit_pending with zero notes returns an empty list
- mark_processed transitions notes to status=processed
- clear_commit_token resets the token on claimed-but-unprocessed notes
  (per fix I2: agent-run failure must not leave notes unrecoverable)

The handler itself is wired in `ws/handlers.py`; these tests document the
storage contract that handler flow depends on (TDD-style pin against the
T6 NotesStore that already implements it) and the dispatch wiring
through `WsHandler.handle` (per fix C1).
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


def test_commit_feedback_clear_commit_token_resets_claim(tmp_path):
    """Per fix I2: clear_commit_token resets the token on a claimed note,
    so it re-qualifies as pending for the next commit_pending call.
    Without this, the T2 `commit_pending` filter `AND commit_token IS NULL`
    would leave the note un-claimable after an agent-run failure."""
    store = NotesStore(tmp_path / "notes.db")
    n = _make_note("p1", text="hello")
    store.append(n)

    notes = store.commit_pending("p1", "token_abc")
    assert notes[0].commit_token == "token_abc"

    # A second commit_pending must NOT re-claim the stamped note.
    second = store.commit_pending("p1", "token_def")
    assert second == []

    # After clear_commit_token, the note is re-claimable.
    store.clear_commit_token([n.note_id])
    third = store.commit_pending("p1", "token_ghi")
    assert len(third) == 1
    assert third[0].note_id == n.note_id


def test_commit_feedback_handler_returns_error_when_no_notes(tmp_path):
    """The handler must short-circuit with an error message when there are
    no pending notes — the user clicked Send with nothing to send."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers
    from phase4_chat_ui.session import Session

    db_path = tmp_path / "notes.db"

    def fake_db_path(project_id: str) -> Path:
        return db_path

    original = ws_module.handlers.get_notes_db_path
    ws_module.handlers.get_notes_db_path = fake_db_path
    try:
        async def run() -> None:
            ws = AsyncMock()
            sess = Session(session_id="s1", project="p1")
            await ws_handlers.handle_commit_feedback(
                handler=MagicMock(),
                ws=ws,
                sess=sess,
                client=MagicMock(),
                data={"creativity_level": "balanced"},
            )
            ws.send_json.assert_awaited_once()
            sent = ws.send_json.await_args.args[0]
            assert sent["type"] == "error"
            assert "no pending notes" in sent["message"]
        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original


def test_commit_feedback_dispatch_passes_correct_positional_args(tmp_path):
    """Per fix C1: WsHandler.handle must dispatch commit_feedback with
    positional args matching the handler's signature.

    The dispatcher in `handler.handle` calls
    `msg_handlers.handle_commit_feedback(self, ws, sess, client, data)`.
    The handler signature is `(handler, ws, sess, client, data)`. So the
    positional mapping is:
      args[0] = handler (WsHandler instance)
      args[1] = ws
      args[2] = sess (Session)
      args[3] = client (adapter)
      args[4] = data (dict)
    The pre-fix dispatch passed the same 5 things but the handler
    signature was different — `sess` was treated as `project_id`, `client`
    as `msg`, `data` as `broadcast`. This test would have failed before
    the fix because the handler would try `notes_store.commit_pending(sess, ...)`
    (a Session where a string was expected) and `Path(sess)` would either
    crash or do the wrong thing.
    """
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers
    from phase4_chat_ui.session import Session
    from phase4_chat_ui.ws.handler import WsHandler

    db_path = tmp_path / "notes.db"

    def fake_db_path(project_id: str) -> Path:
        return db_path

    original = ws_module.handlers.get_notes_db_path
    ws_module.handlers.get_notes_db_path = fake_db_path
    try:
        async def run() -> None:
            ws = AsyncMock()
            sess = Session(session_id="s1", project="p1")
            client = MagicMock()
            manager = MagicMock()
            manager.broadcast_to_project = AsyncMock()

            handler = WsHandler(
                project="p1",
                session_state={"reload_needed": {}},
                sessions_cache={sess.session_id: sess},
                ws_session_map={ws: sess.session_id},
                ws_client_map={ws: client},
                active_tasks={},
                active_watchers={},
                default_app_id="piagent",
                default_model_id="m",
                default_session=sess,
                manager=manager,
            )
            # Send a real commit_feedback message. The handler should
            # short-circuit with "no pending notes to commit" because the
            # notes db is empty. If the dispatch were wrong, the handler
            # would either crash (Session treated as str) or fail to
            # recognize the empty-notes case.
            await handler.handle(ws, {"type": "commit_feedback", "creativity_level": "balanced"})

            # The handler must have sent exactly one error message back.
            ws.send_json.assert_awaited_once()
            sent = ws.send_json.await_args.args[0]
            assert sent["type"] == "error"
            assert "no pending notes" in sent["message"]

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original


def test_commit_feedback_handler_broadcasts_version_ready(tmp_path, monkeypatch):
    """After a successful agent run + render, the handler must broadcast
    `version_ready` to the project's sockets so the UI re-requests the
    version list (per T5 Important #1)."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers
    from phase4_chat_ui.session import Session

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
            store.append(_make_note("p1", text="hello"))

            client = MagicMock()

            async def fake_run_prompt(text, image_paths=None):
                yield MagicMock(kind="tool", tool="pyagent_add_clip", args={}, result=None, error=None)
                yield MagicMock(kind="done")

            client.run_prompt = fake_run_prompt

            handler = MagicMock()
            handler.active_tasks = {}
            handler.get_workdir = lambda pid: tmp_path
            broadcast = AsyncMock()
            handler.manager.broadcast_to_project = broadcast

            ws = AsyncMock()
            sess = Session(session_id="s1", project="p1")

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

            def fake_read_ops(workdir):
                return []
            monkeypatch.setattr(ws_handlers, "_read_edit_graph_ops", fake_read_ops)

            await ws_handlers.handle_commit_feedback(
                handler=handler,
                ws=ws,
                sess=sess,
                client=client,
                data={"creativity_level": "balanced"},
            )

            # The handler must have broadcast `version_ready` (T5 carry-over).
            version_ready_calls = [
                c for c in broadcast.await_args_list
                if c.args[1].get("type") == "version_ready"
            ]
            assert len(version_ready_calls) == 1
            payload = version_ready_calls[0].args[1]
            assert "version_id" in payload
            assert payload.get("status") == "ready"

            # The note must have been marked processed.
            pending = store.list_pending("p1")
            assert len(pending) == 0

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original_db
        ws_module.handlers.get_snapshots_db_path = original_snap


def test_commit_feedback_handler_clears_commit_token_on_agent_failure(tmp_path, monkeypatch):
    """Per fix I2: when the agent run fails, the handler must clear
    commit_token on the claimed notes so they re-qualify as pending for
    the next commit_pending. Without this, the T2 WHERE clause
    `AND commit_token IS NULL` would leave the notes stuck (silent data
    loss)."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers
    from phase4_chat_ui.session import Session

    db_path = tmp_path / "notes.db"

    def fake_db_path(project_id: str) -> Path:
        return db_path

    original = ws_module.handlers.get_notes_db_path
    ws_module.handlers.get_notes_db_path = fake_db_path
    try:
        async def run() -> None:
            store = NotesStore(db_path)
            note = _make_note("p1", text="hello")
            store.append(note)
            # Sanity: the note is pending with no token.
            assert store.list_pending("p1")[0].commit_token is None

            client = MagicMock()

            async def failing_run_prompt(text, image_paths=None):
                raise RuntimeError("simulated agent failure")
                yield  # pragma: no cover (async generator never reaches this)

            client.run_prompt = failing_run_prompt

            handler = MagicMock()
            handler.active_tasks = {}
            handler.get_workdir = lambda pid: tmp_path
            broadcast = AsyncMock()
            handler.manager.broadcast_to_project = broadcast

            ws = AsyncMock()
            sess = Session(session_id="s1", project="p1")

            await ws_handlers.handle_commit_feedback(
                handler=handler,
                ws=ws,
                sess=sess,
                client=client,
                data={"creativity_level": "balanced"},
            )

            # After agent failure: the note is still status=pending AND
            # commit_token must be NULL so the next commit_pending re-claims it.
            all_notes = store.list_all("p1")
            assert len(all_notes) == 1
            assert all_notes[0].status == NoteStatus.pending
            assert all_notes[0].commit_token is None, (
                "I2 fix: commit_token must be cleared on agent failure so the "
                "next commit_pending re-claims the note."
            )

            # A subsequent commit_pending must now successfully re-claim the note.
            re_claimed = store.commit_pending("p1", "token_retry")
            assert len(re_claimed) == 1
            assert re_claimed[0].note_id == note.note_id

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original


def test_commit_feedback_handler_clears_commit_token_when_no_client(tmp_path, monkeypatch):
    """Per fix I2: when no agent client is available (handler resolves
    client from ws_client_map and finds nothing), the handler must still
    clear the commit_token. The agent run never started, so the notes
    would otherwise be stuck."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers
    from phase4_chat_ui.session import Session

    db_path = tmp_path / "notes.db"

    def fake_db_path(project_id: str) -> Path:
        return db_path

    original = ws_module.handlers.get_notes_db_path
    ws_module.handlers.get_notes_db_path = fake_db_path
    try:
        async def run() -> None:
            store = NotesStore(db_path)
            store.append(_make_note("p1", text="hello"))

            handler = MagicMock()
            handler.active_tasks = {}
            handler.get_workdir = lambda pid: tmp_path
            # No client in the map and no client passed in.
            handler.ws_client_map = {}
            broadcast = AsyncMock()
            handler.manager.broadcast_to_project = broadcast

            ws = AsyncMock()
            sess = Session(session_id="s1", project="p1")

            await ws_handlers.handle_commit_feedback(
                handler=handler,
                ws=ws,
                sess=sess,
                client=None,
                data={"creativity_level": "balanced"},
            )

            all_notes = store.list_all("p1")
            assert all_notes[0].commit_token is None

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original


def test_commit_feedback_handler_attributes_ops_via_originating_note_id(tmp_path, monkeypatch):
    """Per fix I1: the handler attributes new ops to notes via
    `op.originating_note_id` (the IR-level field that T1 supports).
    FIFO is no longer the mapping strategy."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers
    from phase4_chat_ui.session import Session
    from open_edit.ir.types import AddClipOp, AddEffectOp

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
            n1 = _make_note("p1", text="first")
            n2 = _make_note("p1", text="second")
            n3 = _make_note("p1", text="third")
            store.append(n1)
            store.append(n2)
            store.append(n3)

            client = MagicMock()

            async def fake_run_prompt(text, image_paths=None):
                yield MagicMock(kind="done")

            client.run_prompt = fake_run_prompt

            handler = MagicMock()
            handler.active_tasks = {}
            handler.get_workdir = lambda pid: tmp_path
            broadcast = AsyncMock()
            handler.manager.broadcast_to_project = broadcast

            ws = AsyncMock()
            sess = Session(session_id="s1", project="p1")

            def fake_render_project(**kwargs):
                from open_edit.storage.render_snapshots import (
                    RenderSnapshot, RenderSnapshotStore, RenderStatus,
                )
                snap_store = RenderSnapshotStore(snapshots_db)
                snap_store.append(RenderSnapshot(
                    project_id=kwargs["project_id"],
                    edit_graph_hash="h1",
                    render_path=tmp_path / "out.mp4",
                    status=RenderStatus.ready,
                ))
                from open_edit.render.orchestrator import RenderResult
                return RenderResult(ok=True, output_path=str(tmp_path / "out.mp4"))

            monkeypatch.setattr(
                "open_edit.render.orchestrator.render_project",
                fake_render_project,
            )

            # The agent ran and emitted three ops; the second and third
            # are tagged with originating_note_id. (n1 has no attributed op.)
            op_n2 = AddClipOp(
                author="ai", asset_hash="h", track_id="t1", position_sec=0.0,
                originating_note_id=n2.note_id,
            )
            op_n3 = AddEffectOp(
                author="ai", target_kind="clip", target_id="c1",
                effect_type="volume", params={"gain": 0.5},
                originating_note_id=n3.note_id,
            )
            # Add an op without originating_note_id (should be ignored).
            op_anon = AddClipOp(
                author="ai", asset_hash="h", track_id="t1", position_sec=1.0,
            )
            # First call: pre_ops (no ops). Second call: post_ops (the three
            # new ops). Use a counter so the handler sees a diff.
            pre_calls = [0]
            def fake_read_ops(workdir):
                pre_calls[0] += 1
                if pre_calls[0] == 1:
                    return []
                return [op_n2, op_n3, op_anon]
            monkeypatch.setattr(ws_handlers, "_read_edit_graph_ops", fake_read_ops)

            await ws_handlers.handle_commit_feedback(
                handler=handler,
                ws=ws,
                sess=sess,
                client=client,
                data={"creativity_level": "balanced"},
            )

            # n2's resulting_op_ids is [op_n2.edit_id]; n3's is [op_n3.edit_id];
            # n1's is ["" ] (no attributed op — mark_processed stores the
            # empty string verbatim; per T6's contract this is fine, the
            # note is still status=processed).
            notes_after = {n.note_id: n for n in store.list_all("p1")}
            assert notes_after[n1.note_id].status == NoteStatus.processed
            assert notes_after[n2.note_id].status == NoteStatus.processed
            assert notes_after[n3.note_id].status == NoteStatus.processed
            assert notes_after[n1.note_id].resulting_op_ids == [""]
            assert notes_after[n2.note_id].resulting_op_ids == [op_n2.edit_id]
            assert notes_after[n3.note_id].resulting_op_ids == [op_n3.edit_id]

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original_db
        ws_module.handlers.get_snapshots_db_path = original_snap


def test_commit_feedback_handler_broadcasts_version_ready_on_render_failure(tmp_path, monkeypatch):
    """Per fix M3: the handler must broadcast `version_ready` even when
    the render fails (audit H2: failed renders should be visible in the
    version list). The payload includes `status` so the UI can render
    failed versions distinctly."""
    from phase4_chat_ui import ws as ws_module
    from phase4_chat_ui.ws import handlers as ws_handlers
    from phase4_chat_ui.session import Session

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
            store.append(_make_note("p1", text="hello"))

            client = MagicMock()

            async def fake_run_prompt(text, image_paths=None):
                yield MagicMock(kind="done")

            client.run_prompt = fake_run_prompt

            handler = MagicMock()
            handler.active_tasks = {}
            handler.get_workdir = lambda pid: tmp_path
            broadcast = AsyncMock()
            handler.manager.broadcast_to_project = broadcast

            ws = AsyncMock()
            sess = Session(session_id="s1", project="p1")

            # Render returns ok=False, but the orchestrator still recorded
            # a `failed` snapshot.
            def fake_render_project(**kwargs):
                from open_edit.storage.render_snapshots import (
                    RenderSnapshot, RenderSnapshotStore, RenderStatus,
                )
                snap_store = RenderSnapshotStore(snapshots_db)
                snap_store.append(RenderSnapshot(
                    project_id=kwargs["project_id"],
                    edit_graph_hash="h1",
                    render_path=tmp_path / "out.mp4",
                    status=RenderStatus.failed,
                ))
                from open_edit.render.orchestrator import RenderResult
                return RenderResult(ok=False, error="melt blew up")

            monkeypatch.setattr(
                "open_edit.render.orchestrator.render_project",
                fake_render_project,
            )
            monkeypatch.setattr(ws_handlers, "_read_edit_graph_ops", lambda w: [])

            await ws_handlers.handle_commit_feedback(
                handler=handler,
                ws=ws,
                sess=sess,
                client=client,
                data={"creativity_level": "balanced"},
            )

            version_ready_calls = [
                c for c in broadcast.await_args_list
                if c.args[1].get("type") == "version_ready"
            ]
            assert len(version_ready_calls) == 1
            payload = version_ready_calls[0].args[1]
            assert payload.get("status") == "failed"

        asyncio.run(run())
    finally:
        ws_module.handlers.get_notes_db_path = original_db
        ws_module.handlers.get_snapshots_db_path = original_snap
