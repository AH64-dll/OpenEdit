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
import collections
import json
import logging
import os
import re
import secrets
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import (
    BackgroundTasks,
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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from . import agent as agent_mod
from . import cli_adapter as cli_adapter_mod
from . import llm_config as llm_config_mod
from . import projects as projects_mod
from .diagnostics import collect_diagnostics
from .diagnostics import get_health as _collect_health
from .errors import ErrorCodes, make_error
from .logging_setup import CorrelationIdMiddleware, setup_logging
from open_edit.kernel.render_service import DEFAULT_RENDER_SERVICE
from .review_mode import auto_proxy_enabled, is_review_only

_LOG = logging.getLogger("open_edit.serve.app")

_UPLOAD_CHUNK_SIZE = 1024 * 1024
_DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024


def _max_upload_bytes() -> int:
    """Return the configured per-file limit without accepting unsafe values."""
    raw = os.environ.get("OPEN_EDIT_MAX_UPLOAD_BYTES", "").strip()
    if not raw:
        return _DEFAULT_MAX_UPLOAD_BYTES
    try:
        value = int(raw)
    except ValueError:
        _LOG.warning("invalid OPEN_EDIT_MAX_UPLOAD_BYTES value; using default")
        return _DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else _DEFAULT_MAX_UPLOAD_BYTES


class UploadTooLargeError(ValueError):
    """Raised when a streamed upload exceeds its configured per-file limit."""


def _copy_upload_limited(source: Any, destination: Path, max_bytes: int) -> None:
    """Copy a spooled upload without blocking the event loop or exceeding a cap."""
    copied = 0
    with destination.open("xb") as target:
        while chunk := source.read(_UPLOAD_CHUNK_SIZE):
            copied += len(chunk)
            if copied > max_bytes:
                raise UploadTooLargeError(f"file exceeds the {max_bytes}-byte upload limit")
            target.write(chunk)
    if copied == 0:
        raise ValueError("zero-byte uploads are not valid media")


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str


class RenderRequest(BaseModel):
    mode: str = "proxy"  # "proxy" | "final" | "overlay"
    expected_revision: int | None = None
    encoder: str | None = None  # "gpu" (default) | "cpu"


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
    graph_revision: int | None = None
    edit_graph_hash: str | None = None


class TimelineCommandRequest(BaseModel):
    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int | None = None
    author: str = "user"


class LLMConfigRequest(BaseModel):
    provider: str
    model: str


class LLMConfigResponse(BaseModel):
    provider: str
    model: str
    available_providers: list[str]
    available_models: list[str]
    provider_capabilities: list[dict[str, Any]] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    conv_id: str | None = None


class CreateNoteRequest(BaseModel):
    text: str
    t_start: float
    t_end: float | None = None
    source: str = "typed"


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


_RENDER_TASKS: dict[str, asyncio.Task] = {}

# Durable scheduling is the canonical render path.  The legacy dictionaries
# above remain temporarily for backwards-compatible helper tests only.
_RENDER_SERVICE = DEFAULT_RENDER_SERVICE


async def _run_render_job(job: RenderJobResponse, project_path: Path) -> None:
    """Run ``open_edit render --mode <mode>`` in the background."""
    proc = None
    job.status = "running"
    _RENDER_TASKS[job.job_id] = asyncio.current_task()
    try:
        proc = await asyncio.create_subprocess_exec(
            "open_edit", "render", "--mode", job.mode,
            cwd=str(project_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1800)
        except asyncio.TimeoutError:
            proc.terminate()
            await proc.wait()
            raise
        if proc.returncode != 0:
            raise RuntimeError(f"render failed (exit {proc.returncode}): {stderr.decode(errors='replace')}")
        last_line = ""
        for line in reversed(stdout.decode(errors="replace").splitlines()):
            if line.strip():
                last_line = line.strip()
                break
        job.output_path = last_line if ("/" in last_line or "\\" in last_line) else ""
        job.status = "complete"
    except asyncio.CancelledError:
        job.status = "failed"
        job.error = "cancelled"
        if proc is not None:
            proc.terminate()
            await proc.wait()
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        if proc is not None:
            proc.terminate()
            try:
                await proc.wait()
            except Exception:
                pass
    finally:
        _RENDER_TASKS.pop(job.job_id, None)


# ---------------------------------------------------------------------------
# Rate limiting (simple in-memory sliding window)
# ---------------------------------------------------------------------------

_RATE_LIMITS: dict[str, collections.deque] = {}


def _check_rate_limit(key: str, max_requests: int = 10, window_sec: float = 60.0) -> None:
    now = time.time()
    if key not in _RATE_LIMITS:
        _RATE_LIMITS[key] = collections.deque()
    window = _RATE_LIMITS[key]
    while window and window[0] < now - window_sec:
        window.popleft()
    if len(window) >= max_requests:
        raise HTTPException(status_code=429, detail="rate limit exceeded. try again later.")
    window.append(now)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Structured logging with correlation ids. Idempotent.
    setup_logging()
    # Touch the projects root so GET /api/projects doesn't 500 on a fresh install.
    projects_mod.projects_root()
    # A process ID cannot be safely recovered after an application restart.
    # Preserve the audit trail and make the interrupted state explicit.
    for project in await projects_mod.list_projects():
        _RENDER_SERVICE.recover(Path(project.path))
    yield


# Local clients are always exempt from token auth. ``testclient`` is the
# host Starlette's TestClient uses; a ``None`` client means a unix socket.
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

# Paths that never require auth (liveness must always be reachable).
_AUTH_EXEMPT_PATHS = frozenset({"/health"})


def _is_localhost(request: Request) -> bool:
    client = request.client
    if client is None:
        return True
    return client.host in _LOCAL_HOSTS


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip() or None
    return request.query_params.get("token") or None


def _is_localhost_websocket(websocket: WebSocket) -> bool:
    client = websocket.client
    return client is None or client.host in _LOCAL_HOSTS


def _websocket_auth_error(websocket: WebSocket) -> tuple[int, str] | None:
    """Validate remote chat connections before ``accept()``.

    HTTP middleware does not run for WebSocket upgrades. Remote operation is
    therefore deliberately opt-in: it requires both ``OPEN_EDIT_TOKEN`` and
    an explicit comma-separated ``OPEN_EDIT_ALLOWED_ORIGINS`` allow-list.
    Local desktop connections retain the documented localhost bypass.
    """
    if _is_localhost_websocket(websocket):
        return None
    expected_token = os.environ.get("OPEN_EDIT_TOKEN", "").strip()
    if not expected_token:
        return 4401, "remote WebSocket access is disabled: OPEN_EDIT_TOKEN is not configured"
    supplied_token = websocket.query_params.get("token", "")
    if not secrets.compare_digest(supplied_token, expected_token):
        return 4401, "authentication required"
    allowed_origins = {
        origin.strip() for origin in os.environ.get("OPEN_EDIT_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }
    origin = websocket.headers.get("origin", "")
    if not allowed_origins or origin not in allowed_origins:
        return 4403, "origin is not allowed"
    return None


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Fail-safe bearer-token auth with a localhost bypass.

    Auth is only enforced when ``OPEN_EDIT_TOKEN`` is set (read at request
    time) AND the client is not localhost. This preserves the open/local
    behaviour the desktop integration relies on.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in _AUTH_EXEMPT_PATHS or _is_localhost(request):
            return await call_next(request)
        token = os.environ.get("OPEN_EDIT_TOKEN", "").strip()
        if not token:
            return await call_next(request)
        if _extract_token(request) != token:
            return JSONResponse(
                status_code=401,
                content=make_error(
                    ErrorCodes.AUTH_REQUIRED,
                    "Authentication required",
                    retriable=False,
                ),
            )
        return await call_next(request)


app = FastAPI(
    title="Open Edit Server",
    version="0.1.0",
    description="Chat-driven backend for the Open Edit AI-native video editor.",
    lifespan=_lifespan,
)

app.add_middleware(TokenAuthMiddleware)
app.add_middleware(CorrelationIdMiddleware)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness/health check. Never requires auth and never raises."""
    return _collect_health()


@app.get("/diagnostics")
async def diagnostics() -> dict[str, Any]:
    """Redacted system diagnostics. Protected by token auth (localhost exempt)."""
    return collect_diagnostics()


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
async def post_create_project(req: CreateProjectRequest) -> Any:
    try:
        return await projects_mod.create_project(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content=make_error(
                ErrorCodes.PROJECT_INITIALIZATION_FAILED,
                str(exc),
                retriable=True,
            ),
        )


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> projects_mod.ProjectState:
    try:
        return await projects_mod.get_project_state(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/projects/{project_id}/ingest", status_code=202)
async def post_ingest(
    project_id: str,
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> dict[str, Any]:
    """Ingest one or more files under the canonical ``files`` form field.

    Each file is isolated in a unique inbox path and bounded while streaming.
    The operation intentionally allows partial success: a bad file never
    removes already ingested assets from the same user selection.
    """
    state = await _require_project(project_id)
    project_path = Path(state.path)
    from open_edit.storage.assets import AssetStore

    assets_dir = project_path / ".open_edit" / "assets"
    inbox_dir = project_path / ".open_edit" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    store = AssetStore(assets_dir)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    max_bytes = _max_upload_bytes()

    for upload in files:
        safe_name = Path(upload.filename or "upload.bin").name or "upload.bin"
        # Preserve the original basename in asset metadata while ensuring
        # concurrent uploads never share a temporary source path.
        temp_path = inbox_dir / f"{uuid.uuid4().hex}_{safe_name}"
        try:
            await asyncio.to_thread(_copy_upload_limited, upload.file, temp_path, max_bytes)
            asset = await asyncio.to_thread(store.ingest, str(temp_path), False)
        except subprocess.CalledProcessError as exc:
            _LOG.info("rejected invalid media upload %s", safe_name)
            rejected.append({"filename": safe_name, "error": "not a recognised media file"})
        except UploadTooLargeError as exc:
            rejected.append({"filename": safe_name, "error": str(exc)})
        except ValueError as exc:
            rejected.append({"filename": safe_name, "error": str(exc)})
        except OSError:
            _LOG.exception("failed to ingest upload %s", safe_name)
            rejected.append({"filename": safe_name, "error": "upload processing failed"})
        else:
            asset_info = projects_mod._asset_to_info(asset, project_id).model_dump(mode="json")
            accepted.append({
                "filename": safe_name,
                "asset": asset_info,
                "transcribing": asset.has_audio,
            })
            if asset.has_audio:
                background_tasks.add_task(
                    _transcribe_in_background, assets_dir, asset.asset_hash, asset.stored_path
                )
        finally:
            await asyncio.to_thread(temp_path.unlink, missing_ok=True)
            await upload.close()

    return {
        "project_id": project_id,
        "accepted": accepted,
        "rejected": rejected,
    }


def _transcribe_in_background(
    assets_dir: Path, asset_hash: str, stored_path: str
) -> None:
    """Background Whisper pass: transcribe and patch the asset sidecar."""
    try:
        from open_edit.storage.assets import AssetStore
        from open_edit.storage.transcription import transcribe

        alignment = transcribe(Path(stored_path))
        AssetStore(assets_dir).update_alignment(asset_hash, alignment)
        _LOG.info(
            "background transcription done: %s (%d words)",
            asset_hash[:8],
            len(alignment),
        )
    except Exception as exc:  # never break the response that already shipped
        _LOG.warning(
            "background transcription failed for %s: %s", asset_hash[:8], exc
        )


@app.post("/api/projects/{project_id}/render", status_code=202)
async def post_render(project_id: str, req: RenderRequest) -> RenderJobResponse:
    """Trigger a render in the background. Returns the job immediately."""
    _check_rate_limit(f"render:{project_id}", max_requests=5, window_sec=300)
    state = await _require_project(project_id)
    if req.mode not in ("proxy", "final", "overlay"):
        raise HTTPException(status_code=400, detail="mode must be 'proxy', 'final', or 'overlay'")

    project_path = Path(state.path)
    from open_edit.kernel.render_service import RenderEnqueueError

    encoder = (req.encoder or "").strip().lower() or None
    if encoder not in (None, "gpu", "cpu"):
        raise HTTPException(status_code=400, detail="encoder must be 'gpu' or 'cpu'")

    try:
        job = _RENDER_SERVICE.enqueue(
            project_id,
            project_path,
            req.mode,
            expected_revision=req.expected_revision,
            encoder_backend=encoder,
        )
    except RenderEnqueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RenderJobResponse(
        job_id=job.job_id, project_id=job.project_id, mode=job.mode,
        status=job.status, output_path=job.output_path, error=job.error,
        created_at=job.created_at, graph_revision=job.graph_revision,
        edit_graph_hash=job.edit_graph_hash,
    )


@app.get("/api/projects/{project_id}/renders")
async def get_renders(project_id: str) -> list[dict[str, Any]]:
    await _require_project(project_id)
    return await projects_mod.list_renders(project_id)


@app.post("/api/projects/{project_id}/render_jobs/{job_id}/cancel")
async def cancel_render_job(project_id: str, job_id: str) -> dict:
    """Cancel a running render job."""
    await _require_project(project_id)
    state = await _require_project(project_id)
    job = await _RENDER_SERVICE.cancel(Path(state.path), job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"render job not found: {job_id}")
    if job.status not in ("queued", "running", "cancelling"):
        return {"status": "already_terminal", "job_status": job.status}
    return {"status": "cancelled"}


@app.get("/api/projects/{project_id}/render_jobs/{job_id}")
async def get_render_job(project_id: str, job_id: str) -> RenderJobResponse:
    """Poll a background render job's status."""
    await _require_project(project_id)
    state = await _require_project(project_id)
    job = _RENDER_SERVICE.get(Path(state.path), job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"render job not found: {job_id}")
    return RenderJobResponse(
        job_id=job.job_id, project_id=job.project_id, mode=job.mode,
        status=job.status, output_path=job.output_path, error=job.error,
        created_at=job.created_at, graph_revision=job.graph_revision,
        edit_graph_hash=job.edit_graph_hash,
    )


@app.get("/api/projects/{project_id}/renders/{render_id}/file")
async def get_render_file(project_id: str, render_id: str) -> FileResponse:
    """Stream a rendered MP4 for in-browser preview (HTTP Range supported)."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    mp4_path = _resolve_render_mp4(project_path, render_id)
    if mp4_path is None:
        raise HTTPException(status_code=404, detail=f"render not found: {render_id}")
    return FileResponse(
        str(mp4_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@app.post("/api/projects/{project_id}/notes", status_code=201)
async def post_project_note(project_id: str, req: CreateNoteRequest) -> JSONResponse:
    """Append a timestamp-anchored review note (readable by MCP get_pending_notes)."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    t_start = max(0.0, float(req.t_start))
    t_end = float(req.t_end) if req.t_end is not None else t_start
    if t_end < t_start:
        t_end = t_start

    from datetime import datetime, timezone

    from open_edit.storage.notes import (
        NoteSource,
        NoteStatus,
        NotesStore,
        ReviewNote,
        TimestampAnchor,
    )

    notes_db = project_path / "notes.db"
    store = NotesStore(notes_db)
    db_path = project_path / ".open_edit" / "edit_graph.db"
    note_project_id = project_id
    if db_path.exists():
        try:
            from open_edit.storage.edit_graph import EditGraphStore
            note_project_id = EditGraphStore(db_path).project_id
        except Exception:
            pass
    note = ReviewNote(
        note_id=uuid.uuid4().hex,
        project_id=note_project_id,
        anchor=TimestampAnchor(t_start=t_start, t_end=t_end),
        text=text,
        source=NoteSource.typed if req.source == "typed" else NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(note)
    return JSONResponse({
        "note_id": note.note_id,
        "t_start": t_start,
        "t_end": t_end,
        "text": text,
        "status": note.status.value,
    })


def _resolve_render_mp4(project_path: Path, render_id: str) -> Path | None:
    """Locate a render MP4 under the project; reject path escape."""
    if not render_id or ".." in render_id or "/" in render_id or "\\" in render_id:
        return None
    if ".melt" in render_id.lower():
        return None
    job = _RENDER_SERVICE.get(project_path, render_id)
    if job is not None and job.output_path:
        candidate = Path(job.output_path).resolve()
        if (
            candidate.is_file()
            and _path_under_project(candidate, project_path)
            and projects_mod._is_complete_render_mp4(candidate)
        ):
            return candidate
    renders_dir = (project_path / ".open_edit" / "renders").resolve()
    for pattern in (f"{render_id}.mp4", f"*{render_id}*.mp4"):
        for hit in renders_dir.glob(pattern):
            resolved = hit.resolve()
            if (
                resolved.is_file()
                and _path_under_project(resolved, project_path)
                and projects_mod._is_complete_render_mp4(resolved)
            ):
                return resolved
    return None


def _path_under_project(path: Path, project_path: Path) -> bool:
    try:
        path.resolve().relative_to(project_path.resolve())
        return True
    except ValueError:
        return False


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


@app.get("/api/health")
async def get_health() -> dict[str, str]:
    """Health check endpoint returning {"status": "ok"}."""
    return {"status": "ok"}


@app.get("/api/ui-config")
async def get_ui_config() -> dict[str, Any]:
    """Frontend mode flags (review studio vs full agent UI)."""
    return {
        "mode": "review" if is_review_only() else "full",
        "review_only": is_review_only(),
        "auto_proxy": auto_proxy_enabled(),
    }


def _require_agent_mode() -> None:
    if is_review_only():
        raise HTTPException(status_code=404, detail="not available in review-only mode")


@app.get("/api/projects/{project_id}/llm-config")
async def get_llm_config(project_id: str) -> LLMConfigResponse:
    """Return the project's LLM provider + model config."""
    _require_agent_mode()
    state = await _require_project(project_id)
    project_path = Path(state.path)
    from . import providers as providers_mod

    try:
        cfg = llm_config_mod.load_llm_config(project_path)
    except llm_config_mod.LLMConfigError as exc:
        raise HTTPException(status_code=500, detail=f"invalid LLM config: {exc}") from exc
    available_models = await asyncio.to_thread(providers_mod.get_provider_models, cfg.provider)
    capabilities = [
        {
            "id": spec.name,
            "label": spec.label,
            "agent_mode": spec.agent_mode,
            "supports_tools": spec.supports_tools,
            "supports_sessions": spec.supports_sessions,
            "context_strategy": spec.context_strategy,
        }
        for spec in providers_mod.list_visible_providers()
    ]
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        available_providers=[s.name for s in providers_mod.list_visible_providers()],
        available_models=available_models,
        provider_capabilities=capabilities,
    )


@app.put("/api/projects/{project_id}/llm-config")
async def put_llm_config(project_id: str, req: LLMConfigRequest) -> LLMConfigResponse:
    """Persist the project's LLM provider + model config."""
    _require_agent_mode()
    from . import providers as providers_mod

    visible = [s.name for s in providers_mod.list_visible_providers()]
    if req.provider not in visible:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown provider {req.provider!r}; "
                f"expected one of: {', '.join(visible)}."
            ),
        )
    if not req.model or not req.model.strip():
        raise HTTPException(status_code=400, detail="model must be a non-empty string")
    state = await _require_project(project_id)
    project_path = Path(state.path)
    cfg = llm_config_mod.LLMConfig(provider=req.provider, model=req.model.strip())
    try:
        llm_config_mod.save_llm_config(project_path, cfg)
    except (llm_config_mod.LLMConfigError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"failed to save LLM config: {exc}") from exc
    avail_models = await asyncio.to_thread(providers_mod.get_provider_models, cfg.provider)
    capabilities = [
        {
            "id": spec.name,
            "label": spec.label,
            "agent_mode": spec.agent_mode,
            "supports_tools": spec.supports_tools,
            "supports_sessions": spec.supports_sessions,
            "context_strategy": spec.context_strategy,
        }
        for spec in providers_mod.list_visible_providers()
    ]
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        available_providers=visible,
        available_models=avail_models,
        provider_capabilities=capabilities,
    )


class SaveKeyRequest(BaseModel):
    provider: str
    key: str


@app.get("/api/runtimes")
async def list_discovered_runtimes() -> JSONResponse:
    """Return auto-discovered CLI runtimes across system PATH and GUI directories."""
    _require_agent_mode()
    from .runtimes.registry import discover_runtimes
    runtimes = discover_runtimes()
    return JSONResponse({"runtimes": [r.to_dict() for r in runtimes]})


@app.get("/api/settings/keys")
async def get_settings_keys() -> JSONResponse:
    """Return masked status summary of API keys (from env or ~/.open_edit/keys.json)."""
    _require_agent_mode()
    from .runtimes.keys_store import get_masked_keys_summary
    return JSONResponse(get_masked_keys_summary())


@app.put("/api/settings/keys")
async def put_settings_key(req: SaveKeyRequest) -> JSONResponse:
    """Save an API key to ~/.open_edit/keys.json with 0600 permissions."""
    _require_agent_mode()
    _check_rate_limit("settings:keys", max_requests=10, window_sec=60)
    from .runtimes.keys_store import save_stored_key, get_masked_keys_summary
    provider = req.provider.strip().lower()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")
    save_stored_key(provider, req.key)
    return JSONResponse({
        "status": "saved",
        "provider": provider,
        "keys": get_masked_keys_summary(),
    })


# ---------------------------------------------------------------------------
# Edit graph CRUD (Wave 1.4)
# ---------------------------------------------------------------------------

class UpdateOpStatusRequest(BaseModel):
    status: str  # "applied" | "reverted" | "superseded"
    expected_revision: int | None = None


class ReorderOpsRequest(BaseModel):
    op_ids: list[str]  # ordered list of edit_ids in desired sequence
    expected_revision: int | None = None


@app.post("/api/projects/{project_id}/ops")
async def post_timeline_command(
    project_id: str, req: TimelineCommandRequest,
) -> JSONResponse:
    """Apply a manual timeline command through the shared edit-graph service."""
    state = await _require_project(project_id)
    author = req.author if req.author in ("ai", "user") else "user"
    from open_edit.kernel.edit_graph_service import EditGraphCommandError, apply_command
    from open_edit.storage.edit_graph import GraphRevisionConflict

    try:
        result = apply_command(
            Path(state.path),
            req.command,
            req.params,
            author=author,  # type: ignore[arg-type]
            expected_revision=req.expected_revision,
        )
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EditGraphCommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@app.patch("/api/projects/{project_id}/ops/{edit_id}/status")
async def update_op_status(
    project_id: str, edit_id: str, req: UpdateOpStatusRequest,
) -> JSONResponse:
    if req.status not in ("applied", "reverted", "superseded"):
        raise HTTPException(
            status_code=400,
            detail=f"invalid status {req.status!r}; expected applied, reverted, or superseded",
        )
    state = await _require_project(project_id)
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict

    store = EditGraphStore(db_path)
    ops = store.load_all()
    if not any(o.edit_id == edit_id for o in ops):
        raise HTTPException(status_code=404, detail=f"op {edit_id} not found")
    try:
        revision = store.update_status(edit_id, req.status, expected_revision=req.expected_revision)
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"edit_id": edit_id, "status": req.status, "graph_revision": revision})


