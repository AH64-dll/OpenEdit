"""FastAPI app for the Open Edit server.

Routes
------
- ``GET  /api/projects``                          → list projects
- ``POST /api/projects``  body={name}             → create new project
- ``GET  /api/projects/{project_id}``             → full project state
- ``POST /api/projects/{project_id}/ingest``      → upload + ingest media
- ``POST /api/projects/{project_id}/render``      → trigger render (returns job_id)
- ``GET  /api/projects/{project_id}/renders``     → list past renders
- ``GET  /api/projects/{project_id}/thumbnail``   → serve a thumbnail
- ``WS   /api/chat/{project_id}``                 → streaming chat

The static frontend is served from ``open_edit/serve/static/`` at ``/``.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent as agent_mod
from . import projects as projects_mod


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str


class RenderRequest(BaseModel):
    mode: str = "proxy"  # "proxy" | "final"


class RenderJobResponse(BaseModel):
    job_id: str
    project_id: str
    mode: str
    status: str  # "queued" | "running" | "complete" | "failed"
    output_path: str | None = None
    error: str | None = None


class ChatRequest(BaseModel):
    message: str
    conv_id: str | None = None


# ---------------------------------------------------------------------------
# In-memory render job registry (production: replace with a real queue)
# ---------------------------------------------------------------------------

_RENDER_JOBS: dict[str, RenderJobResponse] = {}


def _register_job(project_id: str, mode: str) -> RenderJobResponse:
    job_id = uuid.uuid4().hex[:12]
    job = RenderJobResponse(
        job_id=job_id,
        project_id=project_id,
        mode=mode,
        status="queued",
    )
    _RENDER_JOBS[job_id] = job
    return job


async def _run_render_job(job: RenderJobResponse, project_path: Path) -> None:
    """Run ``open_edit render --mode <mode>`` in the background."""
    job.status = "running"
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["open_edit", "render", "--mode", job.mode],
            cwd=str(project_path),
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        # Parse output path from last non-empty stdout line
        last_line = ""
        for line in reversed(proc.stdout.splitlines()):
            if line.strip():
                last_line = line.strip()
                break
        job.output_path = last_line if ("/" in last_line or "\\" in last_line) else ""
        job.status = "complete"
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Touch the projects root so GET /api/projects doesn't 500 on a fresh install.
    projects_mod.projects_root()
    yield


app = FastAPI(
    title="Open Edit Server",
    version="0.1.0",
    description="Chat-driven backend for the Open Edit AI-native video editor.",
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Error contract: v1.4 returns ``{"error": "..."}`` (not FastAPI's default
# ``{"detail": "..."}``). This is the wire shape the frontend parses; see
# ``static/app.js``. We register handlers for HTTPException and for any
# uncaught exception so a raw 500 traceback is never leaked.
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def _http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": msg},
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
    # Log so the server operator can see it; return a constant generic
    # message so we don't leak internals (paths, SQL fragments, etc.)
    # to the client. The traceback goes to stderr; the client only sees
    # a fixed string.
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"error": "internal server error"},
    )


# ---------------------------------------------------------------------------
# REST: projects
# ---------------------------------------------------------------------------

@app.get("/api/projects")
async def get_projects() -> list[projects_mod.ProjectInfo]:
    return await projects_mod.list_projects()


@app.post("/api/projects", status_code=201)
async def post_create_project(req: CreateProjectRequest) -> projects_mod.ProjectInfo:
    try:
        return await projects_mod.create_project(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> projects_mod.ProjectState:
    try:
        return await projects_mod.get_project_state(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/projects/{project_id}/ingest", status_code=202)
async def post_ingest(
    project_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload a media file into the project and re-run ``open_edit init``."""
    state = await _require_project(project_id)
    project_path = Path(state.path)

    # Save the uploaded file to the project's inbox folder.
    inbox = project_path / ".open_edit" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / Path(file.filename or "upload.bin").name
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    # Re-run `open_edit init` to ingest the new file.
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["open_edit", "init"],
            cwd=str(project_path),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="`open_edit` CLI not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"`open_edit init` failed: {exc.stderr.strip() or exc.stdout.strip()}",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="ingest timed out") from exc

    return {
        "project_id": project_id,
        "filename": dest.name,
        "status": "ingested",
    }


