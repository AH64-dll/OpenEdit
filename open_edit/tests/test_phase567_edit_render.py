"""Phase 5/6 tests: timeline commands, graph_revision on state, render binding."""
from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_edit.ir.types import AddClipOp
from open_edit.serve import projects as projects_mod
from open_edit.serve.app import app
from open_edit.serve.edit_graph_service import apply_command
from open_edit.serve.render_service import RenderEnqueueError, RenderService
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict

client = TestClient(app)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(tmp_path))
    info = asyncio.run(projects_mod.create_project(f"p5_{uuid.uuid4().hex[:8]}"))
    return info


def test_project_state_includes_graph_revision(project):
    state = asyncio.run(projects_mod.get_project_state(project.id))
    assert isinstance(state.graph_revision, int)
    assert state.graph_revision >= 0
    assert state.timeline_status in ("valid", "invalid")


def test_apply_command_add_clip_bumps_revision(project):
    path = Path(project.path)
    before = EditGraphStore(path / ".open_edit" / "edit_graph.db").graph_revision()
    result = apply_command(
        path,
        "add_clip",
        {
            "asset_hash": "a" * 64,
            "track_id": "V1",
            "position_sec": 0,
            "in_point_sec": 0,
            "out_point_sec": 2.5,
        },
        author="user",
        expected_revision=before,
    )
    assert result["kind"] == "add_clip"
    assert result["graph_revision"] == before + 1
    assert result["op"]["author"] == "user"


def test_apply_command_stale_revision_rejected(project):
    path = Path(project.path)
    apply_command(
        path,
        "add_clip",
        {"asset_hash": "b" * 64, "track_id": "V1", "position_sec": 0},
        author="user",
    )
    with pytest.raises(GraphRevisionConflict):
        apply_command(
            path,
            "add_clip",
            {"asset_hash": "c" * 64, "track_id": "V1", "position_sec": 1},
            author="user",
            expected_revision=0,
        )


def test_post_ops_endpoint(project):
    r = client.post(
        f"/api/projects/{project.id}/ops",
        json={
            "command": "add_clip",
            "params": {
                "asset_hash": "d" * 64,
                "track_id": "V1",
                "position_sec": 0,
                "out_point_sec": 1,
            },
            "author": "user",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "add_clip"
    assert body["graph_revision"] >= 1


def test_get_project_exposes_revision(project):
    client.post(
        f"/api/projects/{project.id}/ops",
        json={
            "command": "add_clip",
            "params": {"asset_hash": "e" * 64, "track_id": "V1", "position_sec": 0},
        },
    )
    r = client.get(f"/api/projects/{project.id}")
    assert r.status_code == 200
    body = r.json()
    assert "graph_revision" in body
    assert body["graph_revision"] >= 1


@pytest.mark.asyncio
async def test_render_enqueue_stores_graph_revision(tmp_path):
    project = tmp_path / "proj"
    (project / ".open_edit").mkdir(parents=True)
    store = EditGraphStore(project / ".open_edit" / "edit_graph.db")
    store.append(AddClipOp(
        edit_id=str(uuid.uuid4()),
        author="user",
        asset_hash="f" * 64,
        track_id="V1",
        position_sec=0,
        in_point_sec=0,
        out_point_sec=1,
    ))
    revision = store.graph_revision()
    service = RenderService()

    async def ok(project_path, job_id, mode):
        return {"ok": True, "output_path": str(project / "out.mp4"), "mode": mode}

    service._launch = ok  # type: ignore[method-assign]
    job = service.enqueue("proj", project, "proxy", expected_revision=revision)
    assert job.graph_revision == revision
    assert job.edit_graph_hash
    completed = await service.wait(project, job.job_id)
    assert completed.status == "succeeded"


@pytest.mark.asyncio
async def test_render_enqueue_rejects_stale_revision(tmp_path):
    project = tmp_path / "proj"
    (project / ".open_edit").mkdir(parents=True)
    EditGraphStore(project / ".open_edit" / "edit_graph.db")
    service = RenderService()
    with pytest.raises(RenderEnqueueError, match="stale graph revision"):
        service.enqueue("proj", project, "proxy", expected_revision=99)


@pytest.mark.asyncio
async def test_overlay_mode_goes_through_render_service(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    (project / ".open_edit").mkdir(parents=True)
    service = RenderService()

    async def overlay_launch(project_path, job_id, mode):
        assert mode == "overlay"
        return {"ok": True, "output_path": str(project / "overlay.mp4"), "mode": mode}

    service._launch = overlay_launch  # type: ignore[method-assign]
    job = service.enqueue("proj", project, "overlay")
    completed = await service.wait(project, job.job_id)
    assert completed.status == "succeeded"
    assert completed.mode == "overlay"
