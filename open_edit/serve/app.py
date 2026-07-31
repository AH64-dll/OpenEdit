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

This module is deliberately thin: it assembles the router modules
(``routers/``, ``ws/chat.py``) and owns the pieces that must live at
app level — lifespan, middleware, error handlers, the health /
diagnostics endpoints, and the static mount.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from open_edit.kernel.render_service import DEFAULT_RENDER_SERVICE

from . import projects as projects_mod
from .auth import TokenAuthMiddleware, _websocket_auth_error  # noqa: F401 (re-exported for tests)
from .diagnostics import collect_diagnostics
from .diagnostics import get_health as _collect_health
from .logging_setup import CorrelationIdMiddleware, setup_logging
from .routers import assets, config, ops, projects, renders
from .ws import chat as chat_mod


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Structured logging with correlation ids. Idempotent.
    setup_logging()
    # Touch the projects root so GET /api/projects doesn't 500 on a fresh install.
    projects_mod.projects_root()
    # A process ID cannot be safely recovered after an application restart.
    # Preserve the audit trail and make the interrupted state explicit.
    for project in await projects_mod.list_projects():
        DEFAULT_RENDER_SERVICE.recover(Path(project.path))
    yield


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


@app.get("/api/health")
async def get_health() -> dict[str, str]:
    """Health check endpoint returning {"status": "ok"}."""
    return {"status": "ok"}


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
# Routers (split out of this module in Task 5.2 — see ``routers/`` and
# ``ws/chat.py``). URL prefixes are unchanged.
# ---------------------------------------------------------------------------

app.include_router(projects.router)
app.include_router(renders.router)
app.include_router(ops.router)
app.include_router(config.router)
app.include_router(assets.router)
app.include_router(chat_mod.router)


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
