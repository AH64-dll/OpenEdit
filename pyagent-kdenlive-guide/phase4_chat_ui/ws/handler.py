"""WsHandler shell: per-app state, session helpers, websocket endpoint, dispatch.

Owns the per-connection state (session map, adapter map, active prompt
task, active watchers) and the WebSocket entry point. The actual
per-message-type handlers live in `handlers.py`; this module's `handle`
method dispatches by `type` and either handles the simple cases inline
or delegates to the appropriate `handle_*` function in `handlers.py`.
"""
from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from pathlib import Path

from fastapi import WebSocket

from phase4_chat_ui.adapters import build_adapter
from phase4_chat_ui.session import Session, list_sessions
from phase4_chat_ui import state as project_state
from phase4_chat_ui import watcher as file_watcher
from phase4_chat_ui.ws import handlers as msg_handlers
from phase4_chat_ui.ws.manager import try_reload_kdenlive


class WsHandler:
    """Per-app state + dispatch. One instance is built by `create_app`."""

    def __init__(
        self, *, project, session_state, sessions_cache, ws_session_map,
        ws_client_map, active_tasks, active_watchers,
        default_app_id, default_model_id, default_session, manager,
    ) -> None:
        self.project = project
        self.session_state = session_state
        self.sessions_cache = sessions_cache
        self.ws_session_map = ws_session_map
        self.ws_client_map = ws_client_map
        self.active_tasks = active_tasks
        self.active_watchers = active_watchers
        self.default_app_id = default_app_id
        self.default_model_id = default_model_id
        self.default_session = default_session
        self.manager = manager

    # ---- state / project helpers ------------------------------------

    async def _info(self, p: str) -> dict | None:
        return await asyncio.to_thread(project_state.get_project_info, p, self.session_state["catalog"])

    async def _summary(self, p: str) -> dict | None:
        return await asyncio.to_thread(project_state.get_timeline_summary, p, self.session_state["catalog"])

    async def broadcast_state(self, proj_path: str | None = None) -> None:
        paths = [proj_path] if proj_path else list(self.active_watchers.keys())
        for path in paths:
            info = await self._info(path)
            for s in list(self.sessions_cache.values()):
                if s.project == path:
                    s.set_project_state(info)
            await self.manager.broadcast({
                "type": "state",
                "project_path": path,
                "reload_needed": self.session_state["reload_needed"].get(path, False),
                **(info or {}),
            })

    def start_watching(self, proj_path: str) -> None:
        if not proj_path or proj_path in self.active_watchers:
            return

        async def on_changed(_path: str) -> None:
            self.session_state["reload_needed"][proj_path] = not try_reload_kdenlive()
            await self.broadcast_state(proj_path)

        async def safe_watch() -> None:
            try:
                await file_watcher.watch_project(proj_path, on_changed)
            except Exception as e:
                logging.getLogger(__name__).error(f"watcher failed for {proj_path}: {e}")
            finally:
                self.active_watchers.pop(proj_path, None)

        self.active_watchers[proj_path] = asyncio.create_task(safe_watch())

    def _rebuild_adapter(self, ws, app_id, model_id, sess):
        old = self.ws_client_map.get(ws)
        if old is not None:
            try: old.stop()
            except Exception: pass
        try:
            adapter = build_adapter(app_id, model_id, sess.project, sess.session_id)
        except ValueError:
            return None
        if not adapter.available():
            return None
        self.ws_client_map[ws] = adapter
        return adapter

    # ---- session helpers -------------------------------------------

    def _new_session(self, project: str | None = None) -> Session:
        new_id = f"pyagent-chat-{uuid.uuid4().hex[:12]}"
        proj = project or self.project
        s = Session(session_id=new_id,
                    name=f"{Path(proj).stem} - {time.strftime('%Y-%m-%d %H:%M')}",
                    project=proj)
        s.save()
        self.sessions_cache[new_id] = s
        return s

    async def _send_initial_snapshot(self, ws, sess: Session) -> None:
        """Push the state + history + (plan if any) messages for `sess`.

        Unlike `_adopt_snapshot` this does NOT emit `plan_resolved` for the
        no-plan case — the JS client distinguishes the initial-load "no
        plan yet" state from the post-switch "previously had a plan, now
        cleared" state, and the wire protocol reflects that asymmetry.
        """
        info = await self._info(sess.project)
        await ws.send_json({
            "type": "state",
            "project_path": sess.project,
            "reload_needed": self.session_state["reload_needed"].get(sess.project, False),
            **(info or {}),
        })
        await ws.send_json({
            "type": "history",
            "messages": sess.history_dicts(),
            "session_id": sess.session_id,
        })
        if sess.pending_plan:
            p = sess.pending_plan
            await ws.send_json({"type": "plan", "plan_id": p.plan_id, "summary": p.summary, "diff": p.diff})

    async def _adopt_snapshot(self, ws, sess: Session) -> None:
        """Push state + history + plan for a session that the client is
        switching TO. Emits `plan_resolved` when no plan is pending so the
        client clears any stale plan it was previously displaying."""
        info = await self._info(sess.project)
        await ws.send_json({
            "type": "state",
            "project_path": sess.project,
            "reload_needed": self.session_state["reload_needed"].get(sess.project, False),
            **(info or {}),
        })
        await ws.send_json({
            "type": "history",
            "messages": sess.history_dicts(),
            "session_id": sess.session_id,
        })
        if sess.pending_plan:
            p = sess.pending_plan
            await ws.send_json({"type": "plan", "plan_id": p.plan_id, "summary": p.summary, "diff": p.diff})
        else:
            await ws.send_json({"type": "plan_resolved", "plan_id": "", "decision": "rejected"})

    async def _adopt(self, ws, client, sess: Session) -> None:
        """Bind a chosen session to a websocket and push the standard snapshot."""
        self.ws_session_map[ws] = sess.session_id
        client.session_id = sess.session_id
        client.project = sess.project
        self.start_watching(sess.project)
        await ws.send_json({"type": "project", "path": sess.project})
        await self._adopt_snapshot(ws, sess)
        await self.manager.broadcast({
            "type": "session_list",
            "sessions": list_sessions(),
            "active_session_id": sess.session_id,
        })

    async def _handle_note(self, ws, sess: Session, m: str, data: dict) -> None:
        """Dispatch project-scoped message types (notes + version history).

        All these messages carry an implicit `project_id` derived from the
        websocket's currently-bound session. Broadcasts are scoped to that
        project (per audit H4) so other projects in the same UI don't see
        each other's notes or render history.
        """
        project_id = sess.project
        if not project_id:
            return
        # Make sure this ws is tracked for project-scoped broadcasts.
        self.manager.track(project_id, ws)
        broadcast = self.manager.broadcast_to_project
        if m == "note_add":
            await msg_handlers.handle_note_add(ws, project_id, data, broadcast)
        elif m == "note_update":
            await msg_handlers.handle_note_update(ws, project_id, data, broadcast)
        elif m == "note_delete":
            await msg_handlers.handle_note_delete(ws, project_id, data, broadcast)
        elif m == "note_list":
            await msg_handlers.handle_note_list(ws, project_id, data, broadcast)
        elif m == "version_list":
            await msg_handlers.handle_version_list(ws, project_id, data, broadcast)

    # ---- main websocket endpoint -----------------------------------

    async def ws_endpoint(self, ws: WebSocket) -> None:
        await self.manager.connect(ws)
        sess = self.default_session
        self.ws_session_map[ws] = sess.session_id
        client = self._rebuild_adapter(ws, self.default_app_id, self.default_model_id, sess)
        if client is None:
            client = build_adapter("piagent", self.default_model_id, sess.project, sess.session_id)
            self.ws_client_map[ws] = client
        self.start_watching(sess.project)
        # Initial snapshot: order is part of the wire protocol (the JS
        # client in static/app.js consumes these in this sequence).
        self.manager.track(sess.project, ws)
        await ws.send_json({"type": "project", "path": sess.project})
        await ws.send_json({"type": "cost", "usd": sess.cost_usd, "delta": 0.0})
        await self._send_initial_snapshot(ws, sess)
        await ws.send_json({
            "type": "session_list",
            "sessions": list_sessions(),
            "active_session_id": sess.session_id,
        })
        try:
            while True:
                data = await ws.receive_json()
                await self.handle(ws, data)
        except Exception:
            traceback.print_exc()
        finally:
            self.manager.disconnect(ws)
            self.ws_session_map.pop(ws, None)
            self.ws_client_map.pop(ws, None)
            if ws in self.active_tasks:
                self.active_tasks.pop(ws).cancel()
            client.stop()

    # ---- message dispatch ------------------------------------------

    async def handle(self, ws: WebSocket, data: dict) -> None:
        sid = self.ws_session_map.get(ws)
        if not sid or sid not in self.sessions_cache:
            return
        sess = self.sessions_cache[sid]
        client = self.ws_client_map.get(ws)
        if not client:
            return
        m = data.get("type")
        if m == "refresh_state":
            self.session_state["reload_needed"][sess.project] = False
            await self.broadcast_state(sess.project)
        elif m == "reload_kdenlive":
            if try_reload_kdenlive():
                self.session_state["reload_needed"][sess.project] = False
                await ws.send_json({"type": "status", "text": "Reloaded project in Kdenlive"})
                await self.broadcast_state(sess.project)
            else:
                await ws.send_json({"type": "error", "text": "Failed to reload Kdenlive over D-Bus. Is Kdenlive open?"})
        elif m in ("approve", "reject"):
            plan = sess.pending_plan
            if plan:
                decision = m + "d"
                sess.resolve_plan(decision)
                self.manager.broadcast({"type": "plan_resolved", "plan_id": plan.plan_id, "decision": decision})
                sess.clear_pending_plan()
        elif m == "stop":
            if ws in self.active_tasks:
                self.active_tasks.pop(ws).cancel()
                client.stop()
        elif m == "new_session":
            new_sess = self._new_session()
            self.ws_session_map[ws] = new_sess.session_id
            client.session_id = new_sess.session_id
            await self.manager.broadcast({
                "type": "session_list",
                "sessions": list_sessions(),
                "active_session_id": new_sess.session_id,
            })
            await ws.send_json({"type": "history", "messages": [], "session_id": new_sess.session_id})
        elif m == "delete_session":
            await msg_handlers.handle_delete(self, ws, client, data)
        elif m == "change_project":
            await msg_handlers.handle_change_project(self, ws, sess, client, data)
        elif m == "switch_session":
            await msg_handlers.handle_switch(self, ws, client, data)
        elif m in ("set_app", "set_model"):
            await msg_handlers.handle_set(self, ws, sess, data, is_app=(m == "set_app"))
        elif m == "prompt":
            await msg_handlers.handle_prompt(self, ws, sess, client, data)
        elif m in ("note_add", "note_update", "note_delete", "note_list", "version_list"):
            await self._handle_note(ws, sess, m, data)
        elif m == "commit_feedback":
            await msg_handlers.handle_commit_feedback(self, ws, sess, client, data)
