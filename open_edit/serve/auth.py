"""Authentication, WebSocket auth, and rate limiting for the Open Edit server.

Extracted verbatim from ``serve/app.py`` when the app was split into
routers (Task 5.2). Auth is only enforced when ``OPEN_EDIT_TOKEN`` is
set (read at request time) AND the client is not localhost, preserving
the open/local behaviour the desktop integration relies on.
"""
from __future__ import annotations

import collections
import os
import secrets
import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, WebSocket
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .errors import ErrorCodes, make_error

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


# Simple in-memory sliding-window rate limiting (module-level so all
# routers share the same window).

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
