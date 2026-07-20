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
import sqlite3
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

    Dispatches by `anchor_type` to the right Pydantic model. Anything
    unexpected falls back to TimestampAnchor so we never crash the
    websocket over a malformed note.
    """
    from open_edit.storage.notes import (
        TimestampAnchor, RegionAnchor, OpAnchor,
    )
    kind = data.get("anchor_type")
    if kind == "region":
        return RegionAnchor(**data)
    if kind == "op":
        return OpAnchor(**data)
    return TimestampAnchor(**data)


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
    if "text" in msg:
        with sqlite3.connect(store.db_path) as con:
            con.execute(
                "UPDATE notes SET text = ? WHERE note_id = ?",
                (msg["text"], note_id),
            )
    if msg.get("status") == "dismissed":
        store.mark_dismissed([note_id])
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
