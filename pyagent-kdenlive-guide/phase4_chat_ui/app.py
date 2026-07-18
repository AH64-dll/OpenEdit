"""FastAPI app for the pyagent chat UI."""
from __future__ import annotations

import argparse
import json
import os
import sys
import typing
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from phase4_chat_ui.session import PlanCard, Session, list_sessions, _validate_session_id, get_sessions_dir, DEFAULT_APP, DEFAULT_MODEL
from phase4_chat_ui.pi_client import PiClient
from phase4_chat_ui.agent_adapters import build_adapter, list_apps, AgentAdapter, PiAgentAdapter, OpenCodeAdapter
from phase4_chat_ui import state as project_state
from phase4_chat_ui import watcher as file_watcher

# Make Phase 3 importable (it lives in a sibling package at repo root).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_CATALOG = _REPO_ROOT / "phase1_knowledge_base" / "catalog.json"


import base64
import re
import asyncio

ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

def save_base64_image(data_url: str) -> str:
    if data_url.startswith("data:image/"):
        match = re.match(r"^data:image/(\w+);base64,(.+)$", data_url)
        if match:
            ext = match.group(1).lower()
            base64_data = match.group(2)
        else:
            ext = "png"
            base64_data = data_url
    else:
        ext = "png"
        base64_data = data_url

    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError(f"Unsupported image format: {ext}")

    try:
        img_data = base64.b64decode(base64_data)
    except Exception as e:
        raise ValueError(f"Invalid base64 encoding: {e}")

    if len(img_data) > MAX_IMAGE_SIZE:
        raise ValueError(f"Image too large: {len(img_data)} bytes (max {MAX_IMAGE_SIZE})")

    upload_dir = Path("/tmp/pyagent_uploads")
    if upload_dir.is_symlink():
        raise OSError("Upload directory cannot be a symbolic link")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = upload_dir / filename
    file_path.write_bytes(img_data)
    return str(file_path)


class ChatConnectionManager:
    """Holds the single session and fans project-state updates to clients."""

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


