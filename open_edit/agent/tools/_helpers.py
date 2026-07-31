"""Shared helpers for the agent tool wrappers.

Path resolution (``_project_root``, ``_db_path``, ``_notes_db_path``),
project loading for read-back operations (``load_project``), and the
mutating-path IR builder (``make_ir``), which wraps the project's
``EditGraphStore`` in ``_StoreBuffer`` to match the IR's
``SupportsAppend`` protocol: the store's ``append`` takes a
``sequence_num`` kwarg, and ``_StoreBuffer`` drops it so the store
auto-assigns. ``get_asset_store`` locates the project's asset CAS.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from open_edit.ir.api import IR
from open_edit.ir.types import Project
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


class _StoreBuffer:
    """Adapts an EditGraphStore to the IR's SupportsAppend protocol.

    EditGraphStore.append takes (op, sequence_num=None); the IR calls
    `self._ops.append(op)` (single arg). We drop the sequence_num kwarg
    here and let EditGraphStore auto-assign it.
    """

    def __init__(self, store: EditGraphStore):
        self._store = store

    def append(self, op: Any) -> None:
        self._store.append(op)


def _project_root(project_path: str | Path) -> Path:
    """Return the project ROOT directory (the folder that contains
    ``.open_edit/``). Accepts either the root itself or a file inside it
    (legacy convention where ``project_path`` was a .kdenlive file).
    """
    p = Path(project_path)
    return p if p.is_dir() else p.parent


def _db_path(project_path: str | Path) -> Path:
    """Return the edit_graph.db path for the given project directory.

    Canonical server layout (``serve/projects.py``) stores the DB at
    ``<root>/.open_edit/edit_graph.db``. Older tooling wrote it directly
    at ``<root>/edit_graph.db``; we read the legacy path only when the
    canonical one is absent, and always prefer the canonical path for
    creation so new writes land where the server looks for them.
    """
    root = _project_root(project_path)
    canonical = root / ".open_edit" / "edit_graph.db"
    if canonical.exists() or (root / ".open_edit").is_dir():
        return canonical
    legacy = root / "edit_graph.db"
    if legacy.exists():
        return legacy
    return canonical


def _notes_db_path(project_path: str | Path) -> Path:
    """Return the notes.db path. Notes live at the project ROOT
    (``<root>/notes.db``), NOT inside ``.open_edit/`` — see
    ``serve/projects.py`` which reads them from the root.
    """
    return _project_root(project_path) / "notes.db"


def load_project(project_path: str | Path) -> Project:
    """Load a Project from the project directory.

    For read-back operations. Raises FileNotFoundError if the db doesn't exist.
    """

    db_path = _db_path(project_path)
    if not db_path.exists():
        raise FileNotFoundError(f"edit_graph.db not found at {db_path}")
    store = EditGraphStore(db_path)
    workdir = _project_root(project_path)
    project = Project(
        project_id=store.project_id,
        name=workdir.name or "untitled",
        workdir=workdir,
        assets={},
        edit_graph=store.load_all(),
    )
    return project


def make_ir(project_path: str | Path, parent_op_id: Optional[str] = None) -> IR:
    """Create an IR instance backed by the project's EditGraphStore.

    For mutating operations. The returned IR appends ops directly to
    the project's edit_graph.db file.
    """
    db_path = _db_path(project_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = EditGraphStore(db_path)
    project_id = store.project_id
    buffer = _StoreBuffer(store)
    # parent_op_id may be None for pillar/MCP mutations (no note chain).
    return IR(buffer, project_id=project_id, parent_op_id=parent_op_id)  # type: ignore[arg-type]


def get_asset_store(project_path: str | Path) -> AssetStore:
    """Return the AssetStore rooted at <project>/.open_edit/assets."""
    workdir = _project_root(project_path)
    return AssetStore(workdir / ".open_edit" / "assets")
