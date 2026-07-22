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
import logging
import re
import shutil
import subprocess
import time
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
from pydantic import BaseModel, Field

from . import agent as agent_mod
from . import cli_adapter as cli_adapter_mod
from . import llm_config as llm_config_mod
from . import projects as projects_mod

_LOG = logging.getLogger("open_edit.serve.app")


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
    # Set on registration; used by the render-job pruner (P5) to drop
    # terminal entries (complete/failed) older than ``_RENDER_JOB_TTL_S``.
    # Not part of the public API contract — kept on the model so the
    # field survives Pydantic serialization roundtrips in tests.
    created_at: float = Field(default_factory=time.time)


class LLMConfigRequest(BaseModel):
    provider: str
    model: str


class LLMConfigResponse(BaseModel):
    provider: str
    model: str
    available_providers: list[str]
    available_models: list[str]


class ChatRequest(BaseModel):
    message: str
    conv_id: str | None = None


# ---------------------------------------------------------------------------
# In-memory render job registry (production: replace with a real queue)
# ---------------------------------------------------------------------------

_RENDER_JOBS: dict[str, RenderJobResponse] = {}

# v1.6 P5: terminal jobs (status in {"complete", "failed"}) older than
# this many seconds are pruned from ``_RENDER_JOBS`` on every register.
# In-flight jobs (status in {"queued", "running"}) are never pruned
# regardless of age. Default 1h matches the spec.
_RENDER_JOB_TTL_S: float = 3600.0


def _prune_render_jobs(now: float | None = None) -> int:
    """Remove terminal entries older than ``_RENDER_JOB_TTL_S``.

    Only entries with ``status in {"complete", "failed"}`` are eligible;
    ``queued`` and ``running`` jobs are kept so an in-flight render is
    never accidentally GC'd while a client is polling for its status.

    Returns the number of entries removed. The ``now`` parameter is
    injectable so tests can fake the clock without monkey-patching
    ``time.time``.
    """
    if now is None:
        now = time.time()
    cutoff = now - _RENDER_JOB_TTL_S
    terminal = ("complete", "failed")
    stale_ids = [
        jid for jid, job in _RENDER_JOBS.items()
        if job.status in terminal and job.created_at < cutoff
    ]
    for jid in stale_ids:
        _RENDER_JOBS.pop(jid, None)
    if stale_ids:
        _LOG.debug("pruned %d terminal render job(s) older than %ss", len(stale_ids), _RENDER_JOB_TTL_S)
    return len(stale_ids)


def _register_job(project_id: str, mode: str) -> RenderJobResponse:
    # Prune first so the new entry doesn't see its own ``created_at``
    # checked against a cutoff that excludes it. Cheap; the dict is
    # small in steady state.
    _prune_render_jobs()
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
    # ``WebSocketDisconnect`` is a subclass of ``Exception`` raised by
    # Starlette when a WS client disconnects. It's not an error — every
    # normal tab close triggers it. Re-raise so Starlette handles the
    # close cleanly, with no fake traceback polluting the operator log
    # and no meaningless 500 JSON response (the WS has no HTTP body).
    if isinstance(exc, WebSocketDisconnect):
        raise exc
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
    """Upload a media file into the project and ingest it via ``AssetStore``.

    The file is written to the project root (so it matches the layout
    ``open_edit init`` expects) and then ingested into the CAS
    (``<project>/.open_edit/assets/<prefix>/<hash>`` + sidecar) via
    ``AssetStore.ingest``. The response carries the new asset's identity
    (including a servable ``url``) so the frontend can play the file
    immediately without an extra round trip.

    v1.4 P0-2: the previous implementation saved to ``.open_edit/inbox/``
    and re-ran ``open_edit init`` — but ``cmd_init`` only scans the
    project root, so the inbox file never reached the CAS and the
    preview player had nothing to play.
    """
    state = await _require_project(project_id)
    project_path = Path(state.path)

    # Save the uploaded file to a stable path (project root). The
    # ``Asset`` model records this as ``original_path`` so the
    # streaming route can pick the right mime type from the
    # filename extension.
    safe_name = Path(file.filename or "upload.bin").name or "upload.bin"
    dest = project_path / safe_name
    try:
        with dest.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        # Ingest via the real storage class. ``AssetStore.ingest``
        # computes the SHA-256, copies the bytes into the CAS, and
        # writes the sidecar JSON. If the file isn't valid media,
        # ffprobe inside ``ingest`` will fail — surface that as a
        # 400 (the client sent something we can't use) rather than
        # a generic 500.
        from open_edit.storage.assets import AssetStore

        assets_dir = project_path / ".open_edit" / "assets"
        store = AssetStore(assets_dir)
        try:
            asset = await asyncio.to_thread(store.ingest, str(dest))
        except subprocess.CalledProcessError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"ffprobe failed on {safe_name!r}: not a recognised media file",
            ) from exc
    finally:
        # Clean up the project-root copy: the CAS now has the bytes
        # and the sidecar carries the original filename, so the root
        # file is redundant. Leaving it behind would mean a re-run of
        # ``open_edit init`` re-ingests it (doubling the work).
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "project_id": project_id,
        "filename": safe_name,
        "status": "ingested",
        "asset": projects_mod._asset_to_info(asset, project_id).model_dump(mode="json"),
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