@app.delete("/api/projects/{project_id}/ops/{edit_id}")
async def delete_op(project_id: str, edit_id: str, expected_revision: int | None = None) -> JSONResponse:
    """Revert a public operation without destroying durable edit history.

    Hard deletion remains a storage-maintenance operation.  UI/API callers
    must use a reversible status transition so later operations keep their
    references and the graph remains auditable.
    """
    state = await _require_project(project_id)
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict

    store = EditGraphStore(db_path)
    ops = store.load_all()
    if not any(op.edit_id == edit_id for op in ops):
        raise HTTPException(status_code=404, detail=f"op {edit_id} not found")
    if any(op.parent_id == edit_id for op in ops):
        raise HTTPException(
            status_code=409,
            detail="operation is referenced by later edits; revert dependent edits first",
        )
    try:
        revision = store.update_status(
            edit_id, "reverted", reason="api_revert", expected_revision=expected_revision,
        )
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"edit_id": edit_id, "status": "reverted", "deleted": False, "graph_revision": revision})


@app.post("/api/projects/{project_id}/ops/reorder")
async def reorder_ops(
    project_id: str, req: ReorderOpsRequest,
) -> JSONResponse:
    state = await _require_project(project_id)
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict

    store = EditGraphStore(db_path)
    try:
        revision = store.reorder_all(req.op_ids, expected_revision=req.expected_revision)
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"reordered": True, "graph_revision": revision})


