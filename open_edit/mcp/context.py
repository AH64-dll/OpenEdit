"""Project path resolution for the local MCP server."""
from __future__ import annotations

import os
from pathlib import Path


class ProjectPathError(ValueError):
    """Raised when the MCP server cannot bind to a valid Open Edit project."""


def resolve_project_path(
    project: str | Path | None = None,
    *,
    env: dict[str, str] | None = None,
) -> Path:
    """Resolve and validate the project directory for MCP tool dispatch.

    Preference order:
    1. Explicit ``project`` argument (``--project``).
    2. ``OPEN_EDIT_PROJECT`` environment variable.

    The path must exist and contain a ``.open_edit/`` directory (initialize
    with ``open_edit init`` first).
    """
    environ = env if env is not None else os.environ
    raw = project if project is not None else environ.get("OPEN_EDIT_PROJECT")
    if not raw or not str(raw).strip():
        raise ProjectPathError(
            "project path required: pass --project /path/to/proj "
            "or set OPEN_EDIT_PROJECT"
        )

    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise ProjectPathError(f"project path is not a directory: {path}")

    marker = path / ".open_edit"
    if not marker.is_dir():
        raise ProjectPathError(
            f"not an Open Edit project (missing .open_edit/): {path}. "
            f"Run: open_edit init {path}"
        )
    return path