@app.post("/api/projects/{project_id}/render", status_code=202)
async def post_render(project_id: str, req: RenderRequest) -> RenderJobResponse:
    """Trigger a render in the background. Returns the job immediately."""
    state = await _require_project(project_id)
    if req.mode not in ("proxy", "final"):
        raise HTTPException(status_code=400, detail="mode must be 'proxy' or 'final'")

    job = _register_job(project_id, req.mode)
    project_path = Path(state.path)
    asyncio.create_task(_run_render_job(job, project_path))
    return job


@app.get("/api/projects/{project_id}/renders")
async def get_renders(project_id: str) -> list[dict[str, Any]]:
    await _require_project(project_id)
    return await projects_mod.list_renders(project_id)


@app.get("/api/projects/{project_id}/render_jobs/{job_id}")
async def get_render_job(project_id: str, job_id: str) -> RenderJobResponse:
    """Poll a background render job's status."""
    await _require_project(project_id)
    job = _RENDER_JOBS.get(job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"render job not found: {job_id}")
    return job


@app.get("/api/projects/{project_id}/thumbnail")
async def get_thumbnail(project_id: str) -> Any:
    """Serve the project's thumbnail.

    Looks for ``.open_edit/thumbnail.png`` (or .jpg) in the project folder.
    """
    state = await _require_project(project_id)
    project_path = Path(state.path)
    for name in ("thumbnail.png", "thumbnail.jpg", "thumbnail.jpeg"):
        f = project_path / ".open_edit" / name
        if f.exists():
            return FileResponse(str(f))
    raise HTTPException(status_code=404, detail="no thumbnail available")


# ---------------------------------------------------------------------------
# WebSocket: chat
# ---------------------------------------------------------------------------

@app.websocket("/api/chat/{project_id}")
async def ws_chat(websocket: WebSocket, project_id: str) -> None:
    """Stream AgentEvents for a chat conversation.

    Protocol (server -> client)::

        {"type": "text",         "text": "..."}
        {"type": "tool_start",   "name": "...", "input": {...}}
        {"type": "tool_result",  "name": "...", "result": {...}}
        {"type": "render",       "path": "...", "mode": "proxy"|"final"}
        {"type": "error",        "message": "..."}
        {"type": "done",         "stop_reason": "..."}

    Protocol (client -> server)::

        {"message": "...", "conv_id": "optional"}

    On connect, the server sends a ``ready`` event so the client knows the
    project was found and the WS is wired up.
    """
    # Verify project exists before accepting.
    try:
        await _require_project(project_id)
    except HTTPException as exc:
        await websocket.accept()
        # The detail already starts with "project not found: " (set by
        # projects.get_project_state's KeyError) and includes the recovery
        # hint — just forward it.
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": detail,
        }))
        await websocket.close(code=4404, reason="project not found")
        return

    await websocket.accept()
    await websocket.send_text(json.dumps({"type": "ready", "project_id": project_id}))

    # Per-connection conversation cache. In-memory only — persisted via
    # append_to_conversation() if a conv_id is provided by the client.
    conversations: dict[str, list[dict[str, Any]]] = {}

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "invalid JSON; expected {\"message\": \"...\"}",
                }))
                continue

            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "missing 'message' field",
                }))
                continue

            conv_id = payload.get("conv_id") or agent_mod.new_conversation_id()

            # Load conversation from disk (if any) and cache it.
            if conv_id not in conversations:
                conversations[conv_id] = agent_mod.load_conversation(project_id, conv_id)

            history = conversations[conv_id]

            # Run the agent turn and stream events back to the client.
            try:
                async for event in agent_mod.run_agent_turn(
                    project_id=project_id,
                    user_message=message,
                    conversation_history=history,
                    conv_id=conv_id,
                ):
                    await websocket.send_text(json.dumps(event, default=str))
            except Exception as exc:
                # Never crash the WS — surface as error and keep the loop open.
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"agent turn crashed: {exc}",
                }))
                await websocket.send_text(json.dumps({
                    "type": "done",
                    "stop_reason": "error",
                }))
    except WebSocketDisconnect:
        return
    except Exception:
        # Catch-all so the server process never dies on a WS bug.
        return


# ---------------------------------------------------------------------------
# Static frontend (mount LAST so it doesn't shadow /api routes)
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
else:
    @app.get("/")
    async def root_placeholder() -> JSONResponse:
        return JSONResponse({
            "name": "Open Edit Server",
            "status": "running",
            "note": "static/ directory not found; mount the frontend there to serve it at /",
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_project(project_id: str) -> projects_mod.ProjectState:
    """Return the project state or raise 404."""
    try:
        return await projects_mod.get_project_state(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
