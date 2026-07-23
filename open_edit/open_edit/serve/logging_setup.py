"""Structured logging with correlation IDs for the Open Edit server.

This module gives the server three things:

1. ``setup_logging`` — configures the root logger with a JSON line
   formatter. Safe to call once at startup (idempotent).
2. A ``contextvars``-based correlation context (``request_id``,
   ``project_id``, ``conversation_id``, ``job_id``) with typed
   getter/setter helpers and a ``bind_context`` convenience.
3. ``CorrelationIdMiddleware`` — a Starlette ``BaseHTTPMiddleware`` that
   assigns a per-request id (honouring an inbound ``X-Request-ID``),
   binds it into the context, echoes it back on the response, and logs
   request start/end with method, path, status, and duration.

No ``structlog`` dependency: this is stdlib ``logging`` with a JSON
formatter and a ``logging.Filter`` that injects the current context
vars into every record.

Wiring (integration agent)
--------------------------
The middleware is a ``BaseHTTPMiddleware`` subclass, so wire it with::

    from open_edit.serve.logging_setup import (
        CorrelationIdMiddleware,
        setup_logging,
    )

    setup_logging()
    app.add_middleware(CorrelationIdMiddleware)

``add_middleware`` (not ``@app.middleware("http")``) is the expected
style — it takes the class, not an instance.
"""
from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Correlation context
# ---------------------------------------------------------------------------

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "open_edit_request_id", default=None
)
project_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "open_edit_project_id", default=None
)
conversation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "open_edit_conversation_id", default=None
)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "open_edit_job_id", default=None
)

_CONTEXT_VARS: dict[str, contextvars.ContextVar[str | None]] = {
    "request_id": request_id_var,
    "project_id": project_id_var,
    "conversation_id": conversation_id_var,
    "job_id": job_id_var,
}


def set_request_id(value: str | None) -> None:
    request_id_var.set(value)


def get_request_id() -> str | None:
    return request_id_var.get()


def set_project_id(value: str | None) -> None:
    project_id_var.set(value)


def get_project_id() -> str | None:
    return project_id_var.get()


def set_conversation_id(value: str | None) -> None:
    conversation_id_var.set(value)


def get_conversation_id() -> str | None:
    return conversation_id_var.get()


def set_job_id(value: str | None) -> None:
    job_id_var.set(value)


def get_job_id() -> str | None:
    return job_id_var.get()


def bind_context(**kwargs: str | None) -> None:
    """Set one or more correlation vars in the current context.

    Unknown keys raise ``KeyError`` so a typo doesn't silently no-op::

        bind_context(project_id="p1", job_id="abc")
    """
    for key, value in kwargs.items():
        try:
            var = _CONTEXT_VARS[key]
        except KeyError as exc:
            raise KeyError(f"unknown context var {key!r}") from exc
        var.set(value)


def get_context() -> dict[str, str | None]:
    """Snapshot the current correlation context as a plain dict."""
    return {name: var.get() for name, var in _CONTEXT_VARS.items()}


# ---------------------------------------------------------------------------
# Logging plumbing
# ---------------------------------------------------------------------------

class ContextFilter(logging.Filter):
    """Inject the current correlation context onto every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, var in _CONTEXT_VARS.items():
            setattr(record, name, var.get())
        return True


_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class JsonFormatter(logging.Formatter):
    """Render a log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in _CONTEXT_VARS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Surface any explicit ``extra=`` fields the caller attached.
        for key, value in record.__dict__.items():
            if key in _RESERVED or key in _CONTEXT_VARS or key in payload:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with the JSON formatter + context filter.

    Idempotent: repeated calls only adjust the level, they don't stack
    handlers. Safe to call once at application startup.
    """
    global _CONFIGURED
    resolved = logging.getLevelName(level.upper()) if isinstance(level, str) else level
    if not isinstance(resolved, int):
        resolved = logging.INFO

    root = logging.getLogger()
    root.setLevel(resolved)

    if _CONFIGURED:
        for handler in root.handlers:
            handler.setLevel(resolved)
        return

    handler = logging.StreamHandler()
    handler.setLevel(resolved)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger whose records carry the current context vars.

    The context is injected by a ``ContextFilter`` attached to the
    logger, so records propagate the correlation ids even if
    ``setup_logging`` hasn't run yet.
    """
    logger = logging.getLogger(name)
    if not any(isinstance(f, ContextFilter) for f in logger.filters):
        logger.addFilter(ContextFilter())
    return logger


_MW_LOG = get_logger("open_edit.serve.request")

REQUEST_ID_HEADER = "X-Request-ID"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assign, bind, and echo a per-request correlation id.

    Expected wiring is ``app.add_middleware(CorrelationIdMiddleware)``
    (it's a ``BaseHTTPMiddleware`` subclass — pass the class, not an
    instance). It:

    * reads ``X-Request-ID`` from the request, or mints ``uuid4().hex``;
    * binds it into ``request_id_var`` for the duration of the request;
    * logs request start and end (method, path, status, duration_ms);
    * echoes the id back in the ``X-Request-ID`` response header.
    """

    def __init__(self, app: Any, *, header_name: str = REQUEST_ID_HEADER) -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(self._header_name) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        _MW_LOG.info(
            "request start",
            extra={"method": request.method, "path": request.url.path},
        )
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 3)
            response.headers[self._header_name] = request_id
            _MW_LOG.info(
                "request end",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 3)
            _MW_LOG.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            request_id_var.reset(token)
