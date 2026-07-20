"""Phase 4 T5 carry-over #2: render_project's TimeoutExpired branch must
record a `failed` snapshot, so the version list surfaces the failed
attempt rather than disappearing silently (per audit M1 + audit H2).
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from open_edit.ir.types import AddClipOp
from open_edit.render.orchestrator import render_project
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.render_snapshots import (
    RenderSnapshotStore, RenderStatus,
)


def _has_melt() -> bool:
    import shutil
    return shutil.which("melt") is not None


pytestmark = pytest.mark.skipif(
    not _has_melt(), reason="melt not installed"
)


def _seed_project_with_one_op(project_dir: Path) -> None:
    """Set up `.open_edit/edit_graph.db` with one applied AddClipOp so
    `render_project` proceeds past the empty-graph check."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".open_edit").mkdir(parents=True, exist_ok=True)
    store = EditGraphStore(project_dir / ".open_edit" / "edit_graph.db")
    store.append(AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
    ))


def test_timeout_path_records_failed_snapshot(tmp_path: Path) -> None:
    """Per T5 carry-over #2: when melt times out, a `failed` snapshot is
    appended to the RenderSnapshotStore so the user sees the attempt."""
    _seed_project_with_one_op(tmp_path)
    workdir = tmp_path / "renders"

    with patch("open_edit.render.orchestrator.subprocess.run") as run_mock:
        run_mock.side_effect = subprocess.TimeoutExpired(cmd=["melt"], timeout=600)
        result = render_project(
            project_id=str(tmp_path),
            project_dir=tmp_path,
            workdir=workdir,
        )

    assert result.ok is False
    assert "timed out" in (result.error or "").lower()

    # The failure snapshot must be on disk so the version list shows it.
    snapshots = RenderSnapshotStore(tmp_path / ".open_edit" / "render_snapshots.db")
    snaps = snapshots.list_for_project(str(tmp_path))
    assert len(snaps) == 1
    assert snaps[0].status == RenderStatus.failed
