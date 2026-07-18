"""FastAPI app for the pyagent chat UI."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from phase4_chat_ui.session import PlanCard, Session
from phase4_chat_ui.pi_client import PiClient
from phase4_chat_ui import state as project_state
from phase4_chat_ui import watcher as file_watcher

# Make Phase 3 importable (it lives in a sibling package at repo root).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_CATALOG = _REPO_ROOT / "phase1_knowledge_base" / "catalog.json"


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
    app = FastAPI(title="PyAgent Chat UI")
    manager = ChatConnectionManager()
    session = Session()
    session_state = {
        "project": project,
        "provider": provider,
        "model": model,
        "pi_binary": pi_binary,
        "catalog": catalog or str(DEFAULT_CATALOG),
    }

    client = PiClient(
        provider=provider,
        model=model,
        project=project,
        binary=pi_binary,
        session_id=f"pyagent-chat-{uuid.uuid4().hex[:12]}",
        pi_args=["--extension", str(_REPO_ROOT / "phase3_pyagent_core" / "extension.ts")],
    )

    # ---- helpers ------------------------------------------------------

    def get_project_info() -> dict | None:
        return project_state.get_project_info(project, session_state["catalog"])

    def get_timeline_summary() -> dict | None:
        return project_state.get_timeline_summary(project, session_state["catalog"])

    async def broadcast_state() -> None:
        info = get_project_info()
        session.set_project_state(info)
        await manager.broadcast({"type": "state", **(info or {})})

    # ---- file watcher (Phase 5 handoff: refresh on any external write) --
    async def _on_project_changed(path: str) -> None:
        await broadcast_state()

    @app.on_event("startup")
    async def _start_watcher() -> None:
        import asyncio
        asyncio.create_task(
            file_watcher.watch_project(project, _on_project_changed)
        )

    # ---- static + index ----------------------------------------------

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(str(static_dir / "index.html"))

    # ---- REST: project info ------------------------------------------

    @app.get("/api/project")
    async def api_project():
        info = get_project_info()
        summary = get_timeline_summary() if info else None
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
        plan = session.pending_plan
        if plan is None:
            return {"ok": False, "error": "no pending plan"}
        session.resolve_plan(decision)  # type: ignore[arg-type]
        await manager.broadcast({
            "type": "plan_resolved",
            "plan_id": plan.plan_id,
            "decision": decision,
        })
        # The Phase 3 extension auto-approves via PYAGENT_AUTO_APPROVE; the
        # plan card here is a UI affordance. Mark it cleared after broadcast.
        session.clear_pending_plan()
        return {"ok": True, "decision": decision}

    # ---- WebSocket: chat --------------------------------------------

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        await ws.send_json({"type": "project", "path": project})
        await ws.send_json({"type": "state", **(get_project_info() or {})})
        try:
            while True:
                data = await ws.receive_json()
                await handle_ws_message(ws, data)
        except WebSocketDisconnect:
            manager.disconnect(ws)

    async def handle_ws_message(ws: WebSocket, data: dict) -> None:
        mtype = data.get("type")
        if mtype == "refresh_state":
            await broadcast_state()
            return
        if mtype == "approve":
            await api_plan("approved")
            return
        if mtype == "reject":
            await api_plan("rejected")
            return
        if mtype == "prompt":
            text = (data.get("text") or "").strip()
            if not text:
                return
            session.add_user_message(text)
            # NOTE: the client already renders the user's message on submit,
            # so we do NOT echo it back here — echoing would duplicate it.
            try:
                async for ev in client.run_prompt(text):
                    await relay_event(ws, ev)
                # After the agent finishes, refresh project state.
                await broadcast_state()
            except Exception:
                # Client disconnected mid-turn, or a send failed. Swallow so
                # the handler doesn't crash the server.
                pass

    async def relay_event(ws: WebSocket, ev) -> None:
        if ev.kind == "message_delta" and ev.role == "assistant":
            # Live partial; UI updates the in-progress bubble in place.
            await ws.send_json({"type": "message_delta", "role": "assistant", "text": ev.text})
        elif ev.kind == "message" and ev.role == "assistant":
            session.add_assistant_message(ev.text or "")
            await ws.send_json({"type": "message", "role": "assistant", "text": ev.text})
        elif ev.kind == "tool":
            session.add_tool_event(ev.tool or "tool", ev.args or {}, ev.result)
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
