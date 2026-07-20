"""Per-message-type WebSocket handlers.

Each function takes the owning `WsHandler` as its first arg (so it can
read/write the shared state — session map, adapter map, active tasks,
active watchers, reload flags) plus the websocket and the incoming JSON
payload. The dispatcher in `WsHandler.handle` matches on the wire-level
`type` field and routes to the right function here.

Grouped here (vs. methods on `WsHandler`) so the per-message logic —
which is the bulk of the WebSocket protocol surface — can live in its
own module without dragging the WsHandler shell up to 400+ lines.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import WebSocket

from phase4_chat_ui.adapters import build_adapter, list_apps
from phase4_chat_ui.session import (
    Session,
    get_sessions_dir,
    list_sessions,
    _validate_session_id,
)
from phase4_chat_ui.uploads import save_base64_image


# ---- notes (Phase 4 T6) --------------------------------------------------


_NOTES_DIRNAME = ".open_edit_notes"


def get_notes_db_path(project_id: str) -> Path:
    """Resolve the SQLite path for a project's notes.

    Project_id is a free-form string (e.g. an absolute .kdenlive path or
    a short slug). For paths we anchor the .db next to the project file;
    for slugs we fall back to a notes dir under the user's home.
    """
    p = Path(project_id)
    if p.is_absolute() and p.suffix:
        return p.parent / ".open_edit" / "notes.db"
    return Path.home() / _NOTES_DIRNAME / f"{project_id}.db"


def parse_anchor(data: dict):
    """Build a NoteAnchor from the wire-level dict.

    Dispatches by `anchor_type` to the right Pydantic model. Unknown
    anchor_types raise ``ValueError`` with a clear message instead of
    falling through to ``TimestampAnchor`` (which would either drop
    region/op data or crash the connection on a mismatched signature).
    """
    from open_edit.storage.notes import (
        TimestampAnchor, RegionAnchor, OpAnchor,
    )
    kind = data.get("anchor_type")
    if kind == "timestamp":
        return TimestampAnchor(**data)
    if kind == "region":
        return RegionAnchor(**data)
    if kind == "op":
        return OpAnchor(**data)
    raise ValueError(
        f"unknown anchor_type {kind!r}; expected one of 'timestamp', 'region', 'op'"
    )


def _note_list_payload(project_id: str) -> dict:
    """Build a `note_list` message for the project."""
    from open_edit.storage.notes import NotesStore
    store = NotesStore(get_notes_db_path(project_id))
    notes = store.list_all(project_id)
    return {
        "type": "note_list",
        "project_id": project_id,
        "notes": [n.model_dump(mode="json") for n in notes],
    }


async def handle_note_add(ws, project_id, msg, broadcast) -> None:
    """`note_add` — persist a new note and rebroadcast the project list."""
    from open_edit.storage.notes import NotesStore, ReviewNote, NoteSource, NoteStatus
    store = NotesStore(get_notes_db_path(project_id))
    note = ReviewNote(
        project_id=project_id,
        anchor=parse_anchor(msg["anchor"]),
        text=msg.get("text", ""),
        source=NoteSource(msg["source"]),
        status=NoteStatus.pending,
    )
    store.append(note)
    await broadcast(project_id, _note_list_payload(project_id))


async def handle_note_update(ws, project_id, msg, broadcast) -> None:
    """`note_update` — edit text or dismiss a note; rebroadcast."""
    from open_edit.storage.notes import NotesStore
    store = NotesStore(get_notes_db_path(project_id))
    note_id = msg.get("note_id")
    if not note_id:
        return
    fields: dict = {}
    if "text" in msg:
        fields["text"] = msg["text"]
    status = msg.get("status")
    if status is not None:
        fields["status"] = status
    if fields:
        store.update(note_id, **fields)
    await broadcast(project_id, _note_list_payload(project_id))


async def handle_note_delete(ws, project_id, msg, broadcast) -> None:
    """`note_delete` — soft-delete (dismiss) a note; rebroadcast."""
    from open_edit.storage.notes import NotesStore
    store = NotesStore(get_notes_db_path(project_id))
    note_id = msg.get("note_id")
    if not note_id:
        return
    store.mark_dismissed([note_id])
    await broadcast(project_id, _note_list_payload(project_id))


async def handle_note_list(ws, project_id, msg, broadcast) -> None:
    """`note_list` — push the current notes snapshot to the requesting socket."""
    await ws.send_json(_note_list_payload(project_id))


# ---- render version history (Phase 4 T4) ---------------------------------


def get_workdir(project_id: str) -> Path:
    """Resolve the project's working directory.

    For absolute `.kdenlive` paths this is `<project_parent>/.open_edit/`
    — the directory containing `notes.db`, `render_snapshots.db`, and
    `edit_graph.db`. For slug-style ids we fall back under the user's
    home. Centralised here so notes / snapshots / build_prior_state all
    agree on the same anchor.
    """
    p = Path(project_id)
    if p.is_absolute() and p.suffix:
        return p.parent / ".open_edit"
    return Path.home() / _NOTES_DIRNAME


def get_snapshots_db_path(project_id: str) -> Path:
    """Resolve the SQLite path for a project's render snapshots.

    Mirrors `get_notes_db_path`: anchor next to the project file for
    absolute paths, fall back under the user's home for slug-style ids.
    """
    p = Path(project_id)
    if p.is_absolute() and p.suffix:
        return p.parent / ".open_edit" / "render_snapshots.db"
    return Path.home() / _NOTES_DIRNAME / f"{project_id}.snapshots.db"


def _version_list_payload(project_id: str) -> dict:
    """Build a `version_list` message for the project."""
    from open_edit.storage.render_snapshots import RenderSnapshotStore
    store = RenderSnapshotStore(get_snapshots_db_path(project_id))
    snaps = store.list_for_project(project_id)
    return {
        "type": "version_list",
        "project_id": project_id,
        "versions": [s.model_dump(mode="json") for s in snaps],
    }


async def handle_version_list(ws, project_id, msg, broadcast) -> None:
    """`version_list` — push the current render-history snapshot to the
    requesting socket. The `version_ready` message (server → client) is
    fired by the orchestrator after a successful melt and re-requests
    this list, so the dropdown in the UI refreshes without polling.
    """
    await ws.send_json(_version_list_payload(project_id))


# ---- commit_feedback (Phase 4 T7) ----------------------------------------


def _read_edit_graph_ops(workdir: Path) -> list:
    """Read all ops from the project's edit_graph.db.

    Returns an empty list if the db doesn't exist yet (fresh project with
    no applied ops). The list is ordered by sequence_num, which is
    monotonic per project, so callers can use ``len(pre)`` / ``len(post)``
    to compute the slice of new ops appended during a run.
    """
    from open_edit.storage.edit_graph import EditGraphStore
    db_path = Path(workdir) / "edit_graph.db"
    if not db_path.exists():
        return []
    return EditGraphStore(db_path).load_all()


def _project_dir_for(project_id: str, workdir: Path) -> Path:
    """Return the directory that contains the project's `.open_edit/`.

    For absolute `.kdenlive` paths this is the file's parent; for slug
    ids we fall back to ``workdir.parent`` (the home-dir notes bucket
    for that slug). The orchestrator appends ``.open_edit/edit_graph.db``
    onto this so it must be the directory above ``.open_edit/``.
    """
    p = Path(project_id)
    if p.is_absolute() and p.suffix:
        return p.parent
    return workdir.parent


def _ops_to_note_id(new_ops: list) -> dict[str, str]:
    """Build a note_id → op_id map keyed on each op's `originating_note_id`.

    Per T7 step 7 (corrected per fix I1): the agent is instructed to pass
    `originating_note_id=<note_id>` to every IR API call (add_clip, add_effect,
    set_audio_gain, etc.). The IR stamps the field on each emitted op; this
    function looks each op up by that field and records the note→op
    attribution. Ops without `originating_note_id` are skipped (they were
    not produced in response to a note, e.g. free-form edits the agent
    made on its own). Notes with no attributed op get an empty string in
    the caller, which `mark_processed` stores as `[""]` for that note's
    `resulting_op_ids`.
    """
    mapping: dict[str, str] = {}
    for op in new_ops:
        note_id = getattr(op, "originating_note_id", None)
        if not note_id:
            continue
        mapping[note_id] = op.edit_id
    return mapping


async def handle_commit_feedback(handler, ws, sess, client, data) -> None:
    """`commit_feedback` — batch-process all pending notes (T7 + audit H1).

    Signature (per fix C1): matches the WsHandler dispatch
    ``(handler, ws, sess, client, data)`` — the dispatcher in
    ``handler.handle`` already has all four, so the per-message handler
    does not need to re-derive them. ``project_id`` is taken from
    ``sess.project`` and ``broadcast`` is the manager's
    ``broadcast_to_project`` callable (reached via ``handler.manager``).

    Flow (per phase4-design §3.7 + audit H1 + fixes C1/I1/I2):
      1. Generate a `commit_token`, call ``NotesStore.commit_pending`` to
         atomically claim all currently-pending notes (per audit H1).
      2. If empty, return an error to the requesting socket.
      3. Order the notes (timestamp → region → op-anchored) and build
         the ``pending_feedback`` block.
      4. Build the ``prior_state`` block (which itself embeds the
         ``pending_notes_summary`` sub-block from T3 + T6).
      5. Inject both into the system prompt and stream the agent run,
         relaying events to the requesting socket.
      6. After the agent run, find the new ops in ``edit_graph.db`` and
         attribute them to notes via each op's ``originating_note_id``
         (per fix I1 — the agent stamps this field via the IR API).
      7. Trigger ``render_project`` (which records a snapshot).
      8. Mark the claimed notes ``processed`` with their resulting op ids.
      9. Broadcast ``version_ready`` to the project-scoped connections
         (T5 carry-over #1 — also fired on render failure so the UI sees
         the new snapshot regardless of status; per fix M3).

    Failure handling (per fix I2): on agent-run failure, the claimed
    notes still carry their `commit_token`. Without intervention, the T2
    `commit_pending` filter ``AND commit_token IS NULL`` would exclude
    them on the next click — silent data loss. We call
    ``NotesStore.clear_commit_token`` on the claimed notes so they
    re-qualify as pending for the next `commit_feedback`.

    Notes added *after* step 1 are not in the agent's context and remain
    ``status=pending`` for the next click; the UI surfaces this with a
    "your last note arrived after you clicked Send" toast.
    """
    import uuid

    from open_edit.agent.style_inject import build_prior_state
    from open_edit.render.orchestrator import render_project, RenderResult
    from open_edit.storage.notes import NotesStore
    from open_edit.storage.render_snapshots import RenderSnapshotStore

    project_id = sess.project if sess else ""
    if not project_id:
        return

    broadcast = handler.manager.broadcast_to_project

    notes_store = NotesStore(get_notes_db_path(project_id))
    commit_token = uuid.uuid4().hex[:12]
    pending_notes = notes_store.commit_pending(project_id, commit_token)

    if not pending_notes:
        await ws.send_json({"type": "error", "message": "no pending notes to commit"})
        return

    # Order: timestamp first, then region, then op-anchored (per T7 spec).
    pending_notes.sort(key=lambda n: (
        {"timestamp": 0, "region": 1, "op": 2}[n.anchor.anchor_type],
        n.created_at,
    ))

    # Build the pending_feedback block (≤200 tokens for 5 notes).
    feedback_lines = []
    for n in pending_notes:
        if n.anchor.anchor_type == "timestamp":
            anchor_text = f"[{n.anchor.t_start:.1f}s - {n.anchor.t_end:.1f}s]"
        elif n.anchor.anchor_type == "region":
            anchor_text = f"[{n.anchor.t_start:.1f}s - {n.anchor.t_end:.1f}s, region]"
        else:
            anchor_text = f"[op_id={n.anchor.op_id}]"
        feedback_lines.append(f"- {n.note_id}: {anchor_text} \"{n.text}\"")
    pending_feedback = "\n".join(feedback_lines)

    workdir = get_workdir(project_id)

    # Build the prior_state (includes pending_notes_summary via T3+).
    prior_state = build_prior_state(
        project_id=project_id,
        expected_op_type="AddEffect",
        creativity_level=(data or {}).get("creativity_level", "balanced"),
        workdir=str(workdir),
    )

    # Snapshot the edit_graph so we can compute the diff of new ops.
    pre_ops = _read_edit_graph_ops(workdir)

    # Synthesize the agent prompt. The prior_state already wraps itself
    # in <prior_state>; we just append the pending_feedback block.
    # Per fix I1: instruct the agent to pass `originating_note_id=<note_id>`
    # to every IR API call so the resulting ops can be attributed back to
    # the note that requested them.
    prompt = (
        f"{prior_state}\n"
        f"<pending_feedback>\n{pending_feedback}\n</pending_feedback>\n\n"
        "Process the feedback above. For each note, emit operations that "
        "address it (in the order listed). When calling IR methods like "
        "`add_clip`, `add_effect`, `set_audio_gain`, `add_transition`, "
        "etc., pass `originating_note_id=<note_id>` so the resulting ops "
        "are tagged with the source note. Use the IR API; ops are "
        "appended to edit_graph.db automatically."
    )

    # Stream the agent run. We pass through `relay` so the user sees the
    # agent's text and tool calls in the chat panel.
    if client is None:
        client = handler.ws_client_map.get(ws)
    try:
        if client is not None:
            async for ev in client.run_prompt(prompt):
                await relay(ws, ev, sess, handler)
        else:
            await ws.send_json({"type": "error", "message": "no agent client available"})
            # No client means the run never happened; the notes are still
            # stamped by commit_pending. Clear the token so they're
            # re-claimable on the next click.
            notes_store.clear_commit_token([n.note_id for n in pending_notes])
            return
    except Exception as e:
        await ws.send_json({"type": "error", "message": f"agent run failed: {e}"})
        # Per fix I2: clear the commit_token on the claimed notes so they
        # re-qualify as pending for the next commit_pending. The T2
        # `commit_pending` filter `AND commit_token IS NULL` would
        # otherwise leave these notes stuck (silent data loss).
        notes_store.clear_commit_token([n.note_id for n in pending_notes])
        return

    # Find new ops appended during the run; attribute each to a note via
    # `op.originating_note_id` (per fix I1).
    post_ops = _read_edit_graph_ops(workdir)
    new_ops = post_ops[len(pre_ops):]
    note_to_op = _ops_to_note_id(new_ops)

    # Trigger the render. This is sync and CPU/IO-heavy; run in a thread
    # so the event loop stays responsive.
    project_dir = _project_dir_for(project_id, workdir)
    render_workdir = workdir / "renders"
    try:
        result = await asyncio.to_thread(
            render_project,
            project_id=project_id,
            project_dir=project_dir,
            workdir=render_workdir,
        )
    except Exception as e:
        result = RenderResult(ok=False, error=str(e))
        await ws.send_json({"type": "error", "message": f"render failed: {e}"})

    # Mark the claimed notes processed. Per audit H1, this is keyed on
    # the note_ids we got from commit_pending — a note added after step
    # 1 was never claimed and is intentionally left alone.
    notes_store.mark_processed(
        note_ids=[n.note_id for n in pending_notes],
        resulting_op_ids=[note_to_op.get(n.note_id, "") for n in pending_notes],
    )

    # Per audit M3: move processed notes older than 30 days to notes_archive
    # so the main notes table doesn't grow unbounded.
    archived_count = notes_store.archive_old_processed(retention_days=30)
    if archived_count > 0:
        print(f"Archived {archived_count} old notes")

    # Broadcast version_ready (T5 carry-over #1) for any new snapshot,
    # success OR failure (per fix M3). The UI surfaces failed renders
    # distinctly (audit H2: failed entries should be visible), so we
    # forward the status so the chat UI can render the version list
    # accordingly.
    snap_store = RenderSnapshotStore(get_snapshots_db_path(project_id))
    latest = snap_store.latest_for_project(project_id)
    if latest is not None:
        await broadcast(project_id, {
            "type": "version_ready",
            "version_id": latest.version_id,
            "render_path": str(latest.render_path),
            "status": latest.status.value if hasattr(latest.status, "value") else str(latest.status),
        })


# ---- session management -------------------------------------------------


async def handle_delete(handler, ws: WebSocket, client, data: dict) -> None:
    """`delete_session` — remove a session from disk + cache.

    If the deleted session was the one this websocket is currently bound
    to, fall back to adopting the next-most-recent session (or a fresh
    one) so the client isn't left pointing at a dead session id.
    """
    target = data.get("session_id")
    if not target or not _validate_session_id(target):
        await ws.send_json({"type": "error", "text": "Invalid session ID"})
        return
    handler.sessions_cache.pop(target, None)
    path = get_sessions_dir() / f"{target}.json"
    try:
        if path.exists():
            os.remove(path)
    except Exception as e:
        await ws.send_json({"type": "error", "text": f"Failed to delete session file: {e}"})
        return
    if handler.ws_session_map.get(ws) != target:
        await handler.manager.broadcast({
            "type": "session_list",
            "sessions": list_sessions(),
            "active_session_id": handler.ws_session_map.get(ws),
        })
        return
    remaining = list_sessions()
    loaded = Session.load(remaining[0]["session_id"]) if remaining else None
    await handler._adopt(ws, client, loaded or handler._new_session())


async def handle_change_project(handler, ws: WebSocket, sess: Session, client, data: dict) -> None:
    """`change_project` — rebind the websocket to a different .kdenlive file."""
    new_path = (data.get("path") or "").strip()
    if not new_path:
        return
    if not new_path.endswith(".kdenlive"):
        await ws.send_json({"type": "error", "text": "Project file must end with .kdenlive"})
        return
    if not Path(new_path).exists():
        await ws.send_json({"type": "error", "text": f"Project file does not exist: {new_path}"})
        return
    sess.project = new_path
    sess.save()
    client.project = new_path
    handler.start_watching(new_path)
    await ws.send_json({"type": "project", "path": new_path})
    await handler.manager.broadcast({
        "type": "session_list",
        "sessions": list_sessions(),
        "active_session_id": sess.session_id,
    })
    await handler.broadcast_state(new_path)


async def handle_switch(handler, ws: WebSocket, client, data: dict) -> None:
    """`switch_session` — bind the websocket to a different cached session."""
    target = data.get("session_id")
    if not target or not _validate_session_id(target):
        await ws.send_json({"type": "error", "text": "Invalid session ID"})
        return
    if target not in handler.sessions_cache:
        loaded = Session.load(target)
        if loaded:
            handler.sessions_cache[target] = loaded
    loaded = handler.sessions_cache.get(target)
    if not loaded:
        return
    new = handler._rebuild_adapter(ws, loaded.app or "piagent", loaded.model or "", loaded)
    if new:
        handler.ws_client_map[ws] = new
        await handler._adopt(ws, new, loaded)


async def handle_set(handler, ws: WebSocket, sess: Session, data: dict, *, is_app: bool) -> None:
    """`set_app` / `set_model` — swap the active adapter.

    Both messages mutate the session's `app` / `model` fields, rebuild the
    per-websocket adapter, and broadcast the change. App-change also
    picks a model compatible with the new app if the current one isn't
    available there.
    """
    key = "app_id" if is_app else "model"
    val = data.get(key)
    if not val:
        label = "app" if is_app else "model"
        await ws.send_json({"type": "error", "text": f"set_{label} requires {key}"})
        return
    if is_app:
        apps = {a["id"]: a for a in list_apps()}
        if val not in apps or not apps[val]["available"]:
            await ws.send_json({"type": "error", "text": f"Agent app not available: {val}"})
            return
        new_models = apps[val]["models"]
        model = sess.model if any(m["id"] == sess.model for m in new_models) else (
            new_models[0]["id"] if new_models else ""
        )
        sess.app, sess.model = val, model
        sess.save()
        if handler._rebuild_adapter(ws, val, model, sess) is None:
            await ws.send_json({"type": "error", "text": f"Failed to start agent: {val}"})
            return
        await ws.send_json({"type": "app_changed", "app_id": val, "model": model})
    else:
        sess.model = val
        sess.save()
        if handler._rebuild_adapter(ws, sess.app, val, sess) is None:
            await ws.send_json({"type": "error", "text": f"Failed to load model: {val}"})
            return
        await ws.send_json({"type": "model_changed", "model": val})


async def handle_prompt(handler, ws: WebSocket, sess: Session, client, data: dict) -> None:
    """`prompt` — start (or restart) a prompt run for the bound session.

    Saves pasted images to disk first, then spawns a background task that
    streams adapter events through `relay` to the websocket. The task is
    tracked in `handler.active_tasks` so `stop` can cancel it.
    """
    text = (data.get("text") or "").strip()
    if not text:
        return
    paths: list[str] = []
    for img in data.get("images") or []:
        try:
            paths.append(save_base64_image(img))
        except Exception as e:
            await ws.send_json({"type": "error", "text": f"Failed to save pasted image: {e}"})
            for p in paths:
                try: os.remove(p)
                except Exception: pass
            return
    sess.add_user_message(text, data.get("images") or [])
    if ws in handler.active_tasks:
        handler.active_tasks.pop(ws).cancel()
        client.stop()

    async def run() -> None:
        try:
            async for ev in client.run_prompt(text, paths):
                await relay(ws, ev, sess, handler)
            await handler.broadcast_state()
        except asyncio.CancelledError:
            try: await ws.send_json({"type": "status", "text": "stopped"})
            except Exception: pass
            raise
        except Exception as e:
            try: await ws.send_json({"type": "error", "text": f"Error running prompt: {e}"})
            except Exception: pass
        finally:
            for p in paths:
                try: os.remove(p)
                except Exception: pass
            if handler.active_tasks.get(ws) is asyncio.current_task():
                handler.active_tasks.pop(ws, None)
    handler.active_tasks[ws] = asyncio.create_task(run())


# ---- event relay ---------------------------------------------------------


async def relay(ws: WebSocket, ev, sess: Session, handler) -> None:
    """Translate a `PiEvent` from the adapter into a wire message.

    Side effects per kind:
    - `message` (assistant) — appended to session history.
    - `tool` — appended to history + flagged `reload_needed` for the
      project (Kdenlive will need a reload to reflect the tool's effect).
    - `cost` — folded into `sess.cost_usd` and broadcast.
    All other kinds are pure forwards to the websocket.
    """
    if ev.kind == "message_delta" and ev.role == "assistant":
        await ws.send_json({"type": "message_delta", "role": "assistant", "text": ev.text})
    elif ev.kind == "thinking":
        await ws.send_json({"type": "thinking", "text": ev.text or ""})
    elif ev.kind == "message" and ev.role == "assistant":
        sess.add_assistant_message(ev.text or "")
        await ws.send_json({"type": "message", "role": "assistant", "text": ev.text})
    elif ev.kind == "tool":
        sess.add_tool_event(ev.tool or "tool", ev.args or {}, ev.result)
        handler.session_state["reload_needed"][sess.project] = True
        await ws.send_json({
            "type": "tool", "tool": ev.tool, "args": ev.args,
            "result": ev.result, "error": ev.error,
        })
    elif ev.kind == "error":
        await ws.send_json({"type": "error", "text": ev.text or "error"})
    elif ev.kind == "cost" and ev.cost is not None:
        sess.cost_usd = round((sess.cost_usd or 0.0) + ev.cost, 6)
        await ws.send_json({"type": "cost", "usd": sess.cost_usd, "delta": ev.cost})
    elif ev.kind == "done":
        await ws.send_json({"type": "status", "text": "ready"})
