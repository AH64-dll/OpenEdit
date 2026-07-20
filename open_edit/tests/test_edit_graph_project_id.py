"""Phase 3 Task 1: EditGraphStore.project_id round-trip + Project.workdir Optional."""
import json
from pathlib import Path

import pytest

from open_edit.ir.types import Project
from open_edit.storage.edit_graph import EditGraphStore


def test_edit_graph_store_persists_project_id(tmp_path):
    """project_id is generated on first open and stable across reopens."""
    db = tmp_path / "edit_graph.db"
    store1 = EditGraphStore(db)
    pid = store1.project_id
    assert isinstance(pid, str) and len(pid) > 0

    # Reopen: same project_id
    store2 = EditGraphStore(db)
    assert store2.project_id == pid


def test_project_workdir_optional():
    """M8: Project.workdir is Optional, back-compat with Phase 0+1 fixtures."""
    p = Project(name="test")
    assert p.workdir is None
    p2 = Project(name="test", workdir=Path("/tmp/x"))
    assert p2.workdir == Path("/tmp/x")


def test_project_loads_with_workdir_none(tmp_path):
    """Phase 0+1 edit_graph.json without workdir still deserializes."""
    p = Project.model_validate({"name": "legacy", "assets": {}, "edit_graph": []})
    assert p.workdir is None
    assert p.name == "legacy"
