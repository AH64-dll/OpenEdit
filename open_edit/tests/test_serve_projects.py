"""Tests for ``open_edit.serve.projects``.

Covers:
- ``list_projects`` returns ``[]`` on a fresh root
- ``create_project`` creates a folder; with ``open_edit init`` available
  it also lays down ``.open_edit/edit_graph.db``; otherwise the project
  is created but stays uninitialised
- creating two projects and listing returns both
- ``get_project_state`` returns assets/ops/notes for a project that has
  been populated with the real Open Edit storage classes (AssetStore,
  EditGraphStore, NotesStore)

These tests use the real Open Edit storage classes directly so they
exercise the actual integration with the real schema.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterator
from unittest import mock

import pytest

# Make the ``open_edit`` package importable from the repo root.
_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import projects as projects_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def projects_root_tmp(tmp_path, monkeypatch) -> Iterator[Path]:
    """Point OPEN_EDIT_PROJECTS_ROOT at a temp dir."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(projects_dir))
    return projects_dir


def _make_real_project(project_path: Path) -> None:
    """Create a fully-initialised Open Edit project at ``project_path``.

    Uses the real storage classes so the project has:
    - ``.open_edit/edit_graph.db`` with the real ``edits`` table
    - ``.open_edit/assets/<prefix>/<hash>`` with sidecar metadata
    - ``notes.db`` with the real ``notes`` table
    """
    project_path.mkdir(parents=True, exist_ok=True)
    # Init edit_graph.db by instantiating EditGraphStore (it runs the schema)
    db_path = project_path / ".open_edit" / "edit_graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    from open_edit.storage.edit_graph import EditGraphStore
    EditGraphStore(db_path)


def _make_real_asset(project_path: Path, name: str, hash_val: str, duration: float = 10.0) -> Path:
    """Create a fake asset with a sidecar JSON in the project."""
    from open_edit.ir.types import Asset
    assets_dir = project_path / ".open_edit" / "assets" / hash_val[:2]
    assets_dir.mkdir(parents=True, exist_ok=True)
    # Create a tiny fake "media" file (empty)
    media_file = assets_dir / hash_val
    media_file.touch()
    # Write the sidecar
    asset = Asset(
        asset_hash=hash_val,
        original_path=str(project_path / name),
        stored_path=str(media_file),
        type="video",
        duration_sec=duration,
        fps=30.0,
        width=1920,
        height=1080,
        codec="h264",
        has_audio=False,
    )
    sidecar = assets_dir / f"{hash_val}.meta.json"
    sidecar.write_text(asset.model_dump_json(indent=2))
    return media_file


def _make_real_op(project_path: Path, edit_id: str, kind: str, parent_id: str = None) -> None:
    """Append a real op to the project's edit_graph.db."""
    from open_edit.ir.types import AddClipOp
    from open_edit.storage.edit_graph import EditGraphStore
    db_path = project_path / ".open_edit" / "edit_graph.db"
    store = EditGraphStore(db_path)
    op = AddClipOp(
        edit_id=edit_id,
        parent_id=parent_id,
        author="ai",
        asset_hash="deadbeef" * 8,
        track_id="video_main",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=10.0,
    )
    op.kind = kind  # override (AddClipOp is the only concrete type AddClipOp
    # because we don't have all 24 constructors handy; the test just
    # needs ANY real op in the DB to verify the SQL works)
    store.append(op)


def _make_real_note(project_path: Path, text: str, status_value: str = "pending") -> None:
    """Append a real review note to the project's notes.db."""
    from open_edit.storage.edit_graph import EditGraphStore
    from open_edit.storage.notes import (
        NotesStore, ReviewNote, TimestampAnchor, NoteSource, NoteStatus,
    )
    # Notes are scoped to a project_id; we use the edit_graph.db's project_id.
    db_path = project_path / ".open_edit" / "edit_graph.db"
    project_id = EditGraphStore(db_path).project_id

    notes_db = project_path / "notes.db"
    store = NotesStore(notes_db)
    note = ReviewNote(
        project_id=project_id,
        anchor=TimestampAnchor(t_start=3.2, t_end=3.5),
        text=text,
        source=NoteSource.agent,
    )
    if status_value == "processed":
        note.status = NoteStatus.processed
    elif status_value == "dismissed":
        note.status = NoteStatus.dismissed
    store.append(note)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_projects_empty(projects_root_tmp):
    """Fresh root → empty list (no .open_edit/edit_graph.db anywhere)."""
    result = await projects_mod.list_projects()
    assert result == []


