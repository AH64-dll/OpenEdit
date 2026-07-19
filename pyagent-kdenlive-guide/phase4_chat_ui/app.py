"""FastAPI app for the pyagent chat UI.

Slim entry point: route declarations, lifespan, and the default-session
bootstrap. WebSocket dispatch + project-state helpers live in `ws.py`;
image upload + temp-file cleanup live in `uploads.py`.
"""
from __future__ import annotations

import asyncio
import sys
import typing
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from phase4_chat_ui.session import Session, list_sessions, DEFAULT_APP
from phase4_chat_ui.uploads import (
    cleanup_stale_uploads,
    periodic_cleanup,
    save_base64_image,
)

# Re-exported for backward-compat with test_app.py.
__all__ = ["create_app", "save_base64_image"]

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_CATALOG = _REPO_ROOT / "phase1_knowledge_base" / "catalog.json"


def _bootstrap_default_session(project: str) -> Session:
    """Reuse the most recent session for `project`, or create a fresh one."""
    for meta in list_sessions():
        if meta.get("project") == project:
            loaded = Session.load(meta["session_id"])
            if loaded:
                return loaded
    import time
    new_id = f"pyagent-chat-{uuid.uuid4().hex[:12]}"
    nice = f"{Path(project).stem} - {time.strftime('%Y-%m-%d %H:%M')}"
    sess = Session(session_id=new_id, name=nice, project=project)
    sess.save()
    return sess


def create_app(
    project: str,
    provider: str = "opencode-go",
    model: str = "minimax-m3",
    pi_binary: str | None = None,
    catalog: str | None = None,
    default_app: str = DEFAULT_APP,
) -> FastAPI:
    from phase4_chat_ui.adapters import list_apps
    from phase4_chat_ui.ws import ChatConnectionManager, WsHandler

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
    default_session = _bootstrap_default_session(project)
    sessions_cache[default_session.session_id] = default_session

    handler = WsHandler(
        project=project,
        session_state=session_state,
        sessions_cache=sessions_cache,
        ws_session_map={},
        ws_client_map={},
        active_tasks={},
        active_watchers={},
        default_app_id=default_app,
        default_model_id=model,
        default_session=default_session,
        manager=manager,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> typing.AsyncIterator[None]:
        handler.start_watching(project)
        cleanup_stale_uploads()
        asyncio.create_task(periodic_cleanup())
        yield

    app = FastAPI(title="PyAgent Chat UI", lifespan=lifespan)
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(str(static_dir / "index.html"))

    @app.get("/api/project")
    async def api_project():
        info = await handler._info(project)
        summary = (await handler._summary(project)) if info else None
        return {"project": project, "info": info, "summary": summary}

    @app.get("/api/apps")
    async def api_apps():
        return {"apps": list_apps()}

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

    app.websocket("/ws")(handler.ws_endpoint)
    return app
