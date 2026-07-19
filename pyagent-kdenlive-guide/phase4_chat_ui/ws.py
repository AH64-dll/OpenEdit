"""WebSocket handler for the pyagent chat UI.

Owns the per-connection state (session map, adapter map, active prompt
task), the dispatch logic for incoming messages, and the broadcast path
for project-state updates triggered by the file watcher. Also owns the
D-Bus reload call so the round-trip stays in one module.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
import uuid
from pathlib import Path

from fastapi import WebSocket

from phase4_chat_ui.session import (
    Session,
    get_sessions_dir,
    list_sessions,
    _validate_session_id,
)
from phase4_chat_ui.adapters import build_adapter, list_apps
from phase4_chat_ui.uploads import save_base64_image
from phase4_chat_ui import state as project_state
from phase4_chat_ui import watcher as file_watcher


def try_reload_kdenlive() -> bool:
    """Trigger a clean-restart in a running Kdenlive instance, if any."""
    try:
        from phase5_dbus_sync.dbus_client import KdenliveDBus
        from phase5_dbus_sync.kdenlive_state import detect_service_name, is_running
        if is_running():
            svc = detect_service_name()
            if svc:
                return KdenliveDBus(svc).clean_restart(clean=False)
    except Exception:
        pass
    return False


class ChatConnectionManager:
    """Tracks active WebSockets and broadcasts project-state updates."""

    def __init__(self) -> None:
        self.sessions: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.sessions.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.sessions:
            self.sessions.remove(ws)

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.sessions):
            try:
                await ws.send_json(msg)
            except Exception:
                self.disconnect(ws)


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
            await self._delete(ws, client, data)
        elif m == "change_project":
            await self._change_proj(ws, sess, client, data)
        elif m == "switch_session":
            await self._switch(ws, client, data)
        elif m in ("set_app", "set_model"):
            await self._set(ws, sess, data, is_app=(m == "set_app"))
        elif m == "prompt":
            await self._prompt(ws, sess, client, data)

    # ---- per-message handlers --------------------------------------

    async def _delete(self, ws, client, data) -> None:
        target = data.get("session_id")
        if not target or not _validate_session_id(target):
            await ws.send_json({"type": "error", "text": "Invalid session ID"})
            return
        self.sessions_cache.pop(target, None)
        path = get_sessions_dir() / f"{target}.json"
        try:
            if path.exists():
                os.remove(path)
        except Exception as e:
            await ws.send_json({"type": "error", "text": f"Failed to delete session file: {e}"})
            return
        if self.ws_session_map.get(ws) != target:
            await self.manager.broadcast({
                "type": "session_list",
                "sessions": list_sessions(),
                "active_session_id": self.ws_session_map.get(ws),
            })
            return
        remaining = list_sessions()
        loaded = Session.load(remaining[0]["session_id"]) if remaining else None
        await self._adopt(ws, client, loaded or self._new_session())

    async def _change_proj(self, ws, sess, client, data) -> None:
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
        self.start_watching(new_path)
        await ws.send_json({"type": "project", "path": new_path})
        await self.manager.broadcast({
            "type": "session_list",
            "sessions": list_sessions(),
            "active_session_id": sess.session_id,
        })
        await self.broadcast_state(new_path)

    async def _switch(self, ws, client, data) -> None:
        target = data.get("session_id")
        if not target or not _validate_session_id(target):
            await ws.send_json({"type": "error", "text": "Invalid session ID"})
            return
        if target not in self.sessions_cache:
            loaded = Session.load(target)
            if loaded:
                self.sessions_cache[target] = loaded
        loaded = self.sessions_cache.get(target)
        if not loaded:
            return
        new = self._rebuild_adapter(ws, loaded.app or "piagent", loaded.model or "", loaded)
        if new:
            self.ws_client_map[ws] = new
            await self._adopt(ws, new, loaded)

    async def _set(self, ws, sess, data, *, is_app: bool) -> None:
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
            if self._rebuild_adapter(ws, val, model, sess) is None:
                await ws.send_json({"type": "error", "text": f"Failed to start agent: {val}"})
                return
            await ws.send_json({"type": "app_changed", "app_id": val, "model": model})
        else:
            sess.model = val
            sess.save()
            if self._rebuild_adapter(ws, sess.app, val, sess) is None:
                await ws.send_json({"type": "error", "text": f"Failed to load model: {val}"})
                return
            await ws.send_json({"type": "model_changed", "model": val})

    async def _prompt(self, ws, sess, client, data) -> None:
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
        if ws in self.active_tasks:
            self.active_tasks.pop(ws).cancel()
            client.stop()

        async def run() -> None:
            try:
                async for ev in client.run_prompt(text, paths):
                    await self.relay(ws, ev, sess)
                await self.broadcast_state()
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
                if self.active_tasks.get(ws) is asyncio.current_task():
                    self.active_tasks.pop(ws, None)
        self.active_tasks[ws] = asyncio.create_task(run())

    async def relay(self, ws: WebSocket, ev, sess: Session) -> None:
        if ev.kind == "message_delta" and ev.role == "assistant":
            await ws.send_json({"type": "message_delta", "role": "assistant", "text": ev.text})
        elif ev.kind == "thinking":
            await ws.send_json({"type": "thinking", "text": ev.text or ""})
        elif ev.kind == "message" and ev.role == "assistant":
            sess.add_assistant_message(ev.text or "")
            await ws.send_json({"type": "message", "role": "assistant", "text": ev.text})
        elif ev.kind == "tool":
            sess.add_tool_event(ev.tool or "tool", ev.args or {}, ev.result)
            self.session_state["reload_needed"][sess.project] = True
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