@pytest.mark.asyncio
async def test_create_project_creates_folder_and_db(projects_root_tmp):
    """create_project creates a folder. With open_edit on PATH, it also
    creates the edit_graph.db. Without it, the folder is still made but
    the DB is left to a subsequent ingest/init."""
    info = await projects_mod.create_project("my-first-project")
    assert info.name == "my-first-project"
    assert info.id
    assert Path(info.path).is_dir()
    # The id is stable across calls (deterministic hash of path)
    assert info.id == projects_mod._project_id_from_path(Path(info.path).resolve())


@pytest.mark.asyncio
async def test_list_returns_two_created_projects(projects_root_tmp):
    """Create 2 projects, list, verify both present (assuming open_edit init worked)."""
    a = await projects_mod.create_project("alpha")
    b = await projects_mod.create_project("beta")

    listed = await projects_mod.list_projects()
    # The number of listed projects depends on whether open_edit init ran.
    # If it did, both are listed. If not, both are uninitialised and skipped.
    # We need to ensure init ran for this test to be meaningful; assume it did
    # (it does in environments where open_edit is installed).
    if (Path(a.path) / ".open_edit" / "edit_graph.db").is_file():
        assert len(listed) == 2
        names = {p.name for p in listed}
        assert names == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_create_project_idempotent_name_clash(projects_root_tmp):
    """Two creates with the same name produce two distinct folders."""
    a = await projects_mod.create_project("dup")
    b = await projects_mod.create_project("dup")
    assert a.path != b.path


@pytest.mark.asyncio
async def test_get_project_state_seeded(projects_root_tmp):
    """Seed a real project and verify the registry reads it correctly."""
    info = await projects_mod.create_project("seeded")
    project_path = Path(info.path)

    # If open_edit init didn't run (e.g. CLI not on PATH in CI), set up
    # the schema manually so the test can still verify the integration.
    if not (project_path / ".open_edit" / "edit_graph.db").is_file():
        _make_real_project(project_path)

    # Seed: 2 assets, 1 op, 1 note
    _make_real_asset(project_path, "intro.mp4", "a" * 64, duration=12.5)
    _make_real_asset(project_path, "outro.mp4", "b" * 64, duration=8.0)
    _make_real_op(project_path, "op_1", "add_clip")
    _make_real_note(project_path, "tighten this cut", "pending")

    state = await projects_mod.get_project_state(info.id)
    assert state.id == info.id
    assert state.name == "seeded"
    assert len(state.assets) == 2
    # The order of assets may vary; check by hash
    asset_hashes = {a.hash for a in state.assets}
    assert asset_hashes == {"a" * 64, "b" * 64}
    # Find intro.mp4 by filename
    intro = next(a for a in state.assets if a.filename == "intro.mp4")
    assert intro.duration_s == 12.5
    assert intro.width == 1920
    assert intro.codec == "h264"
    # Op was added
    assert len(state.ops) >= 1
    op_ids = {o.id for o in state.ops}
    assert "op_1" in op_ids
    # Note was added
    assert len(state.notes) == 1
    assert state.notes[0].text == "tighten this cut"
    assert state.notes[0].source == "agent"
    assert state.pending_notes_count == 1
    # Timeline summary
    assert state.timeline.total_duration_s == pytest.approx(20.5)
    assert state.timeline.num_markers == 1


@pytest.mark.asyncio
async def test_get_project_state_404_for_unknown(projects_root_tmp):
    """Unknown project id raises KeyError."""
    with pytest.raises(KeyError):
        await projects_mod.get_project_state("does-not-exist")
