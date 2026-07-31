"""Canonical tool result contract.

Every agent tool wrapper returns one of three shapes:

- success: ``{"status": "ok", ...}`` (tool-specific payload)
- error:   ``{"status": "error", "error": str(e)}``
- retry:   ``{"status": "retry", "error": "..."}``

``@tool_result`` normalizes exceptions onto this contract so wrappers only
handle their own success path. ``get_asset_or_error`` and
``require_alignment`` produce the canonical "asset not found" and
"alignment pending — retry" dicts, so every tool emits identical errors
(and the agent can special-case retry status).

Note on the Asset model: the brief drafted ``require_alignment`` against a
``word_alignment`` field, but the actual model (``open_edit/ir/types.py``)
names it ``alignment`` (``list[WordAlignment]``). We check ``asset.alignment``.
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional, TypeVar

from open_edit.agent.tools._helpers import get_asset_store
from open_edit.ir.types import Asset

logger = logging.getLogger("open_edit.agent.tools._contract")

F = TypeVar("F", bound=Callable[..., Any])


class ToolError(Exception):
    """Base class for tool-domain errors surfaced as ``{"status": "error"}``."""


class ToolRetryableError(ToolError):
    """Tool error that should be retried later (e.g. transcription pending).

    Normalized by ``@tool_result`` to ``{"status": "retry", "error": ...}``.
    """


def tool_result(fn: F) -> F:
    """Decorator: catch exceptions and return the canonical error dict.

    ``ToolRetryableError`` → ``{"status": "retry", "error": str(e)}``.
    Any other ``Exception`` → ``logger.exception(...)`` + ``{"status":
    "error", "error": str(e)}``. Any return value passes through untouched.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolRetryableError as e:
            return {"status": "retry", "error": str(e)}
        except Exception as e:
            logger.exception("tool %s failed: %s", fn.__name__, e)
            return {"status": "error", "error": str(e)}

    return wrapper  # type: ignore[return-value]


def get_asset_or_error(project_path: str, asset_hash: str) -> tuple[Optional[Asset], Optional[dict]]:
    """Look up an asset in the project's CAS.

    Returns ``(asset, None)`` on success, or ``(None, canonical error
    dict)`` when the asset is not present.
    """
    store = get_asset_store(project_path)
    asset = store.get(asset_hash)
    if asset is None:
        return None, {"status": "error", "error": f"asset {asset_hash} not found"}
    return asset, None


def require_alignment(asset: Asset) -> Optional[dict]:
    """Check an asset has word-level alignment.

    Returns ``None`` when ``asset.alignment`` is non-empty, else the
    canonical "alignment pending — retry" dict.
    """
    if asset.alignment:
        return None
    return {
        "status": "retry",
        "error": (
            "asset has no word-level alignment yet. Transcription may "
            "still be running server-side. Wait a few seconds and retry."
        ),
    }
