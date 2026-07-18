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

from phase4_chat_ui.session import PlanCard, Session, list_sessions, _validate_session_id
from phase4_chat_ui.pi_client import PiClient
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
) -> FastAPI:
    manager = ChatConnectionManager()

    session_state = {
        "project": project,
        "provider": provider,
        "model": model,
        "pi_binary": pi_binary,
        "catalog": catalog or str(DEFAULT_CATALOG),
        # D6: set True after an AI edit op mutates the project file; cleared
        # when the user confirms they reloaded Kdenlive (Ctrl+Shift+R).
        "reload_needed": False,
    }

    sessions_cache: dict[str, Session] = {}
    ws_session_map: dict[WebSocket, str] = {}
    ws_client_map: dict[WebSocket, PiClient] = {}

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

    async def get_project_info_async() -> dict | None:
        return await asyncio.to_thread(project_state.get_project_info, project, session_state["catalog"])

    async def get_timeline_summary_async() -> dict | None:
        return await asyncio.to_thread(project_state.get_timeline_summary, project, session_state["catalog"])

    async def broadcast_state() -> None:
        info = await get_project_info_async()
        for s in list(sessions_cache.values()):
            s.set_project_state(info)
        await manager.broadcast(
            {"type": "state", "reload_needed": session_state["reload_needed"], **(info or {})}
        )

    # ---- file watcher (Phase 5 handoff: refresh on any external write) --
    async def _on_project_changed(path: str) -> None:
        # D6: any change to the project file means Kdenlive needs a manual
        # reload (Ctrl+Shift+R) to reflect it — flag the banner.
        session_state["reload_needed"] = True
        await broadcast_state()

    async def safe_watch_project() -> None:
        try:
            await file_watcher.watch_project(project, _on_project_changed)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"File watcher failed: {e}")

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
        asyncio.create_task(safe_watch_project())
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
        info = await get_project_info_async()
        summary = (await get_timeline_summary_async()) if info else None
        return {
            "project": project,
            "info": info,
            "summary": summary,
        }

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
        
        client_for_ws = PiClient(
            provider=provider,
            model=model,
            project=project,
            binary=pi_binary,
            session_id=current_sess.session_id,
            pi_args=["--extension", str(_REPO_ROOT / "phase3_pyagent_core" / "extension.ts")],
        )
        ws_client_map[ws] = client_for_ws

        await ws.send_json({"type": "project", "path": project})
        await ws.send_json({"type": "state", **(await get_project_info_async() or {})})
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
        except Exception:
            pass
        finally:
            manager.disconnect(ws)
            ws_session_map.pop(ws, None)
            ws_client_map.pop(ws, None)
            if ws in active_tasks:
                task = active_tasks.pop(ws)
                task.cancel()
                asyncio.create_task(client_for_ws.stop())

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
            # D6: user confirmed they reloaded Kdenlive — clear the banner.
            session_state["reload_needed"] = False
            await broadcast_state()
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

                # Broadcast updated session list
                await manager.broadcast({
                    "type": "session_list",
                    "sessions": list_sessions(),
                    "active_session_id": target_id,
                })
                # Send loaded history
                await ws.send_json({
                    "type": "history",
                    "messages": loaded.history_dicts(),
                    "session_id": target_id,
                })
                # Send pending plan if exists
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
            # D6: any AI tool call mutates the project file; Kdenlive needs a
            # manual reload (Ctrl+Shift+R) to reflect it, so flag the banner.
            session_state["reload_needed"] = True
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
