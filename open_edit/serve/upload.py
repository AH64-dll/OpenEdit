"""Streamed-upload helpers for the Open Edit server.

Extracted verbatim from ``serve/app.py`` when the app was split into
routers (Task 5.2). Bounds uploads while streaming so an oversized
file can never exhaust disk.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("open_edit.serve.upload")

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
