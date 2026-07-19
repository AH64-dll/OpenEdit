"""Error classes for the editor backend.

All errors raised by backend code inherit BackendError. ValidationError
is the only one the LLM should see in normal flow — it always carries
a `fix:` line so the LLM can self-correct.

Hierarchy:
    BackendError
    ├── ValidationError   (bad input — LLM self-corrects)
    ├── NotFoundError     (clip/track not in project)
    └── CatalogError      (effect/transition not in catalog)
"""
from __future__ import annotations


class BackendError(Exception):
    """Base for all backend errors."""


class ValidationError(BackendError):
    """Bad input. The message MUST contain a `fix:` line."""


class NotFoundError(BackendError):
    """Referenced clip/track/effect/transition not in the project."""


class CatalogError(BackendError):
    """Effect/transition id not in Phase 1's catalog."""


def validation_error(msg: str, fix_hint: str | None = None) -> ValidationError:
    """Build a ValidationError. Adds a `fix:` line if not already present.

    >>> e = validation_error("bad", "do good")
    >>> "fix:" in str(e) and "do good" in str(e)
    True
    """
    if "fix:" in msg:
        return ValidationError(msg)
    if fix_hint is None:
        return ValidationError(msg)
    return ValidationError(f"{msg}\nfix: {fix_hint}")


__all__ = [
    "BackendError", "ValidationError", "NotFoundError", "CatalogError",
    "validation_error",
]
