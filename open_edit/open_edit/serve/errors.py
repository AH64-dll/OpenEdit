"""Unified error envelope for the Open Edit server.

Provides a single, dependency-free shape for errors surfaced by tools,
render, and provider calls so clients can handle them uniformly.

The envelope is::

    {"error": {"code", "message", "retriable", "details",
               "request_id", "docs_url"}}
"""
from __future__ import annotations

from typing import Any


class ErrorCodes:
    """String constants for the unified error ``code`` field."""

    VALIDATION_FAILED = "validation_failed"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PERMISSION_DENIED = "permission_denied"
    AUTH_REQUIRED = "auth_required"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    RENDER_FAILED = "render_failed"
    PROVIDER_ERROR = "provider_error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


def make_error(
    code: str,
    message: str,
    *,
    retriable: bool = False,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    docs_url: str | None = None,
) -> dict[str, Any]:
    """Return a unified error envelope dict."""
    return {
        "error": {
            "code": code,
            "message": message,
            "retriable": retriable,
            "details": details,
            "request_id": request_id,
            "docs_url": docs_url,
        }
    }


def wrap_exception(
    exc: Exception,
    code: str = ErrorCodes.INTERNAL,
    **kw: Any,
) -> dict[str, Any]:
    """Build an error envelope from an exception, stringifying its message."""
    return make_error(code, str(exc), **kw)