@app.get("/api/projects/{project_id}/llm-config")
async def get_llm_config(project_id: str) -> LLMConfigResponse:
    """Return the project's LLM provider + model config.

    v1.7: the config is per-project (in ``<project>/.open_edit/config.toml``)
    with env-var fallback. The response also carries the list of available
    providers (so the UI can populate the provider dropdown) and the list
    of available models for the current provider (so the model dropdown
    can be filled). Models come from the adapter's ``available_models()``
    method; for opencode this shells out to ``opencode models`` (cached
    60s by the adapter).
    """
    state = await _require_project(project_id)
    project_path = Path(state.path)
    try:
        cfg = llm_config_mod.load_llm_config(project_path)
    except llm_config_mod.LLMConfigError as exc:
        raise HTTPException(status_code=500, detail=f"invalid LLM config: {exc}") from exc
    try:
        adapter = cli_adapter_mod.get_adapter(cfg.provider)
    except KeyError:
        # The config file references a provider we no longer ship.
        # Fall back to whatever's in the env so the UI can recover.
        available_models: list[str] = []
    else:
        available_models = adapter.available_models()
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        available_providers=cli_adapter_mod.list_adapters(),
        available_models=available_models,
    )


@app.put("/api/projects/{project_id}/llm-config")
async def put_llm_config(project_id: str, req: LLMConfigRequest) -> LLMConfigResponse:
    """Persist the project's LLM provider + model config.

    Validation:
    - ``provider`` must be in the enum ``{anthropic, openai, pi, opencode}``.
      ``antigravity`` is rejected as a provider (A3) — it is a UI label,
      not a backend.
    - ``model`` must be a non-empty string.

    On success, the config is written atomically to
    ``<project>/.open_edit/config.toml`` and the next chat turn picks it up.
    """
    if req.provider not in cli_adapter_mod.list_adapters():
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown provider {req.provider!r}; "
                f"expected one of: {', '.join(cli_adapter_mod.list_adapters())}. "
                f"Note: 'antigravity' is a UI label, not a provider; "
                f"pick 'opencode' as the provider and set model to "
                f"'omniroute/antigravity/<model>'."
            ),
        )
    if not req.model or not req.model.strip():
        raise HTTPException(status_code=400, detail="model must be a non-empty string")
    state = await _require_project(project_id)
    project_path = Path(state.path)
    cfg = llm_config_mod.LLMConfig(provider=req.provider, model=req.model.strip())
    try:
        llm_config_mod.save_llm_config(project_path, cfg)
    except llm_config_mod.LLMConfigError as exc:
        raise HTTPException(status_code=500, detail=f"failed to save LLM config: {exc}") from exc
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        available_providers=cli_adapter_mod.list_adapters(),
        available_models=cli_adapter_mod.get_adapter(cfg.provider).available_models(),
    )


# ---------------------------------------------------------------------------
# Asset streaming (v1.4 P0-2)
# ---------------------------------------------------------------------------

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@app.get("/api/projects/{project_id}/assets/{asset_hash}/file")
async def get_asset_file(project_id: str, asset_hash: str) -> FileResponse:
    """Stream an asset's bytes for the preview player.

    v1.4 P0-2: without this route, the frontend has nothing to set
    ``<video src>`` to and the preview modal is empty. The route
    serves the CAS file with the right ``Content-Type`` (so the
    browser actually plays the response) and supports HTTP Range
    requests (so ``<video>`` can seek — without 206 support, some
    browsers refuse to play).

    The asset hash is validated as a 64-char lowercase hex string
    before being used in a filesystem path so this route can't be
    abused to probe arbitrary files.
    """
    if not _HASH_RE.fullmatch(asset_hash):
        raise HTTPException(status_code=400, detail="invalid asset hash")
    state = await _require_project(project_id)
    project_path = Path(state.path)

    from open_edit.storage.assets import AssetStore

    assets_dir = project_path / ".open_edit" / "assets"
    store = AssetStore(assets_dir)
    asset = store.get(asset_hash)
    if asset is None:
        raise HTTPException(
            status_code=404, detail=f"asset not found: {asset_hash[:12]}"
        )
    cas_path = Path(asset.stored_path)
    if not cas_path.exists():
        raise HTTPException(
            status_code=404, detail=f"asset bytes missing: {asset_hash[:12]}"
        )

    # Pick the mime type from the original filename's extension. The
    # CAS file itself has no extension (it's stored under
    # ``<prefix>/<hash>``), so ``mimetypes.guess_type`` from a bare
    # ``Path("13957...").suffix`` returns ``None``. The original
    # filename (e.g. ``clip_short.mp4``) is preserved in the sidecar.
    media_type = _guess_mime_type(asset)

    return FileResponse(
        str(cas_path),
        media_type=media_type,
        # ``Accept-Ranges: bytes`` is set automatically by Starlette's
        # ``FileResponse`` when the client sends a Range header (it
        # replies with 206 Partial Content). We also set it
        # unconditionally so the browser knows it can ask for a Range
        # up front.
        headers={"Accept-Ranges": "bytes"},
    )


def _guess_mime_type(asset: Asset) -> str:  # noqa: F821
    """Best-effort mime type for a streamed asset.

    Prefers the original filename's extension (``clip_short.mp4`` →
    ``video/mp4``); falls back to ``application/octet-stream`` for
    types we don't know. The stdlib ``mimetypes`` is enough for the
    common formats — we don't need ``python-magic``.
    """
    import mimetypes

    name = asset.original_path or asset.stored_path
    guess, _ = mimetypes.guess_type(name)
    return guess or "application/octet-stream"


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