@app.get("/api/llm/providers/{provider}/models")
async def get_provider_models(provider: str) -> dict[str, list[str]]:
    """Return available models for a given provider."""
    _require_agent_mode()
    from . import providers as providers_mod
    models = await asyncio.to_thread(providers_mod.get_provider_models, provider)
    return {"models": models}


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
    """Stream AgentEvents for a chat conversation."""
    if is_review_only():
        await websocket.close(code=4404, reason="review-only mode")
        return
    # HTTP middleware does not protect WebSocket upgrades. Authenticate and
    # validate the Origin before accepting so unauthorized clients cannot
    # receive project state or submit a chat turn.
    auth_error = _websocket_auth_error(websocket)
    if auth_error is not None:
        code, _reason = auth_error
        await websocket.close(code=code, reason=_reason)
        return

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
    current_turn_task: asyncio.Task | None = None

    async def _cancel_turn():
        nonlocal current_turn_task
        if current_turn_task and not current_turn_task.done():
            current_turn_task.cancel()
            try:
                await current_turn_task
            except (asyncio.CancelledError, Exception):
                pass
        current_turn_task = None

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            max_message_bytes = int(os.environ.get("OPEN_EDIT_WS_MAX_MESSAGE_BYTES", "65536"))
            if len(raw.encode("utf-8")) > max_message_bytes:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"message exceeds {max_message_bytes}-byte limit",
                }))
                await websocket.close(code=4409, reason="message too large")
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "invalid JSON; expected {\"message\": \"...\"}",
                }))
                continue

            if not isinstance(payload, dict):
                continue

            msg_type = payload.get("type")
            if msg_type in ("cancel", "stop"):
                await _cancel_turn()
                await websocket.send_text(json.dumps({"type": "cancelled"}))
                continue

            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "missing 'message' field",
                }))
                continue

            client_host = websocket.client.host if websocket.client else "local"
            try:
                _check_rate_limit(
                    f"ws:{client_host}:{project_id}",
                    max_requests=int(os.environ.get("OPEN_EDIT_WS_MAX_MESSAGES", "20")),
                    window_sec=float(os.environ.get("OPEN_EDIT_WS_WINDOW_SECONDS", "60")),
                )
            except HTTPException:
                await websocket.send_text(json.dumps({
                    "type": "error", "message": "rate limit exceeded. try again later.",
                }))
                await websocket.close(code=4429, reason="rate limited")
                return

            conv_id = payload.get("conv_id") or agent_mod.new_conversation_id()

            # Load conversation from disk (if any) and cache it.
            if conv_id not in conversations:
                conversations[conv_id] = agent_mod.load_conversation(project_id, conv_id)

            history = conversations[conv_id]

            await _cancel_turn()

            async def _run_agent_turn_task(user_msg: str, cid: str, hist: list[dict[str, Any]]):
                try:
                    async for event in agent_mod.run_agent_turn(
                        project_id=project_id,
                        user_message=user_msg,
                        conversation_history=hist,
                        conv_id=cid,
                        should_cancel=lambda: asyncio.current_task() is not None and asyncio.current_task().cancelling() > 0,
                    ):
                        await websocket.send_text(json.dumps(event, default=str))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"agent turn crashed: {exc}",
                    }))
                    await websocket.send_text(json.dumps({
                        "type": "done",
                        "stop_reason": "error",
                    }))

            current_turn_task = asyncio.create_task(_run_agent_turn_task(message, conv_id, history))
    except WebSocketDisconnect:
        await _cancel_turn()
        return
    except Exception:
        await _cancel_turn()
        return
    finally:
        await _cancel_turn()


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