def create_app(
    project: str,
    provider: str = "opencode-go",
    model: str = "minimax-m3",
    pi_binary: str | None = None,
    catalog: str | None = None,
    default_app: str = DEFAULT_APP,
) -> FastAPI:
    manager = ChatConnectionManager()

    session_state = {
        "project": project,
        "provider": provider,
        "model": model,
        "pi_binary": pi_binary,
        "catalog": catalog or str(DEFAULT_CATALOG),
        "reload_needed": {},
    }

    sessions_cache: dict[str, Session] = {}
    ws_session_map: dict[WebSocket, str] = {}
    ws_client_map: dict[WebSocket, AgentAdapter] = {}

    default_app_id = default_app
    default_model_id = model if default_app == "piagent" else model

    default_session = None
    all_saved = list_sessions()
    for s_meta in all_saved:
        if s_meta.get("project") == project:
            loaded = Session.load(s_meta["session_id"])
            if loaded:
                default_session = loaded
                break

    if default_session is None:
        import time
        new_id = f"pyagent-chat-{uuid.uuid4().hex[:12]}"
        proj_name = Path(project).stem
        nice_name = f"{proj_name} - {time.strftime('%Y-%m-%d %H:%M')}"
        default_session = Session(session_id=new_id, name=nice_name, project=project)
        default_session.save()

    sessions_cache[default_session.session_id] = default_session

    active_tasks: dict[WebSocket, asyncio.Task] = {}

    # ---- helpers ------------------------------------------------------

    def _rebuild_adapter_for(ws: WebSocket, app_id: str, model_id: str, sess: Session) -> AgentAdapter | None:
        """Build an adapter for (app_id, model_id); stop old one. Returns None on unavailable."""
        old = ws_client_map.get(ws)
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        try:
            adapter = build_adapter(app_id, model_id, sess.project, sess.session_id)
        except ValueError:
            return None
        if not adapter.available():
            return None
        ws_client_map[ws] = adapter
        return adapter

    active_watchers: dict[str, asyncio.Task] = {}

    async def get_project_info_async(proj_path: str) -> dict | None:
        return await asyncio.to_thread(project_state.get_project_info, proj_path, session_state["catalog"])

    async def get_timeline_summary_async(proj_path: str) -> dict | None:
        return await asyncio.to_thread(project_state.get_timeline_summary, proj_path, session_state["catalog"])

    async def broadcast_state(proj_path: str | None = None) -> None:
        paths = [proj_path] if proj_path else list(active_watchers.keys())
        for path in paths:
            info = await get_project_info_async(path)
            for s in list(sessions_cache.values()):
                if s.project == path:
                    s.set_project_state(info)
            await manager.broadcast(
                {
                    "type": "state",
                    "project_path": path,
                    "reload_needed": session_state["reload_needed"].get(path, False),
                    **(info or {})
                }
            )

    def start_watching_project(proj_path: str) -> None:
        if not proj_path or proj_path in active_watchers:
            return

        async def _on_project_changed(path: str) -> None:
            session_state["reload_needed"][proj_path] = True
            await broadcast_state(proj_path)

        async def safe_watch_project() -> None:
            try:
                await file_watcher.watch_project(proj_path, _on_project_changed)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"File watcher failed for {proj_path}: {e}")
            finally:
                active_watchers.pop(proj_path, None)

        task = asyncio.create_task(safe_watch_project())
        active_watchers[proj_path] = task

    # ---- temp file cleanup --------------------------------------------
    def _cleanup_stale_uploads(max_age_hours: int = 1) -> None:
        import time
        upload_dir = Path("/tmp/pyagent_uploads")
        if not upload_dir.exists():
            return
        cutoff = time.time() - max_age_hours * 3600
        for f in upload_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    async def _periodic_cleanup() -> None:
        while True:
            await asyncio.sleep(1800)  # every 30 minutes
            _cleanup_stale_uploads()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> typing.AsyncIterator[None]:
        start_watching_project(project)
        _cleanup_stale_uploads()
        asyncio.create_task(_periodic_cleanup())
        yield

    app = FastAPI(title="PyAgent Chat UI", lifespan=lifespan)

    # ---- static + index ----------------------------------------------

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(str(static_dir / "index.html"))

    # ---- REST: project info ------------------------------------------

    @app.get("/api/project")
    async def api_project():
        info = await get_project_info_async(project)
        summary = (await get_timeline_summary_async(project)) if info else None
        return {
            "project": project,
            "info": info,
            "summary": summary,
        }

    @app.get("/api/apps")
    async def api_apps():
        return {"apps": list_apps()}

    # ---- REST: plan approve / reject --------------------------------

    @app.post("/api/plan/{decision}")
    async def api_plan(decision: str):
        if decision not in ("approved", "rejected"):
            return {"ok": False, "error": "decision must be approved|rejected"}
        if not sessions_cache:
            return {"ok": False, "error": "no active sessions"}
        default_sess = next(iter(sessions_cache.values()))
        plan = default_sess.pending_plan
        if plan is None:
            return {"ok": False, "error": "no pending plan"}
        default_sess.resolve_plan(decision)  # type: ignore[arg-type]
        await manager.broadcast({
            "type": "plan_resolved",
            "plan_id": plan.plan_id,
            "decision": decision,
        })
        default_sess.clear_pending_plan()
        return {"ok": True, "decision": decision}

    # ---- WebSocket: chat --------------------------------------------

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        current_sess = default_session
        ws_session_map[ws] = current_sess.session_id
        
        ws_app_id = default_app_id
        ws_model_id = default_model_id
        client_for_ws = _rebuild_adapter_for(ws, ws_app_id, ws_model_id, current_sess)
        if client_for_ws is None:
            client_for_ws = build_adapter("piagent", default_model_id, current_sess.project, current_sess.session_id)
            ws_client_map[ws] = client_for_ws

        start_watching_project(current_sess.project)

        await ws.send_json({"type": "project", "path": current_sess.project})
        await ws.send_json({
            "type": "state",
            "project_path": current_sess.project,
            "reload_needed": session_state["reload_needed"].get(current_sess.project, False),
            **(await get_project_info_async(current_sess.project) or {})
        })
        # Send history
        await ws.send_json({
            "type": "history",
            "messages": current_sess.history_dicts(),
            "session_id": current_sess.session_id,
        })
        # Send pending plan if exists
        if current_sess.pending_plan:
            await ws.send_json({
                "type": "plan",
                "plan_id": current_sess.pending_plan.plan_id,
                "summary": current_sess.pending_plan.summary,
                "diff": current_sess.pending_plan.diff,
            })
        # Send session list
        await ws.send_json({
            "type": "session_list",
            "sessions": list_sessions(),
            "active_session_id": current_sess.session_id,
        })

        try:
            while True:
                data = await ws.receive_json()
                await handle_ws_message(ws, data)
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            manager.disconnect(ws)
            ws_session_map.pop(ws, None)
            ws_client_map.pop(ws, None)
            if ws in active_tasks:
                task = active_tasks.pop(ws)
                task.cancel()
                stopped = client_for_ws.stop()
                if asyncio.iscoroutine(stopped):
                    await stopped

    async def handle_ws_message(ws: WebSocket, data: dict) -> None:
        sess_id = ws_session_map.get(ws)
        if not sess_id or sess_id not in sessions_cache:
            return
        sess = sessions_cache[sess_id]
        ws_client = ws_client_map.get(ws)
        if not ws_client:
            return

        mtype = data.get("type")
        if mtype == "refresh_state":
            session_state["reload_needed"][sess.project] = False
            await broadcast_state(sess.project)
            return
        if mtype == "approve":
            plan = sess.pending_plan
            if plan:
                sess.resolve_plan("approved")
                await manager.broadcast({
                    "type": "plan_resolved",
                    "plan_id": plan.plan_id,
                    "decision": "approved",
                })
                sess.clear_pending_plan()
            return
        if mtype == "reject":
            plan = sess.pending_plan
            if plan:
                sess.resolve_plan("rejected")
                await manager.broadcast({
                    "type": "plan_resolved",
                    "plan_id": plan.plan_id,
                    "decision": "rejected",
                })
                sess.clear_pending_plan()
            return
        if mtype == "stop":
            if ws in active_tasks:
                task = active_tasks.pop(ws)
                task.cancel()
                await ws_client.stop()
                await ws.send_json({"type": "status", "text": "stopped"})
            return
        if mtype == "new_session":
            import time
            new_id = f"pyagent-chat-{uuid.uuid4().hex[:12]}"
            proj_name = Path(project).stem
            nice_name = f"{proj_name} - {time.strftime('%Y-%m-%d %H:%M')}"
            new_session = Session(session_id=new_id, name=nice_name, project=project)
            new_session.save()
            sessions_cache[new_id] = new_session
            
            ws_session_map[ws] = new_id
            ws_client.session_id = new_id

            # Broadcast new session list
            await manager.broadcast({
                "type": "session_list",
                "sessions": list_sessions(),
                "active_session_id": new_id,
            })
            # Send empty history
            await ws.send_json({
                "type": "history",
                "messages": [],
                "session_id": new_id,
            })
            return
        if mtype == "delete_session":
            target_id = data.get("session_id")
            if not target_id or not _validate_session_id(target_id):
                await ws.send_json({"type": "error", "text": "Invalid session ID"})
                return

            sessions_cache.pop(target_id, None)

            path = get_sessions_dir() / f"{target_id}.json"
            try:
                if path.exists():
                    os.remove(path)
            except Exception as e:
                await ws.send_json({"type": "error", "text": f"Failed to delete session file: {e}"})
                return

            current_active_id = ws_session_map.get(ws)
            if current_active_id == target_id:
                remaining = list_sessions()
                if remaining:
                    next_id = remaining[0]["session_id"]
                    loaded = Session.load(next_id)
                    if loaded:
                        sessions_cache[next_id] = loaded
                        ws_session_map[ws] = next_id
                        ws_client.session_id = next_id
                        ws_client.project = loaded.project
                        start_watching_project(loaded.project)

                        await ws.send_json({"type": "project", "path": loaded.project})
                        await ws.send_json({
                            "type": "state",
                            "project_path": loaded.project,
                            "reload_needed": session_state["reload_needed"].get(loaded.project, False),
                            **(await get_project_info_async(loaded.project) or {})
                        })
                        await manager.broadcast({
                            "type": "session_list",
                            "sessions": remaining,
                            "active_session_id": next_id,
                        })
                        await ws.send_json({
                            "type": "history",
                            "messages": loaded.history_dicts(),
                            "session_id": next_id,
                        })
                        if loaded.pending_plan:
                            await ws.send_json({
                                "type": "plan",
                                "plan_id": loaded.pending_plan.plan_id,
                                "summary": loaded.pending_plan.summary,
                                "diff": loaded.pending_plan.diff,
                            })
                        else:
                            await ws.send_json({"type": "plan_resolved", "plan_id": "", "decision": "rejected"})
                else:
                    import time
                    new_id = f"pyagent-chat-{uuid.uuid4().hex[:12]}"
                    proj_name = Path(project).stem
                    nice_name = f"{proj_name} - {time.strftime('%Y-%m-%d %H:%M')}"
                    new_session = Session(session_id=new_id, name=nice_name, project=project)
                    new_session.save()
                    sessions_cache[new_id] = new_session

                    ws_session_map[ws] = new_id
                    ws_client.session_id = new_id
                    ws_client.project = project
                    start_watching_project(project)

                    await ws.send_json({"type": "project", "path": project})
                    await ws.send_json({
                        "type": "state",
                        "project_path": project,
                        "reload_needed": session_state["reload_needed"].get(project, False),
                        **(await get_project_info_async(project) or {})
                    })
                    await manager.broadcast({
                        "type": "session_list",
                        "sessions": list_sessions(),
                        "active_session_id": new_id,
                    })
                    await ws.send_json({
                        "type": "history",
                        "messages": [],
                        "session_id": new_id,
                    })
            else:
                await manager.broadcast({
                    "type": "session_list",
                    "sessions": list_sessions(),
                    "active_session_id": current_active_id,
                })
            return

        if mtype == "change_project":
            new_path = data.get("path")
            if not new_path:
                return
            new_path = new_path.strip()
            if not new_path.endswith(".kdenlive"):
                await ws.send_json({"type": "error", "text": "Project file must end with .kdenlive"})
                return

            p = Path(new_path)
            if not p.exists():
                await ws.send_json({"type": "error", "text": f"Project file does not exist: {new_path}"})
                return

            sess.project = new_path
            sess.save()

            ws_client.project = new_path
            start_watching_project(new_path)

            await ws.send_json({"type": "project", "path": new_path})
            await manager.broadcast({
                "type": "session_list",
                "sessions": list_sessions(),
                "active_session_id": sess.session_id,
            })
            await broadcast_state(new_path)
            return

        if mtype == "switch_session":
            target_id = data.get("session_id")
            if not target_id or not _validate_session_id(target_id):
                await ws.send_json({"type": "error", "text": "Invalid session ID"})
                return

            if target_id not in sessions_cache:
                loaded = Session.load(target_id)
                if loaded:
                    sessions_cache[target_id] = loaded

            loaded = sessions_cache.get(target_id)
            if loaded:
                ws_session_map[ws] = target_id
                ws_client.session_id = target_id
                ws_client.project = loaded.project
                start_watching_project(loaded.project)
                ws_client = _rebuild_adapter_for(ws, loaded.app or "piagent", loaded.model or "", loaded)
                ws_client_map[ws] = ws_client

                await ws.send_json({"type": "project", "path": loaded.project})
                await ws.send_json({
                    "type": "state",
                    "project_path": loaded.project,
                    "reload_needed": session_state["reload_needed"].get(loaded.project, False),
                    **(await get_project_info_async(loaded.project) or {})
                })

                await manager.broadcast({
                    "type": "session_list",
                    "sessions": list_sessions(),
                    "active_session_id": target_id,
                })
                await ws.send_json({
                    "type": "history",
                    "messages": loaded.history_dicts(),
                    "session_id": target_id,
                })
                if loaded.pending_plan:
                    await ws.send_json({
                        "type": "plan",
                        "plan_id": loaded.pending_plan.plan_id,
                        "summary": loaded.pending_plan.summary,
                        "diff": loaded.pending_plan.diff,
                    })
                else:
                    await ws.send_json({"type": "plan_resolved", "plan_id": "", "decision": "rejected"})
            return

        if mtype == "set_app":
            app_id = data.get("app_id")
            if not app_id:
                await ws.send_json({"type": "error", "text": "set_app requires app_id"})
                return
            apps = {a["id"]: a for a in list_apps()}
            if app_id not in apps or not apps[app_id]["available"]:
                await ws.send_json({"type": "error", "text": f"Agent app not available: {app_id}"})
                return
            new_models = apps[app_id]["models"]
            new_model = sess.model if any(m["id"] == sess.model for m in new_models) else (new_models[0]["id"] if new_models else "")
            sess.app = app_id
            sess.model = new_model
            sess.save()
            adapter = _rebuild_adapter_for(ws, app_id, new_model, sess)
            if adapter is None:
                await ws.send_json({"type": "error", "text": f"Failed to start agent: {app_id}"})
                return
            await ws.send_json({"type": "app_changed", "app_id": app_id, "model": new_model})
            return

        if mtype == "set_model":
            model_id = data.get("model")
            if not model_id:
                await ws.send_json({"type": "error", "text": "set_model requires model"})
                return
            cur_app = sess.app
            sess.model = model_id
            sess.save()
            adapter = _rebuild_adapter_for(ws, cur_app, model_id, sess)
            if adapter is None:
                await ws.send_json({"type": "error", "text": f"Failed to load model: {model_id}"})
                return
            await ws.send_json({"type": "model_changed", "model": model_id})
            return
        if mtype == "prompt":
            text = (data.get("text") or "").strip()
            if not text:
                return

            images = data.get("images") or []
            image_paths = []
            for img_data in images:
                try:
                    path = save_base64_image(img_data)
                    image_paths.append(path)
                except Exception as e:
                    await ws.send_json({"type": "error", "text": f"Failed to save pasted image: {e}"})
                    for p in image_paths:
                        try: os.remove(p)
                        except Exception: pass
                    return

            sess.add_user_message(text, images)

            # Cancel existing task
            if ws in active_tasks:
                task = active_tasks.pop(ws)
                task.cancel()
                await ws_client.stop()

            async def run_prompt_task():
                try:
                    async for ev in ws_client.run_prompt(text, image_paths):
                        await relay_event(ws, ev, sess)
                    await broadcast_state()
                except asyncio.CancelledError:
                    try:
                        await ws.send_json({"type": "status", "text": "stopped"})
                    except Exception:
                        pass
                    raise
                except Exception as e:
                    try:
                        await ws.send_json({"type": "error", "text": f"Error running prompt: {e}"})
                    except Exception:
                        pass
                finally:
                    # Clean up image files
                    for p in image_paths:
                        try:
                            os.remove(p)
                        except Exception:
                            pass
                    if active_tasks.get(ws) == asyncio.current_task():
                        active_tasks.pop(ws, None)

            task = asyncio.create_task(run_prompt_task())
            active_tasks[ws] = task

    async def relay_event(ws: WebSocket, ev, sess: Session) -> None:
        if ev.kind == "message_delta" and ev.role == "assistant":
            await ws.send_json({"type": "message_delta", "role": "assistant", "text": ev.text})
        elif ev.kind == "thinking":
            await ws.send_json({"type": "thinking", "text": ev.text or ""})
        elif ev.kind == "message" and ev.role == "assistant":
            sess.add_assistant_message(ev.text or "")
            await ws.send_json({"type": "message", "role": "assistant", "text": ev.text})
        elif ev.kind == "tool":
            sess.add_tool_event(ev.tool or "tool", ev.args or {}, ev.result)
            session_state["reload_needed"][sess.project] = True
            await ws.send_json({
                "type": "tool",
                "tool": ev.tool,
                "args": ev.args,
                "result": ev.result,
                "error": ev.error,
            })
        elif ev.kind == "error":
            await ws.send_json({"type": "error", "text": ev.text or "error"})
        elif ev.kind == "done":
            await ws.send_json({"type": "status", "text": "ready"})

    return app
