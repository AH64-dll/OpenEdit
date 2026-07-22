"""Shared helpers for the 32 repointed wrappers + 5 new tools.

Each wrapper function takes `(args, project_path)` and uses `make_ir()`
to construct an `IR` instance backed by the project's `EditGraphStore`.
The store's `append` method takes a sequence_num, so we wrap it in
`_StoreBuffer` to match the IR's `SupportsAppend` protocol.
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


class _ReadBackBuffer(list):
    """No-op buffer for read-back operations: collects ops but never persists."""

    def append(self, op: Any) -> None:
        super().append(op)


def _db_path(project_path: str | Path) -> Path:
    """Return the edit_graph.db path for the given project directory.

    Accepts either a directory (containing edit_graph.db) or a file path
    (whose parent contains edit_graph.db). The latter supports the old
    convention where `project_path` was a .kdenlive file.
    """
    p = Path(project_path)
    if p.is_dir() or p.suffix == "":
        return p / "edit_graph.db"
    return p.parent / "edit_graph.db"


def load_project(project_path: str | Path) -> Project:
    """Load a Project from the project directory.

    For read-back operations. Raises FileNotFoundError if the db doesn't exist.
    """

    db_path = _db_path(project_path)
    if not db_path.exists():
        raise FileNotFoundError(f"edit_graph.db not found at {db_path}")
    store = EditGraphStore(db_path)
    pp = Path(project_path)
    workdir = pp if pp.is_dir() else pp.parent
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
    return IR(buffer, project_id=project_id, parent_op_id=parent_op_id)


def get_asset_store(project_path: str | Path) -> AssetStore:
    """Return the AssetStore rooted at <project>/.open_edit/assets."""
    p = Path(project_path)
    workdir = p if p.is_dir() else p.parent
    return AssetStore(workdir / ".open_edit" / "assets")
